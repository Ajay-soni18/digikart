"""
Admin revenue & transactions analytics (IsAdminUser).

  GET /api/v1/admin/transactions/  — paginated transaction log with filters
  GET /api/v1/admin/revenue/       — totals, time-series, and subject/unit/chapter
                                      revenue breakdowns

Both accept ?from=YYYY-MM-DD&to=YYYY-MM-DD; transactions also accept
?status=paid|failed|created and ?search=<email/name/razorpay id>.
This lets the admin verify which payments succeeded vs failed (so no one can
make false claims) and slice revenue by date and by content.
"""

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDay, TruncMonth, TruncYear
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import generics, viewsets
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.content.models import Chapter, Note, Subject, Unit

from .models import Coupon, Order, OrderItem
from .serializers import AdminCouponSerializer, AdminTransactionSerializer


class AdminCouponViewSet(viewsets.ModelViewSet):
    """Full CRUD for discount coupons (create / edit / activate-deactivate via
    `is_active` / delete). Newest first; the React admin renders the list and
    a schema-driven form against this."""

    queryset = Coupon.objects.all().order_by("-created_at")
    serializer_class = AdminCouponSerializer
    permission_classes = [IsAdminUser]
    pagination_class = None
    search_fields = ["code"]


class AdminTransactionListView(generics.ListAPIView):
    """The full transaction log (newest first), with audit-friendly filters."""

    serializer_class = AdminTransactionSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = Order.objects.select_related("user").prefetch_related("items").all()
        p = self.request.query_params

        status = p.get("status")
        if status in {Order.Status.PAID, Order.Status.FAILED, Order.Status.CREATED}:
            qs = qs.filter(status=status)

        frm, to = parse_date(p.get("from") or ""), parse_date(p.get("to") or "")
        if frm:
            qs = qs.filter(created_at__date__gte=frm)
        if to:
            qs = qs.filter(created_at__date__lte=to)

        search = (p.get("search") or "").strip()
        if search:
            qs = qs.filter(
                Q(user__email__icontains=search)
                | Q(user__full_name__icontains=search)
                | Q(razorpay_payment_id__icontains=search)
                | Q(razorpay_order_id__icontains=search)
            )
        return qs


def _net_line_prices(items, order_totals):
    """Map each OrderItem id → the money actually received for that line.

    `OrderItem.price` is the pre-discount list price, but a coupon is applied at
    the order level only (`Order.amount` = subtotal − discount). Summing raw line
    prices would therefore overstate every breakdown by the discount. So we split
    each order's paid amount across its lines in proportion to their list prices;
    the largest line absorbs the rounding remainder, so the parts always add back
    to the order total exactly.
    """
    net = {}
    by_order = defaultdict(list)
    for it in items:
        by_order[it.order_id].append(it)

    for order_id, lines in by_order.items():
        gross = sum((li.price or Decimal("0.00") for li in lines), Decimal("0.00"))
        paid = order_totals.get(order_id)
        # Undiscounted (or unknown/degenerate) order → line prices are already net.
        if paid is None or gross <= 0 or paid == gross:
            for li in lines:
                net[li.id] = li.price or Decimal("0.00")
            continue
        ranked = sorted(lines, key=lambda li: li.price or Decimal("0.00"), reverse=True)
        allocated = Decimal("0.00")
        for li in ranked[1:]:
            share = ((li.price or Decimal("0.00")) * paid / gross).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            net[li.id] = share
            allocated += share
        net[ranked[0].id] = paid - allocated
    return net


def _breakdowns(paid_orders):
    """Roll paid OrderItem revenue up to the owning subject / unit / chapter.

    A note purchase counts toward its chapter, unit and subject; a chapter
    purchase toward its chapter, unit and subject; a unit purchase toward its unit
    and subject; a subject purchase toward the subject. Line revenue is net of any
    coupon (see `_net_line_prices`) so the breakdowns reconcile with the headline
    total. Items whose content was since deleted are skipped (the authoritative
    total still comes from order amounts).
    """
    items = list(
        OrderItem.objects.filter(order__in=paid_orders).select_related("content_type")
    )
    net_price = _net_line_prices(items, dict(paid_orders.values_list("id", "amount")))
    ct_no = ContentType.objects.get_for_model(Note)
    ct_ch = ContentType.objects.get_for_model(Chapter)
    ct_un = ContentType.objects.get_for_model(Unit)
    ct_su = ContentType.objects.get_for_model(Subject)

    no_ids = {i.object_id for i in items if i.content_type_id == ct_no.id}
    ch_ids = {i.object_id for i in items if i.content_type_id == ct_ch.id}
    un_ids = {i.object_id for i in items if i.content_type_id == ct_un.id}
    su_ids = {i.object_id for i in items if i.content_type_id == ct_su.id}

    notes = {n.id: n for n in Note.objects.filter(id__in=no_ids).select_related("chapter__unit__subject")}
    chapters = {c.id: c for c in Chapter.objects.filter(id__in=ch_ids).select_related("unit__subject")}
    units = {u.id: u for u in Unit.objects.filter(id__in=un_ids).select_related("subject")}
    subjects = {s.id: s for s in Subject.objects.filter(id__in=su_ids)}

    subj_rev, unit_rev, chap_rev = defaultdict(Decimal), defaultdict(Decimal), defaultdict(Decimal)
    subj_name, unit_name, chap_name = {}, {}, {}

    def _roll_up_chapter(c, price):
        """Attribute `price` to a chapter and its parent unit + subject."""
        chap_rev[c.id] += price; chap_name[c.id] = f"{c.unit.subject.name} · {c.name}"
        unit_rev[c.unit_id] += price; unit_name[c.unit_id] = f"{c.unit.subject.name} · {c.unit.name}"
        subj_rev[c.unit.subject_id] += price; subj_name[c.unit.subject_id] = c.unit.subject.name

    for it in items:
        price = net_price.get(it.id, it.price or Decimal("0.00"))
        if it.content_type_id == ct_no.id:
            n = notes.get(it.object_id)
            if not n:
                continue
            _roll_up_chapter(n.chapter, price)  # a note sale shows under its chapter
        elif it.content_type_id == ct_ch.id:
            c = chapters.get(it.object_id)
            if not c:
                continue
            _roll_up_chapter(c, price)
        elif it.content_type_id == ct_un.id:
            u = units.get(it.object_id)
            if not u:
                continue
            unit_rev[u.id] += price; unit_name[u.id] = f"{u.subject.name} · {u.name}"
            subj_rev[u.subject_id] += price; subj_name[u.subject_id] = u.subject.name
        elif it.content_type_id == ct_su.id:
            s = subjects.get(it.object_id)
            if not s:
                continue
            subj_rev[s.id] += price; subj_name[s.id] = s.name

    def rank(rev, names):
        rows = [{"id": k, "name": names.get(k, f"#{k}"), "revenue": v} for k, v in rev.items()]
        return sorted(rows, key=lambda r: r["revenue"], reverse=True)

    return rank(subj_rev, subj_name), rank(unit_rev, unit_name), rank(chap_rev, chap_name)


class AdminRevenueView(APIView):
    """Revenue totals, time-series and content breakdowns (date-range filterable)."""

    permission_classes = [IsAdminUser]

    def get(self, request):
        p = request.query_params
        frm, to = parse_date(p.get("from") or ""), parse_date(p.get("to") or "")
        now = timezone.now()

        # Range-scoped paid orders (drives total, series, breakdowns).
        paid = Order.objects.filter(status=Order.Status.PAID)
        if frm:
            paid = paid.filter(paid_at__date__gte=frm)
        if to:
            paid = paid.filter(paid_at__date__lte=to)

        all_paid = Order.objects.filter(status=Order.Status.PAID)

        def total(qs):
            return qs.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")

        summary = {
            "total_revenue": total(paid),
            "paid_count": paid.count(),
            "failed_count": Order.objects.filter(status=Order.Status.FAILED).count(),
            "pending_count": Order.objects.filter(status=Order.Status.CREATED).count(),
            "today": total(all_paid.filter(paid_at__date=now.date())),
            "this_month": total(all_paid.filter(paid_at__year=now.year, paid_at__month=now.month)),
            "this_year": total(all_paid.filter(paid_at__year=now.year)),
        }

        def series(trunc, key, fmt):
            rows = (paid.annotate(p=trunc("paid_at")).values("p")
                    .annotate(revenue=Sum("amount"), count=Count("id")).order_by("p"))
            return [{key: fmt(r["p"]), "revenue": r["revenue"], "count": r["count"]} for r in rows if r["p"]]

        by_subject, by_unit, by_chapter = _breakdowns(paid)

        return Response({
            "summary": summary,
            "daily": series(TruncDay, "date", lambda d: d.date().isoformat()),
            "monthly": series(TruncMonth, "month", lambda d: d.strftime("%Y-%m")),
            "yearly": series(TruncYear, "year", lambda d: str(d.year)),
            "by_subject": by_subject,
            "by_unit": by_unit,
            "by_chapter": by_chapter,
        })

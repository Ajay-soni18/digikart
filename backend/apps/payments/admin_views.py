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

from apps.catalog.models import Bundle, Category, Product

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
    """Roll paid OrderItem revenue up the category tree, plus a per-product list.

    A product sale counts toward its own category and every category above it, so
    a parent's figure is the true total of everything beneath it. A bundle sale
    counts toward the bundle's category chain — bundles are sold as a unit, and
    splitting one across its members would invent a breakdown the buyer never
    made. Line revenue is net of any coupon (see `_net_line_prices`) so the
    breakdowns reconcile with the headline total. Items whose product or bundle
    was since deleted are skipped; the authoritative total still comes from order
    amounts.
    """
    items = list(
        OrderItem.objects.filter(order__in=paid_orders).select_related("content_type")
    )
    net_price = _net_line_prices(items, dict(paid_orders.values_list("id", "amount")))
    ct_pr = ContentType.objects.get_for_model(Product)
    ct_bu = ContentType.objects.get_for_model(Bundle)

    pr_ids = {i.object_id for i in items if i.content_type_id == ct_pr.id}
    bu_ids = {i.object_id for i in items if i.content_type_id == ct_bu.id}
    products = {
        p.id: p for p in Product.objects.filter(id__in=pr_ids).select_related("category")
    }
    bundles = {
        b.id: b for b in Bundle.objects.filter(id__in=bu_ids).select_related("category")
    }

    cat_rev, cat_name = defaultdict(Decimal), {}
    prod_rev, prod_name = defaultdict(Decimal), {}

    def _roll_up(category, price):
        """Attribute `price` to a category and every ancestor above it."""
        if category is None:
            return
        for node in [*category.ancestors, category]:
            cat_rev[node.id] += price
            cat_name[node.id] = node.path

    for it in items:
        price = net_price.get(it.id, it.price or Decimal("0.00"))
        if it.content_type_id == ct_pr.id:
            product = products.get(it.object_id)
            if not product:
                continue
            prod_rev[product.id] += price
            prod_name[product.id] = f"{product.category.path} · {product.title}"
            _roll_up(product.category, price)
        elif it.content_type_id == ct_bu.id:
            bundle = bundles.get(it.object_id)
            if not bundle:
                continue
            prod_rev[f"bundle-{bundle.id}"] += price
            prod_name[f"bundle-{bundle.id}"] = f"{bundle.title} (bundle)"
            _roll_up(bundle.category, price)

    def rank(rev, names):
        rows = [{"id": k, "name": names.get(k, f"#{k}"), "revenue": v} for k, v in rev.items()]
        return sorted(rows, key=lambda r: r["revenue"], reverse=True)

    return rank(cat_rev, cat_name), rank(prod_rev, prod_name)


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

        by_category, by_product = _breakdowns(paid)

        return Response({
            "summary": summary,
            "daily": series(TruncDay, "date", lambda d: d.date().isoformat()),
            "monthly": series(TruncMonth, "month", lambda d: d.strftime("%Y-%m")),
            "yearly": series(TruncYear, "year", lambda d: str(d.year)),
            "by_category": by_category,
            "by_product": by_product,
        })

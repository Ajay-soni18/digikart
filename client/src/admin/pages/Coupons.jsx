/* Admin coupons — reuses the generic CrudPanel (create / edit / activate /
   deactivate / delete). Discount, usage and status show as badges. */
import { CrudPanel } from "../CrudPanel";

const discountLabel = (c) =>
  c.kind === "percent" ? `${Number(c.value)}% off` : `₹${Number(c.value)} off`;

const usageLabel = (c) =>
  c.max_uses ? `${c.used_count} / ${c.max_uses} used` : `${c.used_count} used`;

export default function Coupons() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight text-ink">Coupons</h1>
        <p className="text-sm text-ink-soft">
          Discount codes students can apply at checkout. Usage is counted only when a payment succeeds.
        </p>
      </div>
      <CrudPanel
        title="Coupons"
        addLabel="Add coupon"
        resource="coupons"
        itemLabel={(it) => it.code}
        renderBadges={(it, Badge) => (
          <>
            <Badge tone="brand">{discountLabel(it)}</Badge>
            <Badge tone="navy">{usageLabel(it)}</Badge>
            {it.reserved_count > 0 && <Badge tone="amber">{it.reserved_count} reserved</Badge>}
            {it.is_active ? <Badge tone="green">Active</Badge> : <Badge tone="gray">Inactive</Badge>}
          </>
        )}
      />
    </div>
  );
}

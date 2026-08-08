/* Admin announcements — reuses the generic CrudPanel. */
import { CrudPanel } from "../CrudPanel";

export default function Announcements() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight text-ink">Announcements</h1>
        <p className="text-sm text-ink-soft">Banners shown to buyers (new products, discounts, updates).</p>
      </div>
      <CrudPanel
        title="Announcements"
        addLabel="Add announcement"
        resource="announcements"
        itemLabel={(it) => it.title}
        renderBadges={(it, Badge) =>
          it.is_live ? <Badge tone="green">Live</Badge> : <Badge tone="gray">Hidden</Badge>
        }
      />
    </div>
  );
}

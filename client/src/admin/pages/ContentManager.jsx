/*
 * The content tree admin: drill from Years → Subjects → [Sections + Units] →
 * Chapters → [Lectures + Notes]. Each level reuses <CrudPanel>; a breadcrumb
 * tracks where you are. Parent IDs are injected into create payloads so new
 * rows attach to the right place.
 */
import { useState } from "react";
import { CrudPanel } from "../CrudPanel";
import { PlaylistImport } from "../PlaylistImport";

const money = (v) => `₹${Number(v).toFixed(0)}`;

// Shared badge renderers per resource.
const badges = {
  flags: (it, Badge) => (
    <>
      {it.is_coming_soon && <Badge tone="amber">Coming Soon</Badge>}
      {it.is_published === false && <Badge tone="gray">Hidden</Badge>}
    </>
  ),
  // How this chapter/unit/subject is sold as a whole (see content.BundlePricing).
  // `contents` names what's inside it ("Chapters" for a unit/subject, "Notes" for
  // a chapter) so the "not sold as a bundle" badge reads correctly at each level.
  bundle: (it, Badge, contents = "Chapters") =>
    it.bundle_pricing === "none" ? (
      <Badge tone="gray">{contents} only</Badge>
    ) : it.bundle_pricing === "custom" ? (
      <Badge tone="green">{money(it.bundle_price)} bundle</Badge>
    ) : (
      <Badge tone="green">Sum bundle</Badge>
    ),
};

export default function ContentManager() {
  // path crumbs: [{resource:'year', id, name}, ...]
  const [path, setPath] = useState([]);
  // Bumped after a playlist import so the Lectures panel reloads.
  const [lectureRefresh, setLectureRefresh] = useState(0);

  const push = (resource, item) =>
    setPath((p) => [...p, { resource, id: item.id, name: item.name || item.title }]);
  const truncate = (i) => setPath((p) => p.slice(0, i));

  const year = path[0];
  const subject = path[1];
  const unit = path[2];
  const chapter = path[3];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight text-ink">Content</h1>
        <p className="text-sm text-ink-soft">
          Manage years, subjects, units, chapters, lectures and notes.
        </p>
      </div>

      {/* Breadcrumb */}
      <nav className="flex flex-wrap items-center gap-1 text-sm">
        <button onClick={() => truncate(0)} className="font-semibold text-brand-700 dark:text-brand-300 hover:underline">
          Years
        </button>
        {path.map((c, i) => (
          <span key={i} className="flex items-center gap-1">
            <span className="text-brand-300">/</span>
            <button
              onClick={() => truncate(i + 1)}
              className="font-semibold text-brand-700 dark:text-brand-300 hover:underline"
            >
              {c.name}
            </button>
          </span>
        ))}
      </nav>

      {/* Level 0: Years */}
      {path.length === 0 && (
        <CrudPanel
          title="Years"
          addLabel="Add year"
          resource="years"
          selectable
          supportsComingSoon
          onOpen={(it) => push("year", it)}
          renderBadges={(it, Badge) => (
            <>
              {badges.flags(it, Badge)}
              <Badge tone="brand">{it.subject_count} subjects</Badge>
            </>
          )}
        />
      )}

      {/* Level 1: Subjects under a year */}
      {path.length === 1 && (
        <CrudPanel
          title="Subjects"
          addLabel="Add subject"
          resource="subjects"
          params={{ year: year.id }}
          parentDefaults={{ year: year.id }}
          selectable
          supportsComingSoon
          onOpen={(it) => push("subject", it)}
          renderBadges={(it, Badge) => (
            <>
              {badges.flags(it, Badge)}
              {badges.bundle(it, Badge)}
              <Badge tone="brand">{it.unit_count} units</Badge>
            </>
          )}
        />
      )}

      {/* Level 2: Subject detail — sections + units */}
      {path.length === 2 && (
        <div className="grid gap-6 lg:grid-cols-2">
          <CrudPanel
            title="Sections"
            addLabel="Add section"
            resource="sections"
            params={{ subject: subject.id }}
            parentDefaults={{ subject: subject.id }}
            itemLabel={(it) => it.label}
            selectable
            supportsComingSoon
            renderBadges={(it, Badge) => badges.flags(it, Badge)}
          />
          <CrudPanel
            title="Units"
            addLabel="Add unit"
            resource="units"
            params={{ subject: subject.id }}
            parentDefaults={{ subject: subject.id }}
            selectable
            supportsComingSoon
            onOpen={(it) => push("unit", it)}
            renderBadges={(it, Badge) => (
              <>
                {badges.flags(it, Badge)}
                {badges.bundle(it, Badge)}
                <Badge tone="brand">{it.chapter_count} chapters</Badge>
              </>
            )}
          />
        </div>
      )}

      {/* Level 3: Chapters under a unit */}
      {path.length === 3 && (
        <CrudPanel
          title="Chapters"
          addLabel="Add chapter"
          resource="chapters"
          params={{ unit: unit.id }}
          parentDefaults={{ unit: unit.id }}
          selectable
          supportsComingSoon
          onOpen={(it) => push("chapter", it)}
          renderBadges={(it, Badge) => (
            <>
              {it.is_free ? <Badge tone="green">Free</Badge> : badges.bundle(it, Badge, "Notes")}
              {badges.flags(it, Badge)}
              <Badge tone="gray">{it.lecture_count} lec · {it.note_count} notes</Badge>
            </>
          )}
        />
      )}

      {/* Level 4: Chapter detail — lectures + notes */}
      {path.length === 4 && (
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="space-y-6">
            <CrudPanel
              title="Lectures"
              addLabel="Add lecture"
              resource="lectures"
              params={{ chapter: chapter.id }}
              parentDefaults={{ chapter: chapter.id }}
              itemLabel={(it) => it.title}
              selectable
              refreshToken={lectureRefresh}
              renderBadges={(it, Badge) => (it.is_published === false ? <Badge tone="gray">Hidden</Badge> : null)}
            />
            <PlaylistImport
              chapterId={chapter.id}
              onImported={() => setLectureRefresh((n) => n + 1)}
            />
          </div>
          <CrudPanel
            title="Notes"
            addLabel="Upload note"
            resource="notes"
            params={{ chapter: chapter.id }}
            parentDefaults={{ chapter: chapter.id }}
            itemLabel={(it) => it.title}
            selectable
            renderBadges={(it, Badge) => (
              <>
                {it.is_free ? (
                  <Badge tone="green">Free</Badge>
                ) : Number(it.price) > 0 ? (
                  <Badge tone="gold">{money(it.price)}</Badge>
                ) : (
                  <Badge tone="gray">In chapter only</Badge>
                )}
                <Badge tone="brand">{it.file_type}</Badge>
                {it.is_published === false && <Badge tone="gray">Hidden</Badge>}
              </>
            )}
          />
        </div>
      )}
    </div>
  );
}

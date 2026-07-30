/*
 * Admin manager for general (dashboard) videos — a 3-level tree that is NOT
 * part of the year → subject → unit → chapter content:
 *
 *   Heading (e.g. "The Academic Edge")
 *     → Subheading / playlist card (e.g. "How to study")
 *       → Videos
 *
 * Drill from Headings → Subheadings → Videos. Each level reuses <CrudPanel>; a
 * breadcrumb tracks where you are and parent IDs are injected into create
 * payloads. The chapter-level <PlaylistImport> is reused at the subheading level
 * to bulk-import a YouTube playlist's videos.
 */
import { useState } from "react";
import { CrudPanel } from "../CrudPanel";
import { PlaylistImport } from "../PlaylistImport";

export default function GeneralVideos() {
  // path crumbs: [{resource:'heading', id, name}, {resource:'section', id, name}]
  const [path, setPath] = useState([]);
  // Bumped after a playlist import so the Videos panel reloads.
  const [videoRefresh, setVideoRefresh] = useState(0);

  const push = (resource, item) =>
    setPath((p) => [...p, { resource, id: item.id, name: item.title }]);
  const truncate = (i) => setPath((p) => p.slice(0, i));

  const heading = path[0];
  const section = path[1];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight text-ink">General Videos</h1>
        <p className="text-sm text-ink-soft">
          Dashboard video playlists (e.g. “The Academic Edge”). Create a heading,
          add subheading playlists under it, then fill each with videos. Separate
          from the MBBS year/subject content.
        </p>
      </div>

      {/* Breadcrumb */}
      <nav className="flex flex-wrap items-center gap-1 text-sm">
        <button onClick={() => truncate(0)} className="font-semibold text-brand-700 dark:text-brand-300 hover:underline">
          Headings
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

      {/* Level 0: headings */}
      {path.length === 0 && (
        <CrudPanel
          title="Headings"
          addLabel="Add heading"
          resource="general-headings"
          selectable
          itemLabel={(it) => it.title}
          onOpen={(it) => push("heading", it)}
          renderBadges={(it, Badge) => (
            <>
              {it.is_published === false && <Badge tone="gray">Hidden</Badge>}
              <Badge tone="brand">{it.playlist_count} playlists</Badge>
            </>
          )}
        />
      )}

      {/* Level 1: subheadings (playlists) under a heading */}
      {path.length === 1 && (
        <CrudPanel
          title="Subheadings"
          addLabel="Add subheading"
          resource="general-sections"
          params={{ heading: heading.id }}
          parentDefaults={{ heading: heading.id }}
          selectable
          itemLabel={(it) => it.title}
          onOpen={(it) => push("section", it)}
          renderBadges={(it, Badge) => (
            <>
              {it.is_published === false && <Badge tone="gray">Hidden</Badge>}
              <Badge tone="brand">{it.video_count} videos</Badge>
            </>
          )}
        />
      )}

      {/* Level 2: videos within a subheading + playlist import */}
      {path.length === 2 && (
        <div className="space-y-6">
          <CrudPanel
            title="Videos"
            addLabel="Add video"
            resource="general-videos"
            params={{ section: section.id }}
            parentDefaults={{ section: section.id }}
            itemLabel={(it) => it.title}
            selectable
            refreshToken={videoRefresh}
            renderBadges={(it, Badge) => (it.is_published === false ? <Badge tone="gray">Hidden</Badge> : null)}
          />
          <PlaylistImport
            sectionId={section.id}
            onImported={() => setVideoRefresh((n) => n + 1)}
          />
        </div>
      )}
    </div>
  );
}

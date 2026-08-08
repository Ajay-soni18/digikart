/*
 * A reusable list panel for one resource level: fetches rows (optionally
 * filtered by a parent), and supports Add / Edit / Delete via a schema-driven
 * modal. Rows can be clickable to drill into children (e.g. category → products).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  FiPlus, FiEdit2, FiTrash2, FiChevronRight, FiEye, FiEyeOff, FiClock, FiCheckCircle,
} from "react-icons/fi";
import { adminApi } from "./adminApi";
import { ResourceForm } from "./ResourceForm";
import { SCHEMAS } from "./schemas";
import { Button } from "../components/ui/Button";
import { Modal } from "../components/ui/Modal";
import { Spinner } from "../components/ui/Spinner";
import { Alert } from "../components/ui/Alert";
import { apiError } from "../lib/api";

// Semantic badge tones (aliases keep older tone names working).
const TONES = {
  brand: "bg-brand-100 text-brand-700 dark:text-brand-300",
  gold: "bg-gold-100 text-gold-700 dark:text-gold-300",
  amber: "bg-gold-100 text-gold-700 dark:text-gold-300",
  teal: "bg-teal-100 text-teal-700 dark:text-teal-300",
  green: "bg-teal-100 text-teal-700 dark:text-teal-300",
  navy: "bg-navy-100 text-navy-600",
  gray: "bg-navy-100 text-navy-600",
  red: "bg-red-100 text-red-700 dark:text-red-300",
};

function Badge({ tone = "brand", children }) {
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${TONES[tone] || TONES.brand}`}>
      {children}
    </span>
  );
}

/* Checkbox that also renders the tri-state "some selected" (indeterminate)
   look, which HTML only exposes via a DOM property (not an attribute). */
function CheckBox({ checked, indeterminate = false, onChange, ariaLabel }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate && !checked;
  }, [indeterminate, checked]);
  return (
    <input
      ref={ref}
      type="checkbox"
      checked={checked}
      onChange={onChange}
      aria-label={ariaLabel}
      className="h-4 w-4 shrink-0 cursor-pointer rounded border-line-strong text-brand-600 focus:ring-2 focus:ring-brand-400"
    />
  );
}

export function CrudPanel({
  title,
  resource,
  params,
  parentDefaults = {},
  onOpen,
  itemLabel = (it) => it.name || it.title,
  renderBadges,
  addLabel,
  refreshToken, // bump to force a reload from a sibling (e.g. playlist import)
  selectable = false, // opt-in multi-select + bulk publish/hide/delete toolbar
  supportsComingSoon = false, // also offer bulk "Coming soon" / "Available"
}) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionError, setActionError] = useState(null); // delete/other action failures
  const [modal, setModal] = useState(null); // null | {mode:'create'} | {mode:'edit', item}
  const [selected, setSelected] = useState(() => new Set()); // selected row ids
  const [bulkBusy, setBulkBusy] = useState(null); // null | "publish" | "hide" | "soon" | "available" | "delete"

  const schema = SCHEMAS[resource];

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setSelected(new Set()); // a fresh list invalidates any prior selection
    try {
      const data = await adminApi.list(resource, params);
      setItems(Array.isArray(data) ? data : data.results || []);
    } catch {
      setError("Could not load. Please retry.");
    } finally {
      setLoading(false);
    }
  }, [resource, JSON.stringify(params), refreshToken]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    load();
  }, [load]);

  // --- Selection + bulk actions ---
  const allIds = items.map((it) => it.id);
  const allSelected = allIds.length > 0 && allIds.every((id) => selected.has(id));
  const someSelected = selected.size > 0 && !allSelected;

  const toggleOne = (id) =>
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const toggleAll = () => setSelected(allSelected ? new Set() : new Set(allIds));
  const clearSelection = () => setSelected(new Set());

  const runBulkUpdate = async (busyKey, fields, failMsg) => {
    setBulkBusy(busyKey);
    setActionError(null);
    try {
      await adminApi.bulkUpdate(resource, [...selected], fields);
      await load(); // reloads (and clears selection) on success
    } catch (e) {
      setActionError(apiError(e, failMsg));
    } finally {
      setBulkBusy(null);
    }
  };

  const handleBulkDelete = async () => {
    const n = selected.size;
    if (
      !window.confirm(
        `Delete ${n} selected ${n === 1 ? "item" : "items"}? Everything inside ` +
          `${n === 1 ? "it" : "them"} is removed too. This cannot be undone.`,
      )
    )
      return;
    setBulkBusy("delete");
    setActionError(null);
    try {
      await adminApi.bulkRemove(resource, [...selected]);
      await load();
    } catch (e) {
      setActionError(apiError(e, "Could not delete the selected items. Please try again."));
    } finally {
      setBulkBusy(null);
    }
  };

  const handleSubmit = async (payload) => {
    if (bulkBusy) return; // don't race a bulk op's reload
    if (modal.mode === "create") {
      await adminApi.create(resource, { ...parentDefaults, ...payload });
    } else {
      await adminApi.update(resource, modal.item.id, payload);
    }
    setModal(null);
    await load();
  };

  const handleDelete = async (item) => {
    if (bulkBusy) return; // don't race a bulk op's reload
    if (!window.confirm(`Delete "${itemLabel(item)}"? This cannot be undone.`)) return;
    setActionError(null);
    try {
      await adminApi.remove(resource, item.id);
      await load();
    } catch (e) {
      setActionError(apiError(e, "Could not delete this item. Please try again."));
    }
  };

  return (
    <section className="rounded-card bg-surface p-5 shadow-card ring-1 ring-line">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-base font-bold text-ink">{title}</h3>
        <Button size="sm" icon={FiPlus} onClick={() => setModal({ mode: "create" })}>
          {addLabel || "Add"}
        </Button>
      </div>

      {actionError && (
        <Alert tone="error" className="mb-3" action={{ label: "Dismiss", onClick: () => setActionError(null) }}>
          {actionError}
        </Alert>
      )}

      {selectable && !loading && !error && items.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-2xl bg-canvas-2/60 px-3 py-2 ring-1 ring-line">
          <label className="flex cursor-pointer items-center gap-2 text-sm font-medium text-ink">
            <CheckBox
              checked={allSelected}
              indeterminate={someSelected}
              onChange={toggleAll}
              ariaLabel={`Select all ${title.toLowerCase()}`}
            />
            {selected.size > 0 ? `${selected.size} selected` : "Select all"}
          </label>

          {selected.size > 0 && (
            <div className="flex flex-1 flex-wrap items-center justify-end gap-2">
              <Button
                size="sm" variant="success" icon={FiEye}
                disabled={!!bulkBusy} loading={bulkBusy === "publish"}
                onClick={() => runBulkUpdate("publish", { is_published: true }, "Could not publish the selected items.")}
              >
                Publish
              </Button>
              <Button
                size="sm" variant="outline" icon={FiEyeOff}
                disabled={!!bulkBusy} loading={bulkBusy === "hide"}
                onClick={() => runBulkUpdate("hide", { is_published: false }, "Could not hide the selected items.")}
              >
                Hide
              </Button>
              {supportsComingSoon && (
                <>
                  <Button
                    size="sm" variant="outline" icon={FiClock}
                    disabled={!!bulkBusy} loading={bulkBusy === "soon"}
                    onClick={() => runBulkUpdate("soon", { is_coming_soon: true }, "Could not update the selected items.")}
                  >
                    Coming soon
                  </Button>
                  <Button
                    size="sm" variant="outline" icon={FiCheckCircle}
                    disabled={!!bulkBusy} loading={bulkBusy === "available"}
                    onClick={() => runBulkUpdate("available", { is_coming_soon: false }, "Could not update the selected items.")}
                  >
                    Available
                  </Button>
                </>
              )}
              <Button
                size="sm" variant="danger" icon={FiTrash2}
                disabled={!!bulkBusy} loading={bulkBusy === "delete"}
                onClick={handleBulkDelete}
              >
                Delete
              </Button>
              <Button size="sm" variant="ghost" disabled={!!bulkBusy} onClick={clearSelection}>
                Clear
              </Button>
            </div>
          )}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-8 text-brand-600 dark:text-brand-300">
          <Spinner />
        </div>
      ) : error ? (
        <Alert tone="error" className="my-2" action={{ label: "Retry", onClick: load }}>
          {error}
        </Alert>
      ) : items.length === 0 ? (
        <p className="py-6 text-center text-sm text-ink-soft">Nothing here yet.</p>
      ) : (
        <ul className="divide-y divide-line">
          {items.map((item) => (
            <li
              key={item.id}
              className={`flex items-center gap-2 py-3 ${selectable && selected.has(item.id) ? "-mx-2 rounded-xl bg-brand-50/60 px-2" : ""}`}
            >
              {selectable && (
                <CheckBox
                  checked={selected.has(item.id)}
                  onChange={() => toggleOne(item.id)}
                  ariaLabel={`Select ${itemLabel(item)}`}
                />
              )}
              <button
                type="button"
                disabled={!onOpen}
                onClick={() => onOpen?.(item)}
                className={`flex-1 text-left ${onOpen ? "group cursor-pointer" : "cursor-default"}`}
              >
                <span className="flex flex-wrap items-center gap-2">
                  <span className={`font-semibold text-ink ${onOpen ? "group-hover:text-brand-700 dark:group-hover:text-brand-300 dark:hover:text-brand-300" : ""}`}>
                    {itemLabel(item)}
                  </span>
                  {renderBadges?.(item, Badge)}
                </span>
              </button>
              <Button variant="ghost" size="sm" icon={FiEdit2} disabled={!!bulkBusy} onClick={() => setModal({ mode: "edit", item })}>
                <span className="hidden sm:inline">Edit</span>
              </Button>
              <Button variant="dangerGhost" size="sm" icon={FiTrash2} disabled={!!bulkBusy} onClick={() => handleDelete(item)}>
                <span className="hidden sm:inline">Delete</span>
              </Button>
              {onOpen && (
                <button onClick={() => onOpen(item)} aria-label="Open" className="px-1 text-navy-300 hover:text-brand-700 dark:hover:text-brand-300">
                  <FiChevronRight className="h-5 w-5" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      <Modal
        open={!!modal}
        onClose={() => setModal(null)}
        title={`${modal?.mode === "edit" ? "Edit" : "Add"} ${title.replace(/s$/, "")}`}
      >
        {modal && (
          <ResourceForm
            fields={schema}
            initial={modal.mode === "edit" ? modal.item : null}
            onSubmit={handleSubmit}
            onCancel={() => setModal(null)}
            submitLabel={modal.mode === "edit" ? "Save changes" : "Create"}
          />
        )}
      </Modal>
    </section>
  );
}

export { Badge };

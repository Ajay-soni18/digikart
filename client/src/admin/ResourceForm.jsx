/*
 * Schema-driven form used by every admin create/edit modal. A `fields` array
 * describes the controls; this renders them, tracks state, and submits.
 *
 * Field shape: { name, label, type, options?, required?, hint?, accept? }
 *   type ∈ text | number | price | textarea | toggle | select | url | file | datetime
 */
import { useState } from "react";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { FileField, Select, Textarea, Toggle } from "../components/ui/fields";
import { Alert } from "../components/ui/Alert";
import { apiError } from "../lib/api";

// A `<input type="datetime-local">` wants "YYYY-MM-DDTHH:MM" in *local* time;
// the API returns ISO 8601 (with a timezone). Convert between the two so editing
// an existing row pre-fills correctly.
function isoToLocalInput(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function initialValues(fields, initial) {
  const v = {};
  for (const f of fields) {
    const has = initial && initial[f.name] !== undefined && initial[f.name] !== null;
    if (f.type === "datetime") {
      v[f.name] = has ? isoToLocalInput(initial[f.name]) : "";
    } else if (has) {
      v[f.name] = initial[f.name];
    } else if (f.type === "toggle") {
      v[f.name] = f.default ?? false;
    } else if (f.type === "file") {
      v[f.name] = null;
    } else if (f.type === "select") {
      // Default to the first option so the value matches what the dropdown shows
      // (otherwise it submits "" and the backend rejects it as an invalid choice).
      v[f.name] = f.options?.[0]?.value ?? "";
    } else {
      v[f.name] = "";
    }
  }
  return v;
}

export function ResourceForm({ fields, initial, onSubmit, submitLabel = "Save", onCancel }) {
  const [values, setValues] = useState(() => initialValues(fields, initial));
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const set = (name, val) => setValues((v) => ({ ...v, [name]: val }));

  const submit = async (e) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const payload = { ...values };
      for (const f of fields) {
        // A field hidden by showIf isn't part of what the admin is describing —
        // sending it anyway means a "free product" still submits a price, and the
        // API rejects the whole save over a field the form deliberately hid.
        if (f.showIf && !f.showIf(values)) {
          delete payload[f.name];
          continue;
        }
        // Drop empty file fields so we don't overwrite an existing file with nothing.
        if (f.type === "file" && !payload[f.name]) delete payload[f.name];
        // An untouched number reads as "", which DRF answers with "A valid number
        // is required." Omit it instead and let the model default apply — blank
        // means "no opinion", not "zero".
        if ((f.type === "number" || f.type === "price") && payload[f.name] === "") {
          delete payload[f.name];
        }
        // A datetime-local value is the admin's *local* wall-clock with no zone.
        // Send a timezone-explicit ISO instant so the server stores the correct
        // absolute time regardless of its own timezone (don't assume browser == server).
        if (f.type === "datetime") {
          payload[f.name] = payload[f.name] ? new Date(payload[f.name]).toISOString() : "";
        }
      }
      await onSubmit(payload);
    } catch (err) {
      setError(apiError(err, "Could not save. Please check the fields."));
    } finally {
      // Reset on BOTH success and failure — otherwise a successful save leaves
      // the button stuck spinning on forms that stay mounted (e.g. Site content).
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-4">
      <Alert tone="error">{error}</Alert>

      {fields.map((f) => {
        // Conditional fields (e.g. a custom price that only applies to one
        // bundle-pricing mode) declare `showIf(values)`; skip when it's false.
        if (f.showIf && !f.showIf(values)) return null;
        const common = { key: f.name, label: f.label, hint: f.hint };
        if (f.type === "toggle") {
          return (
            <Toggle
              {...common}
              checked={!!values[f.name]}
              onChange={(val) => set(f.name, val)}
            />
          );
        }
        if (f.type === "textarea") {
          return (
            <Textarea
              {...common}
              {...(f.rows ? { rows: f.rows } : {})}
              value={values[f.name]}
              onChange={(e) => set(f.name, e.target.value)}
            />
          );
        }
        if (f.type === "select") {
          return (
            <Select
              {...common}
              options={f.options}
              value={values[f.name]}
              onChange={(e) => set(f.name, e.target.value)}
            />
          );
        }
        if (f.type === "file") {
          return (
            <FileField
              {...common}
              accept={f.accept}
              onChange={(file) => set(f.name, file)}
            />
          );
        }
        // text / number / price / url / datetime
        const inputType =
          f.type === "price" || f.type === "number"
            ? "number"
            : f.type === "url"
              ? "url"
              : f.type === "datetime"
                ? "datetime-local"
                : "text";
        return (
          <Input
            {...common}
            type={inputType}
            step={f.type === "price" ? "0.01" : undefined}
            min={f.type === "price" || f.type === "number" ? "0" : undefined}
            required={f.required}
            value={values[f.name]}
            onChange={(e) => set(f.name, e.target.value)}
          />
        );
      })}

      <div className="flex justify-end gap-3 pt-2">
        {onCancel && (
          <Button type="button" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        )}
        <Button type="submit" loading={busy}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}

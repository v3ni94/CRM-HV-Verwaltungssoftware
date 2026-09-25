"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type ChecklistItem = { key: string; label: string; required: boolean; done: boolean };
type ExtraFieldDef = { key: string; label: string; type: string; required: boolean };

/** Checklist and extra fields on the ticket detail page (M19-02). Toggling a checklist item
 *  calls PATCH /tickets/{id}/checklist/{key}; extra field values go through the existing
 *  PATCH /tickets/{id}. A required, still open checklist item or a missing required extra
 *  field blocks the status change to done/closed (422 from the API, shown inline there). */
export function TicketChecklist({
  ticketId,
  checklist,
  extraFieldDefs,
  extraFieldValues,
}: {
  ticketId: string;
  checklist: ChecklistItem[];
  extraFieldDefs: ExtraFieldDef[];
  extraFieldValues: Record<string, unknown>;
}) {
  const t = useTranslations("Tickets");
  const router = useRouter();
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(extraFieldDefs.map((f) => [f.key, String(extraFieldValues[f.key] ?? "")])),
  );
  const [error, setError] = useState<string | null>(null);

  async function toggle(item: ChecklistItem) {
    setBusyKey(item.key);
    setError(null);
    const res = await bff(`/api/bff/tickets/${ticketId}/checklist/${item.key}`, {
      method: "PATCH",
      body: JSON.stringify({ done: !item.done }),
    });
    setBusyKey(null);
    if (res.ok) router.refresh();
    else setError(res.message);
  }

  async function saveField(key: string) {
    setBusyKey(key);
    setError(null);
    const res = await bff(`/api/bff/tickets/${ticketId}`, {
      method: "PATCH",
      body: JSON.stringify({ extra_fields: { [key]: values[key] || null } }),
    });
    setBusyKey(null);
    if (res.ok) router.refresh();
    else setError(res.message);
  }

  if (checklist.length === 0 && extraFieldDefs.length === 0) return null;

  return (
    <section className="flex flex-col gap-3">
      {checklist.length > 0 ? (
        <div className="flex flex-col gap-1">
          <h2 className={ui.h2}>{t("checklist")}</h2>
          <ul className="flex flex-col gap-1">
            {checklist.map((item) => (
              <li key={item.key} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={item.done}
                  disabled={busyKey === item.key}
                  onChange={() => void toggle(item)}
                />
                <span className={item.done ? "text-muted line-through" : undefined}>{item.label}</span>
                {item.required ? <span className="text-xs text-muted">*</span> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {extraFieldDefs.length > 0 ? (
        <div className="flex flex-col gap-2">
          <h2 className={ui.h2}>{t("extraFields")}</h2>
          {extraFieldDefs.map((f) => (
            <label key={f.key} className="flex flex-col gap-1 sm:max-w-xs">
              <span className={ui.label}>
                {f.label}
                {f.required ? " *" : ""}
              </span>
              <div className="flex gap-2">
                <input
                  className={ui.input}
                  type={f.type === "date" ? "date" : f.type === "number" ? "number" : "text"}
                  value={values[f.key] ?? ""}
                  onChange={(e) => setValues((prev) => ({ ...prev, [f.key]: e.target.value }))}
                />
                <button type="button" className={ui.buttonSm} disabled={busyKey === f.key} onClick={() => void saveField(f.key)}>
                  {t("saveField")}
                </button>
              </div>
            </label>
          ))}
        </div>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}

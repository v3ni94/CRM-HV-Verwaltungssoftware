"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { today as businessToday } from "@/lib/today";
import { ui } from "@/lib/ui";

/** Event after a write off was requested; the WriteOffPanel reloads its list. */
export const WRITE_OFF_REQUESTED = "mhvp:write-off-requested";

/** AP12 (GAL-302): Aktion "Ausbuchung beantragen" am offenen Posten (Kontenblatt, Mahnfall).
 *  Legt nur einen Vorschlag ohne Wirkung an (Grund, Stichtag); Freigabe durch eine zweite
 *  Person, Gate G1 und Freigabe der Geschäftsführung bleiben vorbehalten. */
export function WriteOffRequestButton({ openItemId, today }: { openItemId: string; today?: string }) {
  const t = useTranslations("WriteOffs");
  const day = today ?? businessToday();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ effective_on: day, reason: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const valid = form.reason.trim().length >= 10 && form.effective_on !== "" && form.effective_on <= day;

  const submit = async () => {
    if (busy || !valid) return;
    setBusy(true);
    setError(null);
    const res = await bff("/api/bff/accounting/open-item-write-offs", {
      method: "POST",
      body: JSON.stringify({ open_item_id: openItemId, effective_on: form.effective_on, reason: form.reason.trim() }),
    });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setDone(true);
    setOpen(false);
    window.dispatchEvent(new CustomEvent(WRITE_OFF_REQUESTED, { detail: { openItemId } }));
  };

  if (done) return <span className="text-xs text-muted" data-testid={`write-off-requested-${openItemId}`}>{t("requested")}</span>;
  if (!open)
    return (
      <button type="button" className={ui.buttonSm} onClick={() => setOpen(true)} data-testid={`write-off-request-${openItemId}`}>
        {t("request")}
      </button>
    );
  return (
    <div className="flex flex-col gap-1 rounded border border-border p-2 text-sm" data-testid={`write-off-request-form-${openItemId}`}>
      <p className={ui.help}>{t("requestHint")}</p>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("effectiveOn")}</span>
        <input type="date" className={ui.input} max={day} value={form.effective_on} onChange={(e) => setForm((f) => ({ ...f, effective_on: e.target.value }))} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("reason")}</span>
        <input className={ui.input} minLength={10} maxLength={500} value={form.reason} onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))} />
      </label>
      <div className="flex gap-2">
        <button type="button" className={ui.buttonSm} disabled={!valid || busy} aria-busy={busy} onClick={() => void submit()}>
          {t("requestSubmit")}
        </button>
        <button type="button" className={ui.buttonSm} onClick={() => setOpen(false)}>
          {t("cancel")}
        </button>
      </div>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </div>
  );
}

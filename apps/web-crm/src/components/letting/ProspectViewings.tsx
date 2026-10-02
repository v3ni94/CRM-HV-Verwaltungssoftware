"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

type Viewing = { id: string; scheduled_at: string; status: string; location: string | null; note: string | null };
const STATUSES = ["proposed", "confirmed", "done", "cancelled", "no_show"] as const;

/** Besichtigungstermine je Interessent (GAF-17): laden, anlegen, Status ändern. Nur Terminpflege,
 *  keine Einladung und kein Versand. */
export function ProspectViewings({ prospectId }: { prospectId: string }) {
  const t = useTranslations("Af20.viewings");
  const [rows, setRows] = useState<Viewing[] | null>(null);
  const [when, setWhen] = useState("");
  const [location, setLocation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const base = `/api/bff/letting/prospects/${prospectId}/viewings`;
  const load = async () => {
    const res = await bff<Viewing[]>(base);
    if (res.ok) setRows(res.data);
    else setError(res.message);
  };
  const add = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<Viewing>(base, {
      method: "POST",
      body: JSON.stringify({ scheduled_at: new Date(when).toISOString(), location: location.trim() || null }),
    });
    setBusy(false);
    if (res.ok) {
      setWhen("");
      setLocation("");
      await load();
    } else setError(res.message);
  };
  const setStatus = async (id: string, status: string) => {
    setBusy(true);
    setError(null);
    const res = await bff<Viewing>(`/api/bff/letting/prospects/viewings/${id}`, { method: "PATCH", body: JSON.stringify({ status }) });
    setBusy(false);
    if (res.ok) await load();
    else setError(res.message);
  };
  if (rows === null) {
    return (
      <div className="flex flex-col gap-1">
        <button type="button" className={ui.buttonSm} onClick={() => void load()}>
          {t("show")}
        </button>
        {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2" data-testid="viewings">
      <h3 className="text-xs font-semibold">{t("title")}</h3>
      {rows.length === 0 ? <p className="text-xs text-muted">{t("empty")}</p> : null}
      <ul className="flex flex-col gap-1 text-xs">
        {rows.map((v) => (
          <li key={v.id} className="flex flex-wrap items-center gap-2">
            <span>{formatDate(v.scheduled_at)} {new Date(v.scheduled_at).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })}</span>
            {v.location ? <span className="text-muted">{v.location}</span> : null}
            <select aria-label={t("status")} className={ui.input} value={v.status} disabled={busy} onChange={(e) => void setStatus(v.id, e.target.value)}>
              {STATUSES.map((s) => (
                <option key={s} value={s}>{t(`statuses.${s}`)}</option>
              ))}
            </select>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("when")}</span>
          <input type="datetime-local" className={ui.input} value={when} onChange={(e) => setWhen(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("location")}</span>
          <input className={ui.input} value={location} onChange={(e) => setLocation(e.target.value)} />
        </label>
        <button type="button" className={ui.button} disabled={busy || !when} onClick={() => void add()}>
          {t("add")}
        </button>
      </div>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </div>
  );
}

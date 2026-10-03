"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** ISO-Datum als TT.MM.JJJJ. */
function formatDate(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}.${m}.${y}`;
}

const KINDS = ["statement", "receipts", "contracts", "resolutions"] as const;
const STATUSES = ["requested", "released", "provided", "retrieved", "closed", "rejected"];

type Inspection = {
  id: string;
  legal_entity_id: string;
  requested_on: string;
  scope_kinds: string[];
  scope_text: string | null;
  status: string;
  steps: { to_status: string | null; occurred_at: string }[];
};
type InspectionList = {
  enabled: boolean;
  note: string;
  items: Inspection[];
  communities?: { id: string; name: string }[];
};

/** AM06 (GAJ-202, Abschnitt 7.9.3 PÜ10, PÜ12, PÜ13): Einsichtsanfrage des Eigentümers mit
 *  Stand. Die Anfrage geht in den bestehenden Prozess der Verwaltung; Freigabe und
 *  Bereitstellung bleiben dort. Nur sichtbar, wenn die Verwaltung den Schalter der
 *  Belegeinsicht (AG09) eingeschaltet hat. */
export function OwnerInspectionPanel() {
  const t = useTranslations("OwnerInspection");
  const [data, setData] = useState<InspectionList | null>(null);
  const [entity, setEntity] = useState("");
  const [kinds, setKinds] = useState<string[]>([]);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const result = await bff<InspectionList>("/api/bff/portal/owner/inspection-requests");
    if (result.ok) {
      setData(result.data);
      const first = result.data.communities?.[0]?.id;
      if (first) setEntity((prev) => prev || first);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (!data || !data.enabled) return null;
  const communities = data.communities ?? [];

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setDone(false);
    if (kinds.length === 0 && !text.trim()) {
      setError(t("scopeRequired"));
      return;
    }
    setBusy(true);
    const result = await bff("/api/bff/portal/owner/inspection-requests", {
      method: "POST",
      body: JSON.stringify({ legal_entity_id: entity, scope_kinds: kinds, ...(text.trim() ? { scope_text: text.trim() } : {}) }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setDone(true);
    setKinds([]);
    setText("");
    await load();
  }

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="owner-inspection-title">
      <h2 id="owner-inspection-title" className={ui.label}>
        {t("title")}
      </h2>
      <p className={ui.help}>{t("intro")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {done ? <p className={ui.success}>{t("submitted")}</p> : null}
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-2">
        {communities.length > 1 ? (
          <label className="flex flex-col gap-1 text-sm">
            {t("community")}
            <select value={entity} onChange={(e) => setEntity(e.target.value)} className={ui.input}>
              {communities.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <fieldset className="flex flex-wrap gap-3 text-sm">
          <legend className={ui.label}>{t("scope")}</legend>
          {KINDS.map((k) => (
            <label key={k} className="flex items-center gap-1">
              <input
                type="checkbox"
                checked={kinds.includes(k)}
                onChange={(e) => setKinds((prev) => (e.target.checked ? [...prev, k] : prev.filter((x) => x !== k)))}
              />
              {t(`kinds.${k}`)}
            </label>
          ))}
        </fieldset>
        <label className="flex flex-col gap-1 text-sm">
          {t("scopeText")}
          <textarea rows={3} maxLength={4000} className={ui.input} value={text} onChange={(e) => setText(e.target.value)} />
        </label>
        <div className={ui.formActions}>
          <button type="submit" className={ui.primary} disabled={busy || !entity}>
            {t("submit")}
          </button>
        </div>
      </form>
      {data.note ? <p className="text-xs text-subtle">{data.note}</p> : null}
      {data.items.length > 0 ? (
        <div>
          <h3 className={ui.label}>{t("list")}</h3>
          <ul className="flex flex-col gap-1 text-sm">
            {data.items.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center gap-2">
                <span>{t("requestedOn", { date: formatDate(i.requested_on) })}</span>
                <span className={ui.badge}>{STATUSES.includes(i.status) ? t(`status.${i.status}`) : i.status}</span>
                <span className="text-muted">
                  {i.scope_kinds.map((k) => ((KINDS as readonly string[]).includes(k) ? t(`kinds.${k}`) : k)).join(", ")}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

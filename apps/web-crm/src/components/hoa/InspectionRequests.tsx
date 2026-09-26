"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export const SCOPE_KINDS = ["statement", "receipts", "contracts", "resolutions"] as const;

/** Record an inspection request outside the portal (A61): applicant, date, scope. */
export function InspectionRequestCreate({ legalEntityId, basePath }: { legalEntityId: string; basePath: string }) {
  const t = useTranslations("HoaInspection");
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<{ id: string; display_name: string }[]>([]);
  const [contact, setContact] = useState<{ id: string; display_name: string } | null>(null);
  const [requestedOn, setRequestedOn] = useState("");
  const [kinds, setKinds] = useState<string[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dateValid = /^\d{4}-\d{2}-\d{2}$/.test(requestedOn);
  const scopeValid = kinds.length > 0 || text.trim().length > 0;
  const valid = contact !== null && dateValid && scopeValid;
  const hint = contact === null ? t("chooseApplicant") : !dateValid ? t("dateRequired") : !scopeValid ? t("scopeRequired") : null;

  const search = async (q: string) => {
    setQuery(q);
    setContact(null);
    if (q.trim().length < 2) {
      setHits([]);
      return;
    }
    const res = await bff<{ items: { id: string; display_name: string }[] }>(`/api/bff/contacts?q=${encodeURIComponent(q.trim())}&page_size=8`);
    setHits(res.ok ? res.data.items : []);
  };
  const toggle = (kind: string) => setKinds((prev) => (prev.includes(kind) ? prev.filter((k) => k !== kind) : [...prev, kind]));
  const create = async () => {
    if (!contact) return;
    setBusy(true);
    setError(null);
    const res = await bff<{ id: string }>("/api/bff/hoa/inspection-requests", {
      method: "POST",
      body: JSON.stringify({
        legal_entity_id: legalEntityId,
        applicant_contact_id: contact.id,
        requested_on: requestedOn,
        scope_kinds: kinds,
        scope_text: text.trim() || null,
      }),
    });
    setBusy(false);
    if (res.ok) router.push(`${basePath}/einsicht/${res.data.id}`);
    else setError(res.message);
  };
  return (
    <div className="flex flex-col gap-2" data-testid="inspection-create">
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("applicant")}</span>
          <input className={ui.input} value={contact ? contact.display_name : query} onChange={(e) => search(e.target.value)} placeholder={t("applicantSearch")} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("requestedOn")}</span>
          <input className={ui.input} type="date" value={requestedOn} onChange={(e) => setRequestedOn(e.target.value)} />
        </label>
        <button type="button" className={ui.primary} onClick={create} disabled={busy || !valid}>
          {t("create")}
        </button>
      </div>
      {hint ? <p className={ui.help}>{hint}</p> : null}
      {!contact && hits.length > 0 ? (
        <ul className="flex flex-wrap gap-2 text-sm">
          {hits.map((h) => (
            <li key={h.id}>
              <button type="button" className={ui.buttonSm} onClick={() => setContact(h)}>
                {h.display_name}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <fieldset className="flex flex-wrap gap-3 text-sm">
        <legend className={ui.label}>{t("scope")}</legend>
        {SCOPE_KINDS.map((kind) => (
          <label key={kind} className="flex items-center gap-1">
            <input type="checkbox" checked={kinds.includes(kind)} onChange={() => toggle(kind)} /> {t(`scopeKinds.${kind}`)}
          </label>
        ))}
      </fieldset>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("scopeText")}</span>
        <textarea className={ui.input} rows={2} value={text} onChange={(e) => setText(e.target.value)} />
      </label>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </div>
  );
}

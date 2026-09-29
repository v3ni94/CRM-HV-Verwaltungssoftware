"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type RetentionProfile = {
  id: string;
  document_class: string;
  legal_entity_kind: string | null;
  legal_basis: string;
  retention_years: number;
  retention_months: number;
  permanent: boolean;
  start_rule: string;
  review_note: string | null;
  status: string;
  created_by: string | null;
  released_at: string | null;
  released_by: string | null;
};

export type DocumentCategory = {
  id: string;
  code: string;
  name: string;
  retention_profile_id: string | null;
};

const START_RULES = ["end_of_year_created", "end_of_year_last_entry", "contract_end", "statement_issued", "purpose_end"] as const;

type Draft = { retention_years: string; retention_months: string; permanent: boolean; start_rule: string; legal_basis: string };

function draftOf(p: RetentionProfile): Draft {
  return {
    retention_years: String(p.retention_years),
    retention_months: String(p.retention_months),
    permanent: p.permanent,
    start_rule: p.start_rule,
    legal_basis: p.legal_basis,
  };
}

/** Aufbewahrungsprofile (M6-04): Frist, Beginn und Rechtsgrundlage je Unterlagenklasse
 *  bearbeiten (macht ein freigegebenes Profil wieder zum Entwurf), Freigabe durch eine zweite
 *  Person, Zuordnung der Dokumentkategorien zu einem Profil und Anwendung auf den Bestand. */
export function RetentionSettings({
  profiles: initialProfiles,
  categories: initialCategories,
  userId,
}: {
  profiles: RetentionProfile[];
  categories: DocumentCategory[];
  userId: string | null;
}) {
  const t = useTranslations("RetentionSettings");
  const [profiles, setProfiles] = useState(initialProfiles);
  const [categories, setCategories] = useState(initialCategories);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const className = (code: string) => (t.has(`classes.${code}`) ? t(`classes.${code}`) : code);
  const ruleName = (rule: string) => (t.has(`rules.${rule}`) ? t(`rules.${rule}`) : rule);
  const period = (p: RetentionProfile) =>
    p.permanent ? t("permanent") : t("period", { years: p.retention_years, months: p.retention_months });

  const replaceProfile = (next: RetentionProfile) => setProfiles((list) => list.map((p) => (p.id === next.id ? next : p)));

  const startEdit = (p: RetentionProfile) => {
    setEditing(p.id);
    setDraft(draftOf(p));
    setMessage(null);
    setError(null);
  };

  const save = async (id: string) => {
    if (!draft) return;
    setBusy(true);
    setError(null);
    const res = await bff<RetentionProfile>(`/api/bff/retention-profiles/${id}`, {
      method: "PATCH",
      body: JSON.stringify({
        retention_years: Number.parseInt(draft.retention_years, 10) || 0,
        retention_months: Number.parseInt(draft.retention_months, 10) || 0,
        permanent: draft.permanent,
        start_rule: draft.start_rule,
        legal_basis: draft.legal_basis,
      }),
    });
    setBusy(false);
    if (res.ok) {
      replaceProfile(res.data);
      setEditing(null);
      setDraft(null);
      setMessage(t("savedDraft"));
    } else setError(res.message);
  };

  const release = async (id: string) => {
    setBusy(true);
    setError(null);
    setMessage(null);
    const res = await bff<RetentionProfile>(`/api/bff/retention-profiles/${id}/release`, { method: "POST" });
    setBusy(false);
    if (res.ok) {
      replaceProfile(res.data);
      setMessage(t("released"));
    } else setError(res.message);
  };

  const map = async (category: DocumentCategory, profileId: string) => {
    setBusy(true);
    setError(null);
    setMessage(null);
    const res = await bff<DocumentCategory>(`/api/bff/document-categories/${category.id}`, {
      method: "PATCH",
      body: JSON.stringify({ retention_profile_id: profileId || null }),
    });
    setBusy(false);
    if (res.ok) {
      setCategories((list) => list.map((c) => (c.id === res.data.id ? res.data : c)));
      setMessage(t("mapped"));
    } else setError(res.message);
  };

  const apply = async () => {
    setBusy(true);
    setError(null);
    setMessage(null);
    const res = await bff<{ assigned: number }>("/api/bff/retention-profiles/apply", { method: "POST" });
    setBusy(false);
    if (res.ok) setMessage(t("applied", { count: res.data.assigned }));
    else setError(res.message);
  };

  return (
    <div className="flex flex-col gap-4">
      <p className={ui.warning}>{t("legalNotice")}</p>
      {message ? <p className={ui.success}>{message}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <section className={`${ui.card} overflow-x-auto p-0`}>
        <table className={ui.table} data-testid="retention-profiles">
          <thead>
            <tr>
              <th>{t("colClass")}</th>
              <th>{t("colPeriod")}</th>
              <th>{t("colStart")}</th>
              <th>{t("colBasis")}</th>
              <th>{t("colStatus")}</th>
              <th>{t("colActions")}</th>
            </tr>
          </thead>
          <tbody>
            {profiles.map((p) => {
              const isEditing = editing === p.id && draft;
              const canRelease = p.status !== "freigegeben" && userId !== null && p.created_by !== userId;
              return (
                <tr key={p.id}>
                  <td>
                    <div className="font-medium">{className(p.document_class)}</div>
                    <div className={ui.small}>{p.document_class}</div>
                  </td>
                  <td>
                    {isEditing ? (
                      <div className="flex flex-col gap-1">
                        <label className="flex items-center gap-1 text-xs">
                          <input
                            type="checkbox"
                            checked={draft.permanent}
                            onChange={(e) => setDraft({ ...draft, permanent: e.target.checked })}
                          />
                          {t("permanent")}
                        </label>
                        <div className="flex gap-1">
                          <input
                            className={`${ui.input} w-16`}
                            type="number"
                            min={0}
                            max={100}
                            aria-label={t("years")}
                            value={draft.retention_years}
                            disabled={draft.permanent}
                            onChange={(e) => setDraft({ ...draft, retention_years: e.target.value })}
                          />
                          <input
                            className={`${ui.input} w-16`}
                            type="number"
                            min={0}
                            max={11}
                            aria-label={t("months")}
                            value={draft.retention_months}
                            disabled={draft.permanent}
                            onChange={(e) => setDraft({ ...draft, retention_months: e.target.value })}
                          />
                        </div>
                      </div>
                    ) : (
                      period(p)
                    )}
                  </td>
                  <td>
                    {isEditing ? (
                      <select
                        className={ui.input}
                        value={draft.start_rule}
                        aria-label={t("colStart")}
                        onChange={(e) => setDraft({ ...draft, start_rule: e.target.value })}
                      >
                        {START_RULES.map((r) => (
                          <option key={r} value={r}>
                            {ruleName(r)}
                          </option>
                        ))}
                      </select>
                    ) : (
                      ruleName(p.start_rule)
                    )}
                  </td>
                  <td className="max-w-xs">
                    {isEditing ? (
                      <textarea
                        className={ui.input}
                        rows={3}
                        aria-label={t("colBasis")}
                        value={draft.legal_basis}
                        onChange={(e) => setDraft({ ...draft, legal_basis: e.target.value })}
                      />
                    ) : (
                      <span className="text-xs">{p.legal_basis}</span>
                    )}
                  </td>
                  <td>
                    {p.status === "freigegeben" ? (
                      <span className={ui.badgeSuccess}>{t("statusReleased")}</span>
                    ) : (
                      <span className={ui.badgeWarning}>{t("statusDraft")}</span>
                    )}
                    {p.review_note ? <div className={ui.small}>{p.review_note}</div> : null}
                    {p.released_at ? <div className={ui.small}>{formatDateTime(p.released_at)}</div> : null}
                  </td>
                  <td>
                    <div className="flex flex-wrap gap-1">
                      {isEditing ? (
                        <>
                          <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void save(p.id)}>
                            {t("save")}
                          </button>
                          <button
                            type="button"
                            className={ui.buttonSm}
                            disabled={busy}
                            onClick={() => {
                              setEditing(null);
                              setDraft(null);
                            }}
                          >
                            {t("cancel")}
                          </button>
                        </>
                      ) : (
                        <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => startEdit(p)}>
                          {t("edit")}
                        </button>
                      )}
                      {p.status !== "freigegeben" ? (
                        <button
                          type="button"
                          className={ui.buttonSm}
                          disabled={busy || !canRelease}
                          title={canRelease ? undefined : t("fourEyesHint")}
                          onClick={() => void release(p.id)}
                        >
                          {t("release")}
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
      <section className={`${ui.card} flex flex-col gap-3`}>
        <h2 id="retention-mapping-title" className="text-sm font-semibold">{t("mappingTitle")}</h2>
        <p className={ui.help}>{t("mappingHint")}</p>
        <div className={ui.tableScroll}>
          <table className={ui.table} data-testid="retention-mapping">
            <thead>
              <tr>
                <th>{t("colCategory")}</th>
                <th>{t("colProfile")}</th>
              </tr>
            </thead>
            <tbody>
              {categories.map((c) => (
                <tr key={c.id}>
                  <td>
                    {c.name} <span className={ui.small}>{c.code}</span>
                  </td>
                  <td>
                    <select
                      className={ui.input}
                      aria-label={t("colProfile")}
                      value={c.retention_profile_id ?? ""}
                      disabled={busy}
                      onChange={(e) => void map(c, e.target.value)}
                    >
                      <option value="">{t("noProfile")}</option>
                      {profiles.map((p) => (
                        <option key={p.id} value={p.id}>
                          {className(p.document_class)} ({period(p)})
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          <button type="button" className={ui.secondary} disabled={busy} onClick={() => void apply()}>
            {t("apply")}
          </button>
          <p className={ui.help}>{t("applyHint")}</p>
        </div>
      </section>
    </div>
  );
}

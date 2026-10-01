"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type RegisterEntryFull = {
  id: string;
  kind: string;
  name: string;
  role: string | null;
  purpose: string | null;
  data_categories: string[];
  data_subjects: string[];
  recipients: string | null;
  third_country: boolean;
  third_country_status: string;
  third_country_countries: string | null;
  third_country_note: string | null;
  avv_status: string;
  avv_confirmed_on: string | null;
  avv_document_id: string | null;
  retention_note: string | null;
  legal_review_status: string;
  legal_reviewed_on: string | null;
  active: boolean;
  legal_basis: string | null;
  responsibilities: Record<string, string>;
  responsibility_note: string | null;
  processor_ids: string[];
  source_key: string | null;
  source_detail: string | null;
};

export const ACTORS = ["gdwe", "verwalter", "betreiber"] as const;
export const ROLES = ["open", "controller", "joint_controller", "processor", "not_involved"] as const;
const THIRD = ["open", "no", "yes"] as const;
const AVV = ["none", "requested", "confirmed", "not_required"] as const;

const list = (value: string) =>
  value
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean);
const orNull = (value: string) => value.trim() || null;

/**
 * Pflege eines Registereintrags (S711-10, AE32): Rollen von GdWE, Verwalter und Betreiber je
 * Verarbeitungstätigkeit, Rechtsgrundlage, eingesetzte Auftragsverarbeiter, Drittland je
 * Anbieter. Alle rechtlichen Felder sind Eingaben des Betreibers und starten mit "offen"; die
 * Oberfläche schlägt keine Rechtsgrundlage und keine Rolle vor. Das Backend prüft Recht und
 * Zuordnung (422 bei unbekanntem Auftragsverarbeiter).
 */
export function PrivacyRegisterEditor({
  entry,
  processors,
  onSaved,
  onCancel,
}: {
  entry: RegisterEntryFull;
  processors: { id: string; name: string }[];
  onSaved: () => void | Promise<void>;
  onCancel: () => void;
}) {
  const t = useTranslations("PrivacyRegister");
  const tk = useTranslations("PrivacyAdmin");
  const activity = entry.kind === "processing_activity";
  const [f, setF] = useState({
    name: entry.name,
    purpose: entry.purpose ?? "",
    avv_status: entry.avv_status,
    avv_confirmed_on: entry.avv_confirmed_on ?? "",
    third_country_status: entry.third_country_status || "open",
    third_country_countries: entry.third_country_countries ?? "",
    third_country_note: entry.third_country_note ?? "",
    legal_review_status: entry.legal_review_status,
    legal_reviewed_on: entry.legal_reviewed_on ?? "",
    active: entry.active,
    legal_basis: entry.legal_basis ?? "",
    responsibility_note: entry.responsibility_note ?? "",
    data_categories: entry.data_categories.join(", "),
    data_subjects: entry.data_subjects.join(", "),
    recipients: entry.recipients ?? "",
    retention_note: entry.retention_note ?? "",
  });
  const [roles, setRoles] = useState<Record<string, string>>(() =>
    Object.fromEntries(ACTORS.map((a) => [a, entry.responsibilities?.[a] ?? "open"])),
  );
  const [pids, setPids] = useState<string[]>(entry.processor_ids ?? []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!f.name.trim()) return;
    setBusy(true);
    setError(null);
    const body = {
      kind: entry.kind,
      name: f.name.trim(),
      role: entry.role,
      purpose: orNull(f.purpose),
      data_categories: list(f.data_categories),
      data_subjects: list(f.data_subjects),
      recipients: orNull(f.recipients),
      third_country: f.third_country_status === "yes",
      third_country_status: f.third_country_status,
      third_country_countries: f.third_country_status === "yes" ? orNull(f.third_country_countries) : null,
      third_country_note: orNull(f.third_country_note),
      avv_status: f.avv_status,
      avv_confirmed_on: f.avv_confirmed_on || null,
      avv_document_id: entry.avv_document_id,
      retention_note: orNull(f.retention_note),
      legal_review_status: f.legal_review_status,
      legal_reviewed_on: f.legal_review_status === "reviewed" ? f.legal_reviewed_on || null : null,
      active: f.active,
      legal_basis: activity ? orNull(f.legal_basis) : null,
      responsibilities: activity ? Object.fromEntries(Object.entries(roles).filter(([, r]) => r !== "open")) : {},
      responsibility_note: activity ? orNull(f.responsibility_note) : null,
      processor_ids: activity ? pids : [],
    };
    const res = await bff(`/api/bff/privacy/register/${entry.id}`, { method: "PUT", body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    await onSaved();
  }

  const field = (key: keyof typeof f, label: string, opts: { area?: boolean; hint?: string; wide?: boolean } = {}) => (
    <div className={`flex flex-col gap-1 ${opts.wide ? "sm:col-span-2" : ""}`}>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{label}</span>
        {opts.area ? (
          <textarea className={ui.input} rows={2} value={String(f[key])} onChange={(e) => setF({ ...f, [key]: e.target.value })} />
        ) : (
          <input className={ui.input} value={String(f[key])} onChange={(e) => setF({ ...f, [key]: e.target.value })} />
        )}
      </label>
      {opts.hint ? <span className={ui.help}>{opts.hint}</span> : null}
    </div>
  );

  return (
    <form className={`${ui.card} grid gap-3 sm:grid-cols-2`} onSubmit={(e) => void save(e)} aria-label={t("editor.title")} data-testid="privacy-register-editor">
      <div className="flex flex-col gap-1 sm:col-span-2">
        <h3 className={ui.title}>
          {t("editor.title")}: {entry.name} ({tk(`kind.${entry.kind}`)})
        </h3>
        <p className={ui.help}>{t("editor.maintenanceHint")}</p>
        {entry.source_key ? (
          <p className={ui.notice} data-testid="privacy-register-origin">
            {t("editor.originConfig")} {entry.source_detail}
          </p>
        ) : null}
      </div>
      {error ? (
        <p role="alert" className={`${ui.alert} sm:col-span-2`}>
          {error}
        </p>
      ) : null}
      {field("name", t("editor.name"))}
      {field("purpose", t("editor.purpose"))}

      {activity ? (
        <fieldset className="flex flex-col gap-2 sm:col-span-2">
          <legend className={ui.label}>{t("editor.responsibilities")}</legend>
          <p className={ui.help}>{t("editor.responsibilitiesHint")}</p>
          <div className="grid gap-3 sm:grid-cols-3">
            {ACTORS.map((a) => (
              <label key={a} className="flex flex-col gap-1">
                <span className={ui.label}>{t(`actor.${a}`)}</span>
                <select className={ui.input} value={roles[a]} onChange={(e) => setRoles({ ...roles, [a]: e.target.value })}>
                  {ROLES.map((r) => (
                    <option key={r} value={r}>
                      {t(`role.${r}`)}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>
        </fieldset>
      ) : null}
      {activity ? field("responsibility_note", t("editor.responsibilityNote"), { area: true, wide: true }) : null}
      {activity ? field("legal_basis", t("editor.legalBasis"), { area: true, wide: true, hint: t("editor.legalBasisHint") }) : null}
      {activity ? (
        <fieldset className="flex flex-col gap-1 sm:col-span-2">
          <legend className={ui.label}>{t("editor.processors")}</legend>
          {processors.length === 0 ? (
            <p className={ui.help}>{t("editor.noProcessors")}</p>
          ) : (
            processors.map((p) => (
              <label key={p.id} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={pids.includes(p.id)}
                  onChange={(e) => setPids(e.target.checked ? [...pids, p.id] : pids.filter((id) => id !== p.id))}
                />
                {p.name}
              </label>
            ))
          )}
        </fieldset>
      ) : null}
      {activity ? field("data_categories", t("editor.dataCategories"), { hint: t("editor.listHint") }) : null}
      {activity ? field("data_subjects", t("editor.dataSubjects"), { hint: t("editor.listHint") }) : null}
      {activity ? field("recipients", t("editor.recipients")) : null}
      {activity ? field("retention_note", t("editor.retention")) : null}

      {!activity ? (
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("editor.avv")}</span>
          <select className={ui.input} value={f.avv_status} onChange={(e) => setF({ ...f, avv_status: e.target.value })}>
            {AVV.map((a) => (
              <option key={a} value={a}>
                {tk(`avv.${a}`)}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {!activity ? (
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("editor.avvConfirmedOn")}</span>
          <input type="date" className={ui.input} value={f.avv_confirmed_on} onChange={(e) => setF({ ...f, avv_confirmed_on: e.target.value })} />
        </label>
      ) : null}

      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("editor.thirdCountry")}</span>
        <select className={ui.input} value={f.third_country_status} onChange={(e) => setF({ ...f, third_country_status: e.target.value })}>
          {THIRD.map((s) => (
            <option key={s} value={s}>
              {t(`thirdCountry.${s}`)}
            </option>
          ))}
        </select>
      </label>
      {f.third_country_status === "yes" ? field("third_country_countries", t("editor.thirdCountryCountries")) : <div className="hidden sm:block" />}
      {field("third_country_note", t("editor.thirdCountryNote"), { area: true, wide: true, hint: t("editor.thirdCountryHint") })}

      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("editor.review")}</span>
        <select className={ui.input} value={f.legal_review_status} onChange={(e) => setF({ ...f, legal_review_status: e.target.value })}>
          <option value="open">{t("review.open")}</option>
          <option value="reviewed">{t("review.reviewed")}</option>
        </select>
      </label>
      {f.legal_review_status === "reviewed" ? (
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("editor.reviewedOn")}</span>
          <input type="date" className={ui.input} value={f.legal_reviewed_on} onChange={(e) => setF({ ...f, legal_reviewed_on: e.target.value })} />
        </label>
      ) : (
        <div className="hidden sm:block" />
      )}
      <label className="flex items-center gap-2 text-sm sm:col-span-2">
        <input type="checkbox" checked={f.active} onChange={(e) => setF({ ...f, active: e.target.checked })} />
        {t("editor.active")}
      </label>
      <div className={`${ui.formActions} sm:col-span-2`}>
        <button type="submit" className={ui.primary} disabled={busy}>
          {t("editor.save")}
        </button>
        <button type="button" className={ui.button} onClick={onCancel} disabled={busy}>
          {t("editor.cancel")}
        </button>
      </div>
    </form>
  );
}

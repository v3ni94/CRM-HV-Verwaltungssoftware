"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type AccessExportSettingsData = {
  third_party_scope: "none" | "names";
  include_internal_notes: boolean;
  include_tickets?: boolean;
  include_communication?: boolean;
  include_documents?: boolean;
  include_portal_account?: boolean;
  include_payments?: boolean;
  include_contracts?: boolean;
};
type SourceKey =
  | "include_tickets"
  | "include_communication"
  | "include_documents"
  | "include_portal_account"
  | "include_payments"
  | "include_contracts";
const SOURCE_KEYS: SourceKey[] = [
  "include_tickets",
  "include_communication",
  "include_documents",
  // AK06 (GAI-506): portal account, payment and contract data, off by default.
  "include_portal_account",
  "include_payments",
  "include_contracts",
];

/** Umfang der DSGVO-Auskunft je Mandant (AE33, AC07-01). Standard: andere Personen nur mit
 *  Rolle, interne Vermerke zurückgehalten. Die Rechtsfrage ist offen; der Umfang wird beim
 *  Vorbereiten einer Auskunft festgehalten und gilt dann unverändert bis zur Freigabe. */
export function AccessExportSettings({ initial, canEdit }: { initial: AccessExportSettingsData; canEdit: boolean }) {
  const t = useTranslations("AccessExportSettings");
  const [scope, setScope] = useState(initial.third_party_scope);
  const [notes, setNotes] = useState(initial.include_internal_notes);
  // GAI-506: further data sources, off by default (AC07-01).
  const [sources, setSources] = useState<Record<SourceKey, boolean>>({
    include_tickets: initial.include_tickets ?? false,
    include_communication: initial.include_communication ?? false,
    include_documents: initial.include_documents ?? false,
    include_portal_account: initial.include_portal_account ?? false,
    include_payments: initial.include_payments ?? false,
    include_contracts: initial.include_contracts ?? false,
  });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setMessage(null);
    setError(null);
    const result = await bff<AccessExportSettingsData>("/api/bff/contact-access-export-settings", {
      method: "PUT",
      body: JSON.stringify({ third_party_scope: scope, include_internal_notes: notes, ...sources }),
    });
    setBusy(false);
    if (result.ok) setMessage(t("saved"));
    else setError(result.message);
  }

  return (
    <section aria-labelledby="access-export-settings-title" className={`${ui.card} max-w-2xl`}>
      <h2 id="access-export-settings-title" className="mb-1 text-base font-semibold">
        {t("title")}
      </h2>
      <p className="mb-3 text-sm">{t("hint")}</p>
      <div className="flex flex-col gap-3">
        <div className="max-w-md">
          <label className={ui.label} htmlFor="access-export-scope">
            {t("scope")}
          </label>
          <select
            id="access-export-scope"
            className={ui.input}
            value={scope}
            disabled={!canEdit || busy}
            onChange={(e) => setScope(e.target.value as "none" | "names")}
          >
            <option value="none">{t("scopeNone")}</option>
            <option value="names">{t("scopeNames")}</option>
          </select>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={notes} disabled={!canEdit || busy} onChange={(e) => setNotes(e.target.checked)} />
          {t("notes")}
        </label>
        {SOURCE_KEYS.map((key) => (
          <label key={key} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={sources[key]}
              disabled={!canEdit || busy}
              onChange={(e) => setSources((prev) => ({ ...prev, [key]: e.target.checked }))}
            />
            {t(`sources.${key}`)}
          </label>
        ))}
        {canEdit ? (
          <div>
            <button type="button" className={ui.primary} disabled={busy} onClick={() => void save()}>
              {t("save")}
            </button>
          </div>
        ) : null}
        {message ? <p role="status" className={ui.success}>{message}</p> : null}
        {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      </div>
    </section>
  );
}

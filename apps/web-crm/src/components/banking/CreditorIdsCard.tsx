"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type CreditorEntity = { id: string; name: string };

/** AF03 (GAF-04): Gläubiger-Identifikationsnummer je Rechtsträger (PUT creditor-ids) und
 *  Rückfall des Mandanten. Betreibereingabe, wird nicht validiert (OPEN_QUESTIONS M15-01 a);
 *  leer lassen entfernt die Nummer. Ohne Nummer erzeugt die API keinen Lastschriftlauf. */
export function CreditorIdsCard({
  entities,
  canUpdate,
  canUpdateTenant,
}: {
  entities: CreditorEntity[];
  canUpdate: boolean;
  canUpdateTenant: boolean;
}) {
  const t = useTranslations("CreditorIds");
  const [target, setTarget] = useState(entities[0]?.id ?? "tenant");
  const [value, setValue] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const allowed = target === "tenant" ? canUpdateTenant : canUpdate;
  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    const path =
      target === "tenant"
        ? "/api/bff/accounting/direct-debits/creditor-ids/tenant"
        : `/api/bff/accounting/direct-debits/creditor-ids/legal-entities/${target}`;
    const res = await bff(path, {
      method: "PUT",
      body: JSON.stringify({ sepa_creditor_id: value.trim() || null }),
    });
    setBusy(false);
    if (res.ok) setMessage(value.trim() ? t("saved") : t("removed"));
    else setError(res.message);
  };
  return (
    <form onSubmit={save} className="flex flex-col gap-3">
      <p className={ui.notice}>{t("notice")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {message ? <p role="status">{message}</p> : null}
      <label>
        <span className={ui.label}>{t("target")}</span>
        <select className={ui.input} value={target} onChange={(e) => setTarget(e.target.value)}>
          {entities.map((e) => (
            <option key={e.id} value={e.id}>
              {e.name}
            </option>
          ))}
          <option value="tenant">{t("tenantFallback")}</option>
        </select>
      </label>
      <label>
        <span className={ui.label}>{t("creditorId")}</span>
        <input className={ui.input} maxLength={35} value={value} onChange={(e) => setValue(e.target.value)} />
      </label>
      <div className={ui.formActions}>
        <button type="submit" className={ui.primary} disabled={!allowed || busy}>
          {t("save")}
        </button>
      </div>
      {!allowed ? <p className={ui.help}>{t("noPermission")}</p> : null}
    </form>
  );
}

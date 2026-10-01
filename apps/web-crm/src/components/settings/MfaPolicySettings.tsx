"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type MfaPolicy = {
  crm_mode: "all_staff" | "roles" | "voluntary";
  crm_role_codes: string[];
  portal_required: boolean;
  stored: boolean;
  available_role_codes: string[];
};

const MODES: MfaPolicy["crm_mode"][] = ["voluntary", "all_staff", "roles"];

/** M2-04: Richtlinie zweiter Faktor je Rolle (Mandant). Standard ohne gespeicherte Richtlinie:
 *  freiwillig für alle (Betreiberentscheidung M2-01), Portal freiwillig; die Pflicht für alle
 *  CRM-Rollen oder gewählte Rollen ist eine Wahl des Mandanten. Änderungen wirken bei der
 *  nächsten Anmeldung; laufende Sitzungen bleiben, wer noch keinen zweiten Faktor hat, richtet
 *  ihn im Anmeldeablauf ein. */
export function MfaPolicySettings({ initial, canUpdate }: { initial: MfaPolicy; canUpdate: boolean }) {
  const t = useTranslations("MfaPolicy");
  const [mode, setMode] = useState<MfaPolicy["crm_mode"]>(initial.crm_mode);
  const [roles, setRoles] = useState<string[]>(initial.crm_role_codes);
  const [portal, setPortal] = useState(initial.portal_required);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function toggle(code: string, checked: boolean) {
    setRoles((prev) => (checked ? [...prev, code].sort() : prev.filter((c) => c !== code)));
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setMessage(null);
    setError(null);
    if (mode === "roles" && roles.length === 0) {
      setError(t("rolesRequired"));
      return;
    }
    setBusy(true);
    const result = await bff<MfaPolicy>("/api/bff/auth/mfa-policy", {
      method: "PUT",
      body: JSON.stringify({ crm_mode: mode, crm_role_codes: mode === "roles" ? roles : [], portal_required: portal }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setMode(result.data.crm_mode);
    setRoles(result.data.crm_role_codes);
    setPortal(result.data.portal_required);
    setMessage(t("saved"));
  }

  return (
    <section className={ui.card} aria-labelledby="mfa-policy-title">
      <h2 id="mfa-policy-title" className={ui.h2}>
        {t("title")}
      </h2>
      <p className="mt-1 text-sm text-muted">{t("intro")}</p>
      {!initial.stored ? <p className="mt-1 text-xs text-muted">{t("defaultActive")}</p> : null}
      <form onSubmit={(e) => void save(e)} className="mt-3 flex flex-col gap-3">
        <fieldset className="flex flex-col gap-2" disabled={!canUpdate || busy}>
          <legend className={ui.label}>{t("crmLegend")}</legend>
          {MODES.map((value) => (
            <label key={value} className="flex items-start gap-2 text-sm">
              <input type="radio" name="mfa-crm-mode" value={value} checked={mode === value} onChange={() => setMode(value)} />
              <span>{t(`mode.${value}`)}</span>
            </label>
          ))}
        </fieldset>
        {mode === "roles" ? (
          <fieldset className="flex flex-wrap gap-3" disabled={!canUpdate || busy}>
            <legend className={ui.label}>{t("rolesLegend")}</legend>
            {initial.available_role_codes.map((code) => (
              <label key={code} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={roles.includes(code)} onChange={(e) => toggle(code, e.target.checked)} />
                <span className="font-mono text-xs">{code}</span>
              </label>
            ))}
          </fieldset>
        ) : null}
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" checked={portal} disabled={!canUpdate || busy} onChange={(e) => setPortal(e.target.checked)} />
          <span>{t("portalRequired")}</span>
        </label>
        <p className="text-xs text-muted">{t("transition")}</p>
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
        {message ? (
          <p role="status" className="text-sm">
            {message}
          </p>
        ) : null}
        {canUpdate ? (
          <button type="submit" className={`${ui.primary} self-start`} disabled={busy}>
            {busy ? t("saving") : t("save")}
          </button>
        ) : null}
      </form>
    </section>
  );
}

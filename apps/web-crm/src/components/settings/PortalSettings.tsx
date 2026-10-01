"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type BrandingRecord = Record<string, unknown> & { portal_name?: string | null; imprint_url?: string | null; privacy_url?: string | null };
export type PortalSecondFactor = "account_choice" | "required";

/** Portal je Mandant (B26, M21-04, B20): Name, Impressum und Datenschutz für das Portal sowie
 *  die Anmeldestrenge. Leere Felder lassen das Portal neutral. Der Branding Block wird ganz
 *  ersetzt, deshalb wird der bestehende Stand (Farben, Logo, Briefband) unverändert mitgesendet.
 *  Standard der Anmeldestrenge ist die Wahl je Konto (Betreiberentscheidung 26.09.2026). */
export function PortalSettings({ branding, secondFactor, canUpdate }: { branding: BrandingRecord; secondFactor: PortalSecondFactor; canUpdate: boolean }) {
  const t = useTranslations("PortalSettings");
  const [name, setName] = useState(branding.portal_name ?? "");
  const [imprint, setImprint] = useState(branding.imprint_url ?? "");
  const [privacy, setPrivacy] = useState(branding.privacy_url ?? "");
  const [factor, setFactor] = useState<PortalSecondFactor>(secondFactor);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const linkOk = (value: string) => value.trim() === "" || /^https:\/\/\S+$/.test(value.trim());
  const valid = linkOk(imprint) && linkOk(privacy) && name.trim().length <= 80;

  async function save() {
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff("/api/bff/tenant/settings", {
      method: "PATCH",
      body: JSON.stringify({
        branding: { ...branding, portal_name: name.trim() || null, imprint_url: imprint.trim() || null, privacy_url: privacy.trim() || null },
        portal_second_factor: factor,
      }),
    });
    setBusy(false);
    if (res.ok) setMessage(t("saved"));
    else setError(res.message);
  }

  return (
    <section className={ui.card} aria-labelledby="portal-settings-title">
      <div className="flex flex-col gap-3">
        <h2 id="portal-settings-title" className={ui.h2}>{t("title")}</h2>
        <p className={ui.help}>{t("description")}</p>
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="flex flex-col gap-1 text-sm">
            <span className={ui.label}>{t("name")}</span>
            <input className={ui.input} value={name} maxLength={80} disabled={!canUpdate || busy} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className={ui.label}>{t("imprint")}</span>
            <input className={ui.input} value={imprint} placeholder="https://" disabled={!canUpdate || busy} onChange={(e) => setImprint(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className={ui.label}>{t("privacy")}</span>
            <input className={ui.input} value={privacy} placeholder="https://" disabled={!canUpdate || busy} onChange={(e) => setPrivacy(e.target.value)} />
          </label>
        </div>
        <label className="flex flex-col gap-1 text-sm sm:max-w-md">
          <span className={ui.label}>{t("secondFactor")}</span>
          <select className={ui.input} value={factor} disabled={!canUpdate || busy} onChange={(e) => setFactor(e.target.value as PortalSecondFactor)}>
            <option value="account_choice">{t("factor.account_choice")}</option>
            <option value="required">{t("factor.required")}</option>
          </select>
        </label>
        <p className={ui.help}>{t("factorHint")}</p>
        {!valid ? <p className={ui.help}>{t("invalid")}</p> : null}
        <div>
          <button type="button" className={ui.secondary} disabled={!canUpdate || busy || !valid} onClick={() => void save()}>
            {t("save")}
          </button>
        </div>
        {!canUpdate ? <p className={ui.help}>{t("readOnly")}</p> : null}
        {message ? <span className="text-xs text-success-fg">{message}</span> : null}
        {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      </div>
    </section>
  );
}

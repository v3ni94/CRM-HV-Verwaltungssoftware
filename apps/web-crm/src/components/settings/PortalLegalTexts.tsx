"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { StatusPill } from "@/components/ui/StatusPill";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type LegalTextItem = {
  code: string;
  label: string;
  released: boolean;
  version: number | null;
  external_url: string | null;
};
export type LegalTextsConfig = {
  terms_version_mode: "manual" | "follow_text";
  policy_terms_version: string | null;
  approved_text_version: number | null;
  suggested_label: string | null;
  in_sync: boolean;
  items: LegalTextItem[];
};

/** Stand der Rechtstexte des Portals (AE29, M21-04): Ampel je Text, Abgleich mit der Fassung der
 *  Einwilligungsrichtlinie (AC06) und der Schalter, ob die Fassung dem freigegebenen Text folgt.
 *  Das Ändern von Fassung und Schalter verlangt contacts:approve (vom Backend geprüft). */
export function PortalLegalTexts({ config, canChange }: { config: LegalTextsConfig; canChange: boolean }) {
  const t = useTranslations("PortalLegalTexts");
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [mode, setMode] = useState(config.terms_version_mode);

  async function call(path: string, method: string, body: unknown) {
    setError(null);
    setSaved(false);
    const res = await bff(path, { method, body: JSON.stringify(body) });
    if (!res.ok) {
      setError(res.message || t("error"));
      return;
    }
    setSaved(true);
    router.refresh();
  }

  return (
    <div className="flex min-w-0 flex-col gap-4">
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      {saved ? <p role="status" className="text-sm text-muted">{t("saved")}</p> : null}
      <section className="flex min-w-0 flex-col gap-2 rounded-md border border-line p-3" aria-labelledby="legal-status-title">
        <h2 id="legal-status-title" className="text-sm font-semibold">{t("statusTitle")}</h2>
        <ul className="flex flex-col gap-1 text-sm">
          {config.items.map((item) => (
            <li key={item.code} className="flex flex-wrap items-center gap-2" data-testid={`legal-item-${item.code}`}>
              <span>{item.label}</span>
              <StatusPill
                variant={item.released ? "success" : "warning"}
                label={item.released ? t("released", { version: item.version ?? 0 }) : t("notReleased")}
              />
              {!item.released && item.external_url ? <span className="text-xs text-muted">{t("externalLink")}</span> : null}
            </li>
          ))}
        </ul>
      </section>
      <section className="flex min-w-0 flex-col gap-2 rounded-md border border-line p-3" aria-labelledby="legal-terms-title">
        <h2 id="legal-terms-title" className="text-sm font-semibold">{t("termsTitle")}</h2>
        <p className="text-sm text-muted">{t("termsHint")}</p>
        <dl className="grid grid-cols-1 gap-x-4 gap-y-1 text-sm sm:grid-cols-[auto_1fr]">
          <dt className="text-muted">{t("policyVersion")}</dt>
          <dd>{config.policy_terms_version ?? t("none")}</dd>
          <dt className="text-muted">{t("approvedVersion")}</dt>
          <dd>{config.approved_text_version === null ? t("none") : `v${config.approved_text_version}`}</dd>
          <dt className="text-muted">{t("suggested")}</dt>
          <dd>{config.suggested_label ?? t("none")}</dd>
        </dl>
        <div>
          <StatusPill variant={config.in_sync ? "success" : "warning"} label={config.in_sync ? t("inSync") : t("notInSync")} />
        </div>
        {canChange ? (
          <>
            <fieldset className="flex flex-col gap-1 text-sm">
              <legend className={ui.label}>{t("modeLabel")}</legend>
              <label className="flex items-center gap-2">
                <input type="radio" name="terms-mode" checked={mode === "manual"} onChange={() => setMode("manual")} />
                {t("modeManual")}
              </label>
              <label className="flex items-start gap-2">
                <input type="radio" name="terms-mode" className="mt-1" checked={mode === "follow_text"} onChange={() => setMode("follow_text")} />
                <span>
                  {t("modeFollow")}
                  <span className="block text-xs text-muted">{t("modeFollowHint")}</span>
                </span>
              </label>
            </fieldset>
            <div className={ui.formActions}>
              <button
                type="button"
                className={ui.buttonSm}
                disabled={mode === config.terms_version_mode}
                onClick={() => call("/api/bff/tenant/legal-texts-config", "PUT", { terms_version_mode: mode })}
              >
                {t("saveMode")}
              </button>
              <button
                type="button"
                className={ui.buttonSm}
                disabled={config.suggested_label === null || config.in_sync}
                onClick={() => {
                  if (config.suggested_label && window.confirm(t("applyConfirm", { label: config.suggested_label }))) {
                    void call("/api/bff/tenant/legal-texts-config/apply-terms-version", "POST", { confirm: true });
                  }
                }}
              >
                {t("apply")}
              </button>
            </div>
          </>
        ) : null}
      </section>
    </div>
  );
}

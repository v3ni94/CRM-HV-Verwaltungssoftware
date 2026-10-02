"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Mode = "consent_only" | "consent_or_contract";
export type ConsentPolicyData = { email_delivery: Mode; data_sharing: Mode; portal_terms_version: string | null };

/**
 * Einwilligungsregeln des Mandanten (GAI-414, AC06): GET und PUT /consent-policy. Standard ist
 * die strenge Variante "nur mit Einwilligung"; die Erweiterung auf Vertrag ist eine
 * Rechtsentscheidung (OPEN_QUESTIONS AC06-01, AC06-02) und wird als Ereignis protokolliert.
 */
export function ConsentPolicySettings({ canEdit }: { canEdit: boolean }) {
  const t = useTranslations("ConsentPolicySettings");
  const [data, setData] = useState<ConsentPolicyData | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void bff<ConsentPolicyData>("/api/bff/consent-policy").then((res) => {
      if (res.ok) setData(res.data);
      else setError(res.message);
    });
  }, []);

  async function save() {
    if (!data) return;
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<ConsentPolicyData>("/api/bff/consent-policy", {
      method: "PUT",
      body: JSON.stringify({
        email_delivery: data.email_delivery,
        data_sharing: data.data_sharing,
        portal_terms_version: data.portal_terms_version?.trim() || null,
      }),
    });
    setBusy(false);
    if (res.ok) {
      setData(res.data);
      setMessage(t("saved"));
    } else setError(res.message);
  }

  return (
    <section aria-labelledby="consent-policy-title" className={`${ui.card} max-w-2xl`}>
      <h2 id="consent-policy-title" className="mb-1 text-base font-semibold">
        {t("title")}
      </h2>
      <p className="mb-3 text-sm">{t("hint")}</p>
      {data ? (
        <div className="flex flex-col gap-3">
          {(["email_delivery", "data_sharing"] as const).map((k) => (
            <div key={k} className="max-w-md">
              <label className={ui.label} htmlFor={`consent-policy-${k}`}>
                {t(k)}
              </label>
              <select
                id={`consent-policy-${k}`}
                className={ui.input}
                value={data[k]}
                disabled={!canEdit || busy}
                onChange={(e) => setData({ ...data, [k]: e.target.value as Mode })}
              >
                <option value="consent_only">{t("consentOnly")}</option>
                <option value="consent_or_contract">{t("consentOrContract")}</option>
              </select>
            </div>
          ))}
          <div className="max-w-md">
            <label className={ui.label} htmlFor="consent-policy-terms">
              {t("termsVersion")}
            </label>
            <input
              id="consent-policy-terms"
              className={ui.input}
              maxLength={60}
              value={data.portal_terms_version ?? ""}
              disabled={!canEdit || busy}
              onChange={(e) => setData({ ...data, portal_terms_version: e.target.value })}
            />
          </div>
          {canEdit ? (
            <div>
              <button type="button" className={ui.primary} disabled={busy} onClick={() => void save()}>
                {t("save")}
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
      {message ? <p role="status" className={ui.success}>{message}</p> : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </section>
  );
}

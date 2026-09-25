"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type DmsConnection = {
  kind: string;
  enabled: boolean;
  base_url: string | null;
  has_secret: boolean;
  options: Record<string, string>;
};

const OBJECT_FIELD_KEY = "object_field_id";
const COMPANY_FIELD_KEY = "company_field_id";

/** DMS-Anbindung (Einstellungen): Paperless-Zugangsdaten pflegbar, Google Drive nur lesend.
 *  Immoware24 bleibt Master der Stammdaten; hier wird nur die Anbindung des CRM an das
 *  Dokumentenmanagement konfiguriert. */
export function DmsConnectionSettings({
  paperless,
  googleDrive,
}: {
  paperless: DmsConnection | null;
  googleDrive: DmsConnection | null;
}) {
  const t = useTranslations("DmsSettings");
  const [saved, setSaved] = useState<DmsConnection | null>(paperless);
  const [enabled, setEnabled] = useState(paperless?.enabled ?? false);
  const [baseUrl, setBaseUrl] = useState(paperless?.base_url ?? "");
  const [token, setToken] = useState("");
  const [objectFieldId, setObjectFieldId] = useState(paperless?.options?.[OBJECT_FIELD_KEY] ?? "");
  const [companyFieldId, setCompanyFieldId] = useState(paperless?.options?.[COMPANY_FIELD_KEY] ?? "");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage(null);
    setError(null);
    const options: Record<string, string> = { ...(saved?.options ?? {}) };
    if (objectFieldId.trim()) options[OBJECT_FIELD_KEY] = objectFieldId.trim();
    else delete options[OBJECT_FIELD_KEY];
    if (companyFieldId.trim()) options[COMPANY_FIELD_KEY] = companyFieldId.trim();
    else delete options[COMPANY_FIELD_KEY];
    const body = {
      enabled,
      base_url: baseUrl.trim() || null,
      options,
      ...(token ? { secret: token } : {}),
    };
    setBusy(true);
    const res = await bff<DmsConnection>("/api/bff/dms-connections/paperless", {
      method: "PUT",
      body: JSON.stringify(body),
    });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setSaved(res.data);
    setToken("");
    setMessage(t("saved"));
  };

  return (
    <div className="flex flex-col gap-4">
      <form onSubmit={save} className={`${ui.card} flex flex-col gap-4`} aria-label={t("paperlessTitle")}>
        <h2 className={ui.h2}>{t("paperlessTitle")}</h2>

        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          {t("enabled")}
        </label>

        <div>
          <label htmlFor="dms-base-url" className={ui.label}>
            {t("baseUrl")}
          </label>
          <input
            id="dms-base-url"
            type="url"
            className={ui.input}
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://paperless.muellerhv.de"
          />
          <p className={ui.help}>{t("baseUrlHint")}</p>
        </div>

        <div>
          <label htmlFor="dms-token" className={ui.label}>
            {t("token")}
          </label>
          <input
            id="dms-token"
            type="password"
            autoComplete="off"
            className={ui.input}
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder={saved?.has_secret ? t("tokenStored") : t("tokenMissing")}
          />
          <p className={ui.help}>{t("tokenHint")}</p>
        </div>

        <div className="grid gap-2 sm:grid-cols-2">
          <div>
            <label htmlFor="dms-object-field" className={ui.label}>
              {t("objectFieldId")}
            </label>
            <input
              id="dms-object-field"
              className={ui.input}
              value={objectFieldId}
              onChange={(e) => setObjectFieldId(e.target.value)}
              placeholder="7"
            />
          </div>
          <div>
            <label htmlFor="dms-company-field" className={ui.label}>
              {t("companyFieldId")}
            </label>
            <input
              id="dms-company-field"
              className={ui.input}
              value={companyFieldId}
              onChange={(e) => setCompanyFieldId(e.target.value)}
              placeholder="5"
            />
          </div>
        </div>

        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
        {message ? <p className={ui.success}>{message}</p> : null}

        <div className={ui.formActions}>
          <button type="submit" className={`${ui.primary} ${ui.actionFull}`} disabled={busy}>
            {t("save")}
          </button>
        </div>
      </form>

      <div className={`${ui.card} flex flex-col gap-2`} aria-label={t("googleDriveTitle")}>
        <h2 className={ui.h2}>{t("googleDriveTitle")}</h2>
        <p className="text-sm text-muted">{t("googleDriveHint")}</p>
        <dl className="grid gap-1 text-sm sm:grid-cols-2">
          <dt className="text-muted">{t("enabled")}</dt>
          <dd>{googleDrive?.enabled ? t("yes") : t("no")}</dd>
          <dt className="text-muted">{t("baseUrl")}</dt>
          <dd>{googleDrive?.base_url ?? t("notSet")}</dd>
          <dt className="text-muted">{t("token")}</dt>
          <dd>{googleDrive?.has_secret ? t("tokenStored") : t("tokenMissing")}</dd>
        </dl>
      </div>
    </div>
  );
}

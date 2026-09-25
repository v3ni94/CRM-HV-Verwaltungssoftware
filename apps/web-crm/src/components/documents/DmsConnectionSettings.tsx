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
const ROOT_FOLDER_KEY = "root_folder_id";
const CLIENT_ID_KEY = "client_id";

/** DMS-Anbindung (Einstellungen): Paperless- und Google-Drive-Zugangsdaten pflegbar.
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

  const [gdSaved, setGdSaved] = useState<DmsConnection | null>(googleDrive);
  const [gdEnabled, setGdEnabled] = useState(googleDrive?.enabled ?? false);
  const [rootFolderId, setRootFolderId] = useState(googleDrive?.options?.[ROOT_FOLDER_KEY] ?? "");
  const [clientId, setClientId] = useState(googleDrive?.options?.[CLIENT_ID_KEY] ?? "");
  const [clientSecret, setClientSecret] = useState("");
  const [refreshToken, setRefreshToken] = useState("");
  const [gdError, setGdError] = useState<string | null>(null);
  const [gdMessage, setGdMessage] = useState<string | null>(null);
  const [gdBusy, setGdBusy] = useState(false);

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

  const saveGoogleDrive = async (e: React.FormEvent) => {
    e.preventDefault();
    setGdMessage(null);
    setGdError(null);
    if (Boolean(clientSecret.trim()) !== Boolean(refreshToken.trim())) {
      setGdError(t("secretPairRequired"));
      return;
    }
    const options: Record<string, string> = { ...(gdSaved?.options ?? {}) };
    if (rootFolderId.trim()) options[ROOT_FOLDER_KEY] = rootFolderId.trim();
    else delete options[ROOT_FOLDER_KEY];
    if (clientId.trim()) options[CLIENT_ID_KEY] = clientId.trim();
    else delete options[CLIENT_ID_KEY];
    const secret =
      clientSecret.trim() && refreshToken.trim()
        ? JSON.stringify({ client_secret: clientSecret.trim(), refresh_token: refreshToken.trim() })
        : null;
    const body = {
      enabled: gdEnabled,
      base_url: null,
      options,
      ...(secret ? { secret } : {}),
    };
    setGdBusy(true);
    const res = await bff<DmsConnection>("/api/bff/dms-connections/google_drive", {
      method: "PUT",
      body: JSON.stringify(body),
    });
    setGdBusy(false);
    if (!res.ok) return setGdError(res.message);
    setGdSaved(res.data);
    setClientSecret("");
    setRefreshToken("");
    setGdMessage(t("saved"));
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

      <form
        onSubmit={saveGoogleDrive}
        className={`${ui.card} flex flex-col gap-4`}
        aria-label={t("googleDriveTitle")}
      >
        <h2 className={ui.h2}>{t("googleDriveTitle")}</h2>
        <p className="text-sm text-muted">{t("googleDriveHint")}</p>

        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={gdEnabled} onChange={(e) => setGdEnabled(e.target.checked)} />
          {t("enabled")}
        </label>

        <div>
          <label htmlFor="dms-gd-root-folder" className={ui.label}>
            {t("rootFolderId")}
          </label>
          <input
            id="dms-gd-root-folder"
            className={ui.input}
            value={rootFolderId}
            onChange={(e) => setRootFolderId(e.target.value)}
          />
          <p className={ui.help}>{t("rootFolderIdHint")}</p>
        </div>

        <div>
          <label htmlFor="dms-gd-client-id" className={ui.label}>
            {t("clientId")}
          </label>
          <input
            id="dms-gd-client-id"
            className={ui.input}
            value={clientId}
            onChange={(e) => setClientId(e.target.value)}
          />
        </div>

        <div className="grid gap-2 sm:grid-cols-2">
          <div>
            <label htmlFor="dms-gd-client-secret" className={ui.label}>
              {t("clientSecret")}
            </label>
            <input
              id="dms-gd-client-secret"
              type="password"
              autoComplete="off"
              className={ui.input}
              value={clientSecret}
              onChange={(e) => setClientSecret(e.target.value)}
              placeholder={gdSaved?.has_secret ? t("secretStored") : t("secretMissing")}
            />
          </div>
          <div>
            <label htmlFor="dms-gd-refresh-token" className={ui.label}>
              {t("refreshToken")}
            </label>
            <input
              id="dms-gd-refresh-token"
              type="password"
              autoComplete="off"
              className={ui.input}
              value={refreshToken}
              onChange={(e) => setRefreshToken(e.target.value)}
              placeholder={gdSaved?.has_secret ? t("secretStored") : t("secretMissing")}
            />
          </div>
        </div>
        <p className={ui.help}>{t("secretHint")}</p>

        {gdError ? (
          <p role="alert" className={ui.alert}>
            {gdError}
          </p>
        ) : null}
        {gdMessage ? <p className={ui.success}>{gdMessage}</p> : null}

        <div className={ui.formActions}>
          <button type="submit" className={`${ui.primary} ${ui.actionFull}`} disabled={gdBusy}>
            {t("save")}
          </button>
        </div>
      </form>
    </div>
  );
}

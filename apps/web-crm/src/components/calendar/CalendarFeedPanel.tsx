"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Kalender-Abo für externe Kalender (M23-06): persönliche Adresse mit Token. Die Adresse wird
 *  nur einmal angezeigt; eine neue Adresse ersetzt die alte, Widerruf beendet das Abo. */
export function CalendarFeedPanel({
  initialActive,
  canDownload = false,
}: {
  initialActive: boolean;
  /** Download needs tenant_settings:read (GAH-405); without it the link would only give 403. */
  canDownload?: boolean;
}) {
  const t = useTranslations("CalendarFeed");
  const [active, setActive] = useState(initialActive);
  const [url, setUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create() {
    if (active && !window.confirm(t("replaceConfirm"))) return;
    setBusy(true);
    setError(null);
    const res = await bff<{ path: string }>("/api/bff/workspace/calendar-feed/token", {
      method: "POST",
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setUrl(`${window.location.origin}${res.data.path}`);
    setActive(true);
  }

  async function revoke() {
    if (!window.confirm(t("revokeConfirm"))) return;
    setBusy(true);
    setError(null);
    const res = await bff<null>("/api/bff/workspace/calendar-feed/token", { method: "DELETE" });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setUrl(null);
    setActive(false);
  }

  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-sm font-semibold">{t("title")}</h2>
      <p className="text-sm text-muted">{active ? t("active") : t("inactive")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {url ? (
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("address")}</span>
          <input className={ui.input} readOnly value={url} onFocus={(e) => e.currentTarget.select()} />
        </label>
      ) : null}
      {url ? (
        <span className={ui.help}>{t("once")}</span>
      ) : null}
      {canDownload ? (
        <p className="text-sm">
          <a className="underline" href="/api/bff/workspace/calendar.ics" download="kalender.ics">
            {t("download")}
          </a>{" "}
          <span className={ui.help}>{t("downloadHint")}</span>
        </p>
      ) : null}
      <div className="flex gap-2">
        <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void create()}>
          {active ? t("renew") : t("create")}
        </button>
        {active ? (
          <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void revoke()}>
            {t("revoke")}
          </button>
        ) : null}
      </div>
    </section>
  );
}

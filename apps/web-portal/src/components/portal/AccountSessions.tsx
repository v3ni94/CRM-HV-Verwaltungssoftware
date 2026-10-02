"use client";

import type { components } from "@mhvp/api-client";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type SessionRow = components["schemas"]["SessionOut"];

/** GAH-305: change the own password (POST /auth/password). The API ends every session of the
 *  account, the current one when its access token expires. */
export function PasswordChange() {
  const t = useTranslations("Security");
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setMessage(null);
    if (next !== repeat) {
      setError(t("passwordMismatch"));
      return;
    }
    setBusy(true);
    const res = await bff<null>("/api/bff/auth/password", {
      method: "POST",
      body: JSON.stringify({ current_password: current, new_password: next }),
    });
    setBusy(false);
    if (res.ok) {
      setCurrent("");
      setNext("");
      setRepeat("");
      setMessage(t("passwordChanged"));
    } else {
      setError(res.message);
    }
  }

  return (
    <section className={`${ui.card} ${ui.sectionGap}`} aria-labelledby="password-title">
      <h2 id="password-title" className={ui.h2}>
        {t("passwordTitle")}
      </h2>
      <p className={ui.help}>{t("passwordHint")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {message ? (
        <p role="status" className={ui.success}>
          {message}
        </p>
      ) : null}
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3 sm:max-w-sm">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("currentPassword")}</span>
          <input type="password" required autoComplete="current-password" className={ui.input}
            value={current} onChange={(e) => setCurrent(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("newPassword")}</span>
          <input type="password" required minLength={12} autoComplete="new-password" className={ui.input}
            value={next} onChange={(e) => setNext(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("repeatPassword")}</span>
          <input type="password" required autoComplete="new-password" className={ui.input}
            value={repeat} onChange={(e) => setRepeat(e.target.value)} />
        </label>
        <button type="submit" className={ui.primary} disabled={busy}>
          {t("passwordSubmit")}
        </button>
      </form>
    </section>
  );
}

/** GAH-305: active sessions (device list) with "Sitzung beenden" (GET/DELETE /auth/sessions). */
export function ActiveSessions({ initial }: { initial: SessionRow[] }) {
  const t = useTranslations("Security");
  const format = useFormatter();
  const [rows, setRows] = useState(initial);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const when = (value: string) =>
    format.dateTime(new Date(value), {
      day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
    });

  async function revoke(id: string) {
    setError(null);
    setBusyId(id);
    const res = await bff<null>(`/api/bff/auth/sessions/${id}`, { method: "DELETE" });
    setBusyId(null);
    if (res.ok) setRows((prev) => prev.filter((r) => r.family_id !== id));
    else setError(res.message);
  }

  return (
    <section className={`${ui.card} ${ui.sectionGap}`} aria-labelledby="sessions-title">
      <h2 id="sessions-title" className={ui.h2}>
        {t("sessionsTitle")}
      </h2>
      <p className={ui.help}>{t("sessionsHint")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {rows.length === 0 ? (
        <p className="text-sm text-muted">{t("noSessions")}</p>
      ) : (
        <ul className="flex flex-col gap-2 text-sm">
          {rows.map((row) => (
            <li key={row.family_id} className="flex flex-wrap items-center justify-between gap-2">
              <span>
                {row.user_agent || t("sessionUnknownDevice")}
                <span className="block text-muted">
                  {t("sessionSince", { start: when(row.started_at), last: when(row.last_used_at) })}
                </span>
              </span>
              <button type="button" className={ui.secondary} disabled={busyId === row.family_id}
                onClick={() => void revoke(row.family_id)}>
                {t("sessionRevoke")}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

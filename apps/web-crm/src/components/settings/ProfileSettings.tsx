"use client";

import type { components } from "@mhvp/api-client";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

type SessionRow = components["schemas"]["SessionOut"];

function PasswordForm() {
  const t = useTranslations("Profile");
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setMessage(null);
    setError(null);
    if (next !== repeat) {
      setError(t("mismatch"));
      return;
    }
    setBusy(true);
    const res = await bff<null>("/api/bff/auth/password", {
      method: "POST",
      body: JSON.stringify({ current_password: current, new_password: next }),
    });
    setBusy(false);
    if (res.ok) {
      setMessage(t("passwordChanged"));
      setCurrent("");
      setNext("");
      setRepeat("");
    } else {
      setError(res.message);
    }
  }

  return (
    <form onSubmit={(e) => void submit(e)} className={`${ui.card} flex flex-col gap-3 sm:max-w-sm`}>
      <h2 className="text-sm font-semibold">{t("passwordTitle")}</h2>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("currentPassword")}</span>
        <input type="password" required className={ui.input} value={current} onChange={(e) => setCurrent(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("newPassword")}</span>
        <input type="password" required minLength={12} className={ui.input} value={next} onChange={(e) => setNext(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("repeatPassword")}</span>
        <input type="password" required minLength={12} className={ui.input} value={repeat} onChange={(e) => setRepeat(e.target.value)} />
      </label>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      {message ? <p className="text-xs text-success-fg">{message}</p> : null}
      <button type="submit" className={ui.primary} disabled={busy}>
        {t("save")}
      </button>
    </form>
  );
}

function Sessions({ initial }: { initial: SessionRow[] }) {
  const t = useTranslations("Profile");
  const [sessions, setSessions] = useState(initial);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function revoke(familyId: string) {
    setBusyId(familyId);
    const res = await bff<null>(`/api/bff/auth/sessions/${familyId}`, { method: "DELETE" });
    setBusyId(null);
    if (res.ok) setSessions((prev) => prev.filter((s) => s.family_id !== familyId));
  }

  return (
    <section className={ui.card}>
      <h2 className="text-sm font-semibold">{t("sessionsTitle")}</h2>
      {sessions.length === 0 ? (
        <p className="mt-2 text-sm text-muted">{t("noSessions")}</p>
      ) : (
        <ul className="mt-2 flex flex-col gap-2 text-sm">
          {sessions.map((s) => (
            <li key={s.family_id} className="flex items-center justify-between gap-2 border-b border-border pb-2 last:border-0">
              <span className="text-muted">
                {s.user_agent ?? t("unknownDevice")} · {formatDateTime(s.last_used_at)}
              </span>
              <button type="button" className="text-xs underline" disabled={busyId === s.family_id} onClick={() => void revoke(s.family_id)}>
                {t("revoke")}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function ProfileSettings({
  displayName,
  email,
  roles,
  tenantName,
  initialSessions,
}: {
  displayName: string;
  email: string;
  roles: string[];
  tenantName: string;
  initialSessions: SessionRow[];
}) {
  const t = useTranslations("Profile");
  return (
    <div className="flex flex-col gap-4">
      <section className={ui.card}>
        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          <div>
            <dt className={ui.label}>{t("name")}</dt>
            <dd>{displayName}</dd>
          </div>
          <div>
            <dt className={ui.label}>{t("email")}</dt>
            <dd>{email}</dd>
          </div>
          <div>
            <dt className={ui.label}>{t("roles")}</dt>
            <dd>{roles.join(", ") || "-"}</dd>
          </div>
          <div>
            <dt className={ui.label}>{t("tenant")}</dt>
            <dd>{tenantName}</dd>
          </div>
        </dl>
      </section>
      <PasswordForm />
      <Sessions initial={initialSessions} />
    </div>
  );
}

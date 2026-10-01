"use client";

import type { components } from "@mhvp/api-client";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";
import { createPasskey, passkeysSupported, type WebAuthnOptions } from "@/lib/webauthn";
import { ThemeSwitch } from "@/components/workspace/ThemeToggle";

import { SignatureProfile, type SignaturePreviewData, type SignatureProfileData } from "./SignatureProfile";

type SessionRow = components["schemas"]["SessionOut"];
type TrustedDeviceRow = components["schemas"]["TrustedDeviceOut"];

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
    <form aria-label={t("passwordTitle")} onSubmit={(e) => void submit(e)} className={`${ui.card} flex flex-col gap-3 sm:max-w-sm`}>
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

type Setup = { secret: string; otpauth_uri: string; qr: string };

/** Optional second factor (operator 26.09.2026, M2-01): every user may switch TOTP on or off
 *  here; the login asks for a code only while it is on. */
function SecondFactor({ initialEnabled, required = false }: { initialEnabled: boolean; required?: boolean }) {
  const t = useTranslations("Profile");
  const tPolicy = useTranslations("MfaPolicy");
  const [enabled, setEnabled] = useState(initialEnabled);
  const [setup, setSetup] = useState<Setup | null>(null);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setError(null);
    setMessage(null);
    setBusy(true);
    const res = await bff<Setup>("/api/session/totp/setup", { method: "POST", body: "{}" });
    setBusy(false);
    if (res.ok) setSetup(res.data);
    else setError(res.message);
  }

  async function confirm(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!/^\d{6,8}$/.test(code.trim())) {
      setError(t("totpCodeInvalid"));
      return;
    }
    setBusy(true);
    const res = await bff<null>("/api/bff/auth/totp/confirm", {
      method: "POST",
      body: JSON.stringify({ code: code.trim() }),
    });
    setBusy(false);
    if (res.ok) {
      setEnabled(true);
      setSetup(null);
      setCode("");
      setMessage(t("totpEnabled"));
    } else {
      setError(res.message);
    }
  }

  async function disable(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    const res = await bff<null>("/api/bff/auth/totp/disable", {
      method: "POST",
      body: JSON.stringify({ current_password: password }),
    });
    setBusy(false);
    if (res.ok) {
      setEnabled(false);
      setPassword("");
      setMessage(t("totpDisabled"));
    } else {
      setError(res.message);
    }
  }

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="totp-title">
      <h2 id="totp-title" className="text-sm font-semibold">
        {t("totpTitle")}
      </h2>
      <p className="text-sm text-muted">{enabled ? t("totpStatusOn") : t("totpStatusOff")}</p>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      {message ? <p role="status" className="text-xs text-success-fg">{message}</p> : null}
      {/* M2-04: under the tenant policy the second factor stays; the API refuses the switch off. */}
      {enabled && required ? (
        <p className="text-xs text-muted">{tPolicy("requiredHint")}</p>
      ) : enabled ? (
        <form aria-label={t("totpDisable")} onSubmit={(e) => void disable(e)} className="flex flex-col gap-3 sm:max-w-sm">
          <p className="text-xs text-muted">{t("totpDisableHint")}</p>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("currentPassword")}</span>
            <input
              type="password"
              required
              autoComplete="current-password"
              className={ui.input}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <button type="submit" className={ui.buttonSm} disabled={busy}>
            {t("totpDisable")}
          </button>
        </form>
      ) : setup ? (
        <form aria-label={t("totpTitle")} onSubmit={(e) => void confirm(e)} className="flex flex-col gap-3 sm:max-w-sm">
          <p className="text-xs text-muted">{t("totpSetupHint")}</p>
          {/* eslint-disable-next-line @next/next/no-img-element -- server generated data URL */}
          <img src={setup.qr} alt={t("totpQrAlt")} width={220} height={220} className="rounded bg-paper p-1" />
          <p className={ui.label}>{t("totpSecretLabel")}</p>
          <code data-testid="totp-secret" className="select-all break-all rounded bg-surface-2 px-2 py-1 font-mono text-sm">
            {setup.secret}
          </code>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("totpCode")}</span>
            <input
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={8}
              className={`${ui.input} font-mono tracking-widest`}
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
          </label>
          <button type="submit" className={ui.primary} disabled={busy}>
            {t("totpConfirm")}
          </button>
        </form>
      ) : (
        <div>
          <p className="mb-2 text-xs text-muted">{t("totpEnableHint")}</p>
          <button type="button" className={ui.primary} disabled={busy} onClick={() => void start()}>
            {t("totpEnable")}
          </button>
        </div>
      )}
    </section>
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
              <button type="button" className={ui.buttonSm} disabled={busyId === s.family_id} onClick={() => void revoke(s.family_id)}>
                {t("revoke")}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function TrustedDevices({ initial }: { initial: TrustedDeviceRow[] }) {
  const t = useTranslations("Profile");
  const [devices, setDevices] = useState(initial);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function revoke(id: string) {
    setBusyId(id);
    const res = await bff<null>(`/api/bff/auth/trusted-devices/${id}`, { method: "DELETE" });
    setBusyId(null);
    if (res.ok) setDevices((prev) => prev.filter((d) => d.id !== id));
  }

  return (
    <section className={ui.card}>
      <h2 className="text-sm font-semibold">{t("devicesTitle")}</h2>
      <p className="mt-1 text-xs text-muted">{t("devicesHint")}</p>
      {devices.length === 0 ? (
        <p className="mt-2 text-sm text-muted">{t("noDevices")}</p>
      ) : (
        <ul className="mt-2 flex flex-col gap-2 text-sm">
          {devices.map((d) => (
            <li key={d.id} className="flex items-center justify-between gap-2 border-b border-border pb-2 last:border-0">
              <span className="text-muted">
                {d.label ?? t("unknownDevice")} · {t("deviceExpires")} {formatDateTime(d.expires_at)}
              </span>
              <button type="button" className={ui.buttonSm} disabled={busyId === d.id} onClick={() => void revoke(d.id)}>
                {t("revoke")}
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

type PasskeyRow = { id: string; label: string | null; created_at: string; last_used_at: string | null; passwordless?: boolean };

/** S16-01: own passkeys (second factor, optionally passwordless sign in). */
export function Passkeys() {
  const t = useTranslations("Profile");
  const [available, setAvailable] = useState<boolean | null>(null);
  const [rows, setRows] = useState<PasskeyRow[]>([]);
  const [label, setLabel] = useState("");
  const [passwordless, setPasswordless] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  async function load() {
    const status = await bff<{ available: boolean }>("/api/bff/auth/webauthn/status");
    setAvailable(status.ok ? status.data?.available === true : false);
    const list = await bff<PasskeyRow[]>("/api/bff/auth/webauthn/credentials");
    if (list.ok && Array.isArray(list.data)) setRows(list.data);
  }
  useEffect(() => {
    void load();
  }, []);

  async function add(event: React.FormEvent) {
    event.preventDefault();
    setMessage(null);
    if (!passkeysSupported()) {
      setMessage({ ok: false, text: t("passkeyFailed") });
      return;
    }
    setBusy(true);
    const options = await bff<WebAuthnOptions>("/api/bff/auth/webauthn/register/options", {
      method: "POST",
      body: JSON.stringify({ passwordless }),
    });
    if (!options.ok) {
      setBusy(false);
      setMessage({ ok: false, text: options.message });
      return;
    }
    let created: Awaited<ReturnType<typeof createPasskey>>;
    try {
      created = await createPasskey(options.data.public_key);
    } catch {
      setBusy(false);
      setMessage({ ok: false, text: t("passkeyFailed") });
      return;
    }
    const done = await bff<PasskeyRow>("/api/bff/auth/webauthn/register/verify", {
      method: "POST",
      body: JSON.stringify({ challenge_id: options.data.challenge_id, label: label.trim() || null, ...created }),
    });
    setBusy(false);
    if (!done.ok) {
      setMessage({ ok: false, text: done.message });
      return;
    }
    setRows((prev) => [...prev, done.data]);
    setLabel("");
    setMessage({ ok: true, text: t("passkeyAdded") });
  }

  async function revoke(id: string) {
    const res = await bff<null>(`/api/bff/auth/webauthn/credentials/${id}`, { method: "DELETE" });
    if (res.ok) setRows((prev) => prev.filter((r) => r.id !== id));
  }

  return (
    <section className={ui.card} aria-labelledby="passkeys-title">
      <h2 id="passkeys-title" className="text-sm font-semibold">
        {t("passkeysTitle")}
      </h2>
      <p className="mt-1 text-xs text-muted">{t("passkeysHint")}</p>
      {message ? (
        <p role={message.ok ? "status" : "alert"} className={message.ok ? "mt-2 text-sm" : ui.alert}>
          {message.text}
        </p>
      ) : null}
      {rows.length === 0 ? (
        <p className="mt-2 text-sm text-muted">{t("noPasskeys")}</p>
      ) : (
        <ul className="mt-2 flex flex-col gap-2 text-sm">
          {rows.map((r) => (
            <li key={r.id} className="flex items-center justify-between gap-2 border-b border-border pb-2 last:border-0">
              <span className="text-muted">
                {r.label ?? t("unknownDevice")} · {formatDateTime(r.created_at)}
                {r.passwordless ? ` · ${t("passkeyPasswordlessBadge")}` : ""}
              </span>
              <button type="button" className={ui.buttonSm} onClick={() => void revoke(r.id)}>
                {t("passkeyRevoke")}
              </button>
            </li>
          ))}
        </ul>
      )}
      {available === false ? (
        <p className="mt-2 text-sm text-muted">{t("passkeysUnavailable")}</p>
      ) : available ? (
        <form onSubmit={add} className="mt-3 flex flex-col gap-2">
          <label htmlFor="passkey-label" className={ui.label}>
            {t("passkeyLabel")}
          </label>
          <input id="passkey-label" className={ui.input} maxLength={200} value={label} onChange={(e) => setLabel(e.target.value)} />
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={passwordless} onChange={(e) => setPasswordless(e.target.checked)} />
            {t("passkeyPasswordless")}
          </label>
          <button type="submit" className={`${ui.button} self-start`} disabled={busy}>
            {t("passkeyAdd")}
          </button>
        </form>
      ) : null}
    </section>
  );
}

export function ProfileSettings({
  displayName,
  email,
  roles,
  tenantName,
  initialSessions,
  initialDevices,
  totpEnabled,
  mfaRequired = false,
  signatureProfile = null,
  signaturePreview = null,
}: {
  displayName: string;
  email: string;
  roles: string[];
  tenantName: string;
  initialSessions: SessionRow[];
  initialDevices: TrustedDeviceRow[];
  totpEnabled: boolean;
  mfaRequired?: boolean;
  signatureProfile?: SignatureProfileData | null;
  signaturePreview?: SignaturePreviewData | null;
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
      <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="appearance-title">
        <h2 id="appearance-title" className={ui.h3}>
          {t("appearanceTitle")}
        </h2>
        <p className={ui.help}>{t("appearanceHelp")}</p>
        <ThemeSwitch className="self-start" />
      </section>
      <SignatureProfile initialProfile={signatureProfile} initialPreview={signaturePreview} />
      <PasswordForm />
      <SecondFactor initialEnabled={totpEnabled} required={mfaRequired} />
      <Passkeys />
      <Sessions initial={initialSessions} />
      <TrustedDevices initial={initialDevices} />
    </div>
  );
}

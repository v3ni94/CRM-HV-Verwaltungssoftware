"use client";

import type { components } from "@mhvp/api-client";
import { useFormatter, useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type TrustedDeviceRow = components["schemas"]["TrustedDeviceOut"];
type Setup = { secret: string; otpauth_uri: string; qr: string };

/** Optional second factor (operator 26.09.2026, M2-01): every portal user may switch TOTP on
 *  or off; the login asks for a code only while it is on, and not on a remembered device. */
function SecondFactor({ initialEnabled }: { initialEnabled: boolean }) {
  const t = useTranslations("Security");
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
    <section className={`${ui.card} ${ui.sectionGap}`} aria-labelledby="totp-title">
      <h2 id="totp-title" className={ui.h2}>
        {t("totpTitle")}
      </h2>
      <p className="text-sm text-muted">{enabled ? t("totpStatusOn") : t("totpStatusOff")}</p>
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
      {enabled ? (
        <form onSubmit={(e) => void disable(e)} className="flex flex-col gap-3 sm:max-w-sm">
          <p className={ui.help}>{t("totpDisableHint")}</p>
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
          <button type="submit" className={ui.secondary} disabled={busy}>
            {t("totpDisable")}
          </button>
        </form>
      ) : setup ? (
        <form onSubmit={(e) => void confirm(e)} className="flex flex-col gap-3 sm:max-w-sm">
          <p className={ui.help}>{t("totpSetupHint")}</p>
          {/* eslint-disable-next-line @next/next/no-img-element -- server generated data URL */}
          <img src={setup.qr} alt={t("totpQrAlt")} width={220} height={220} className="rounded bg-white p-1" />
          <p className={ui.label}>{t("totpSecretLabel")}</p>
          <code data-testid="totp-secret" className="select-all break-all rounded bg-surface px-2 py-1 font-mono text-sm">
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
        <div className="flex flex-col gap-2">
          <p className={ui.help}>{t("totpEnableHint")}</p>
          <button type="button" className={`${ui.primary} ${ui.actionFull}`} disabled={busy} onClick={() => void start()}>
            {t("totpEnable")}
          </button>
        </div>
      )}
    </section>
  );
}

function TrustedDevices({ initial }: { initial: TrustedDeviceRow[] }) {
  const t = useTranslations("Security");
  const format = useFormatter();
  const [devices, setDevices] = useState(initial);
  const [busyId, setBusyId] = useState<string | null>(null);
  const when = (value: string) =>
    format.dateTime(new Date(value), { day: "2-digit", month: "2-digit", year: "numeric" });

  async function revoke(id: string) {
    setBusyId(id);
    const res = await bff<null>(`/api/bff/auth/trusted-devices/${id}`, { method: "DELETE" });
    setBusyId(null);
    if (res.ok) setDevices((prev) => prev.filter((d) => d.id !== id));
  }

  return (
    <section className={`${ui.card} ${ui.sectionGap}`} aria-labelledby="devices-title">
      <h2 id="devices-title" className={ui.h2}>
        {t("devicesTitle")}
      </h2>
      <p className={ui.help}>{t("devicesHint")}</p>
      {devices.length === 0 ? (
        <p className="text-sm text-muted">{t("noDevices")}</p>
      ) : (
        <ul className="flex flex-col gap-2 text-sm">
          {devices.map((d) => (
            <li key={d.id} className="flex items-center justify-between gap-2 border-b border-border pb-2 last:border-0">
              <span className="text-muted">
                {d.label ?? t("unknownDevice")} · {t("deviceExpires")} {when(d.expires_at)}
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

export function SecuritySettings({
  totpEnabled,
  initialDevices,
}: {
  totpEnabled: boolean;
  initialDevices: TrustedDeviceRow[];
}) {
  return (
    <div className={ui.sectionGap}>
      <SecondFactor initialEnabled={totpEnabled} />
      <TrustedDevices initial={initialDevices} />
    </div>
  );
}

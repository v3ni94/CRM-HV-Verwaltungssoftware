"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { safeNext, withNext } from "@/lib/next-path";
import { ui } from "@/lib/ui";

type Setup = { secret: string; otpauth_uri: string; qr: string };
type Verified = { tenant_id: string | null; tenants: { id: string; name: string }[] };

/** M2-04: the tenant policy demands a second factor this user has not set up yet. The login
 *  continues here: scan the QR code (or type the key) into an authenticator app, confirm with
 *  the first code, and the session starts. Nothing is locked; leaving keeps the old state. */
export function MfaSetupForm({ next }: { next?: string }) {
  const t = useTranslations("Auth");
  const router = useRouter();
  const [setup, setSetup] = useState<Setup | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [rememberDevice, setRememberDevice] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void bff<Setup>("/api/session/mfa/setup", { method: "POST", body: "{}" }).then((res) => {
      if (cancelled) return;
      if (res.ok) setSetup(res.data);
      else setError(res.message);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!/^\d{6,8}$/.test(code.trim())) {
      setError(t("codeInvalid"));
      return;
    }
    setBusy(true);
    const result = await bff<Verified>("/api/session/mfa/setup/confirm", {
      method: "POST",
      body: JSON.stringify({ code: code.trim(), remember_device: rememberDevice }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    router.push(result.data.tenant_id ? safeNext(next) : withNext("/mandant", next));
    router.refresh();
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted">{t("mfaSetupHint")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {setup ? (
        <>
          {/* The QR image is a locally generated data URL; next/image adds nothing here. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={setup.qr} alt={t("mfaSetupQrAlt")} width={220} height={220} className="self-center rounded bg-paper p-1" />
          <p className={ui.label}>{t("mfaSetupSecret")}</p>
          <code data-testid="mfa-setup-secret" className="select-all break-all rounded bg-surface-2 px-2 py-1 font-mono text-sm">
            {setup.secret}
          </code>
          <form onSubmit={onSubmit} noValidate className="flex flex-col gap-3" aria-label={t("mfaSetupTitle")}>
            <div>
              <label htmlFor="setup-code" className={ui.label}>
                {t("code")}
              </label>
              <input
                id="setup-code"
                inputMode="numeric"
                autoComplete="one-time-code"
                autoFocus
                maxLength={8}
                className={`${ui.input} font-mono tracking-widest`}
                value={code}
                onChange={(e) => setCode(e.target.value)}
              />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={rememberDevice} onChange={(e) => setRememberDevice(e.target.checked)} />
              {t("rememberDevice")}
            </label>
            <button type="submit" className={ui.primary} disabled={busy}>
              {busy ? t("submitting") : t("mfaSetupConfirm")}
            </button>
          </form>
        </>
      ) : null}
      <Link href="/anmelden" className="text-sm text-muted underline">
        {t("backToLogin")}
      </Link>
    </div>
  );
}

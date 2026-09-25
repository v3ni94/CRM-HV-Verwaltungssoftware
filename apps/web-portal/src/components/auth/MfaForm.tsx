"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Setup = { secret: string; otpauth_uri: string; qr: string };
type Verified = { tenant_id: string | null; tenants: { id: string; name: string }[] };

export function MfaForm({ setup, next }: { setup: boolean; next?: string }) {
  const t = useTranslations("Auth");
  const router = useRouter();
  const [data, setData] = useState<Setup | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const started = useRef(false);

  useEffect(() => {
    // Each setup call creates a new secret: run it exactly once per page view.
    if (!setup || started.current) return;
    started.current = true;
    void bff<Setup>("/api/session/mfa/setup", { method: "POST", body: "{}" }).then((result) => {
      if (result.ok) setData(result.data);
      else setError(result.message);
    });
  }, [setup]);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!/^\d{6,8}$/.test(code.trim())) {
      setError(t("codeInvalid"));
      return;
    }
    setBusy(true);
    const result = await bff<Verified>("/api/session/mfa/verify", {
      method: "POST",
      body: JSON.stringify({ code: code.trim() }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    const target = next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
    // Portal users belong to exactly one tenant; without a tenant in the token nothing works.
    if (!result.data.tenant_id) {
      setError(t("noTenant"));
      return;
    }
    router.push(target);
    router.refresh();
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted">{setup ? t("mfaSetupHint") : t("mfaHint")}</p>
      {setup ? (
        data ? (
          <div className="flex flex-col items-start gap-2">
            {/* eslint-disable-next-line @next/next/no-img-element -- server generated data URL */}
            <img src={data.qr} alt={t("qrAlt")} width={220} height={220} className="rounded bg-white p-1" />
            <p className={ui.label}>{t("secretLabel")}</p>
            <code data-testid="totp-secret" className="select-all break-all rounded bg-surface px-2 py-1 font-mono text-sm">
              {data.secret}
            </code>
          </div>
        ) : !error ? (
          <p role="status" className="text-sm text-muted">
            {t("setupLoading")}
          </p>
        ) : null
      ) : null}
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-3">
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
        <div>
          <label htmlFor="code" className={ui.label}>
            {t("code")}
          </label>
          <input
            id="code"
            inputMode="numeric"
            autoComplete="one-time-code"
            autoFocus
            maxLength={8}
            className={`${ui.input} font-mono tracking-widest`}
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
        </div>
        <button type="submit" className={ui.primary} disabled={busy}>
          {busy ? t("submitting") : t("verify")}
        </button>
      </form>
      <Link href="/anmelden" className="text-sm text-muted underline">
        {t("backToLogin")}
      </Link>
    </div>
  );
}

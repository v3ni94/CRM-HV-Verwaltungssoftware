"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Verified = { tenant_id: string | null; tenants: { id: string; name: string }[] };

/** Login step 2 for users who enabled the second factor under Einstellungen, Sicherheit
 *  (operator 26.09.2026, M2-01: TOTP is optional; setup happens in the settings, not here). */
export function MfaForm({ next }: { next?: string }) {
  const t = useTranslations("Auth");
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [rememberDevice, setRememberDevice] = useState(false);
  const [busy, setBusy] = useState(false);
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
      body: JSON.stringify({ code: code.trim(), remember_device: rememberDevice }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    const target = next && next.startsWith("/") && !next.startsWith("//") ? next : "/kontakte";
    if (!result.data.tenant_id) {
      router.push(`/mandant?next=${encodeURIComponent(target)}`);
    } else {
      router.push(target);
    }
    router.refresh();
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted">{t("mfaHint")}</p>
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
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={rememberDevice}
            onChange={(e) => setRememberDevice(e.target.checked)}
          />
          {t("rememberDevice")}
        </label>
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

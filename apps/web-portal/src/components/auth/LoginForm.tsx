"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/**
 * Login step 1 (e-mail and password). Accounts without TOTP are signed in right away;
 * accounts with an MFA duty continue with the second factor on the next page.
 */
export function LoginForm({ next }: { next?: string }) {
  const t = useTranslations("Auth");
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    const errors: { email?: string; password?: string } = {};
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) errors.email = t("emailInvalid");
    if (!password) errors.password = t("passwordRequired");
    setFieldErrors(errors);
    if (errors.email || errors.password) return;
    setBusy(true);
    const result = await bff<{ status: string }>("/api/session/login", {
      method: "POST",
      body: JSON.stringify({ email: email.trim(), password }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    if (result.data.status === "ok") {
      const target = next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
      router.push(target);
      router.refresh();
      return;
    }
    // mfa_required / mfa_setup_required: continue with the TOTP step.
    const params = new URLSearchParams();
    if (result.data.status === "mfa_setup_required") params.set("einrichten", "1");
    if (next) params.set("next", next);
    const query = params.toString();
    router.push(`/anmelden/zweiter-faktor${query ? `?${query}` : ""}`);
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-3" aria-label={t("loginTitle")}>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div>
        <label htmlFor="email" className={ui.label}>
          {t("email")}
        </label>
        <input
          id="email"
          type="email"
          autoComplete="username"
          autoFocus
          className={ui.input}
          aria-invalid={!!fieldErrors.email}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        {fieldErrors.email ? <p className={ui.error}>{fieldErrors.email}</p> : null}
      </div>
      <div>
        <label htmlFor="password" className={ui.label}>
          {t("password")}
        </label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          className={ui.input}
          aria-invalid={!!fieldErrors.password}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {fieldErrors.password ? <p className={ui.error}>{fieldErrors.password}</p> : null}
      </div>
      <button type="submit" className={ui.primary} disabled={busy}>
        {busy ? t("submitting") : t("submit")}
      </button>
      <Link href="/einladung" className="text-sm text-muted underline-offset-2 hover:text-fg hover:underline">
        {t("inviteLink")}
      </Link>
    </form>
  );
}

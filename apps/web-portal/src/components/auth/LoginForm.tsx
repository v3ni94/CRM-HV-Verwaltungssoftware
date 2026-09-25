"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export function LoginForm({ next }: { next?: string }) {
  const t = useTranslations("Auth");
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({});
  const [error, setError] = useState<string | null>(null);
  const [mfa, setMfa] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setMfa(false);
    const errors: { email?: string; password?: string } = {};
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) errors.email = t("emailInvalid");
    if (!password) errors.password = t("passwordRequired");
    setFieldErrors(errors);
    if (errors.email || errors.password) return;
    setSubmitting(true);
    const result = await bff<{ status: string }>("/api/session/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setSubmitting(false);
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
    // mfa_required / mfa_setup_required: the portal offers no TOTP step.
    setMfa(true);
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-3" aria-label={t("loginTitle")}>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {mfa ? (
        <p role="alert" className={ui.notice}>
          {t("mfaHint")}
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
      <button type="submit" className={ui.primary} disabled={submitting}>
        {submitting ? t("submitting") : t("submit")}
      </button>
      <Link href="/einladung" className="text-sm text-muted underline-offset-2 hover:text-fg hover:underline">
        {t("inviteLink")}
      </Link>
    </form>
  );
}

"use client";

import Link from "next/link";
import { useState } from "react";
import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export function InviteForm() {
  const t = useTranslations("Auth");
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [fieldErrors, setFieldErrors] = useState<{ token?: string; password?: string; repeat?: string }>({});
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    const errors: { token?: string; password?: string; repeat?: string } = {};
    if (token.trim().length < 10) errors.token = t("inviteTokenRequired");
    if (!password) errors.password = t("passwordRequired");
    if (password !== repeat) errors.repeat = t("passwordMismatch");
    setFieldErrors(errors);
    if (errors.token || errors.password || errors.repeat) return;
    setSubmitting(true);
    const result = await bff<{ status: string }>("/api/session/einladung", {
      method: "POST",
      body: JSON.stringify({ token: token.trim(), password }),
    });
    setSubmitting(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setDone(true);
  }

  if (done) {
    return (
      <div className="flex flex-col gap-4">
        <p role="status" className={ui.success}>
          {t("inviteSuccess")}
        </p>
        <Link href="/anmelden" className={ui.primary}>
          {t("toLogin")}
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-3" aria-label={t("inviteTitle")}>
      <p className="text-sm text-muted">{t("inviteIntro")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div>
        <label htmlFor="token" className={ui.label}>
          {t("inviteToken")}
        </label>
        <input
          id="token"
          type="text"
          autoComplete="off"
          autoFocus
          className={ui.input}
          aria-invalid={!!fieldErrors.token}
          value={token}
          onChange={(e) => setToken(e.target.value)}
        />
        {fieldErrors.token ? <p className={ui.error}>{fieldErrors.token}</p> : null}
      </div>
      <div>
        <label htmlFor="password" className={ui.label}>
          {t("newPassword")}
        </label>
        <input
          id="password"
          type="password"
          autoComplete="new-password"
          className={ui.input}
          aria-invalid={!!fieldErrors.password}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {fieldErrors.password ? <p className={ui.error}>{fieldErrors.password}</p> : null}
      </div>
      <div>
        <label htmlFor="repeat" className={ui.label}>
          {t("newPasswordRepeat")}
        </label>
        <input
          id="repeat"
          type="password"
          autoComplete="new-password"
          className={ui.input}
          aria-invalid={!!fieldErrors.repeat}
          value={repeat}
          onChange={(e) => setRepeat(e.target.value)}
        />
        {fieldErrors.repeat ? <p className={ui.error}>{fieldErrors.repeat}</p> : null}
      </div>
      <button type="submit" className={ui.primary} disabled={submitting}>
        {submitting ? t("submitting") : t("inviteSubmit")}
      </button>
      <Link href="/anmelden" className="text-sm text-muted underline-offset-2 hover:text-fg hover:underline">
        {t("loginLink")}
      </Link>
    </form>
  );
}

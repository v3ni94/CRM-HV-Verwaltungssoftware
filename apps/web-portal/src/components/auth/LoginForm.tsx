"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Login step 1 (e-mail and password); the second factor follows on the next page. */
export function LoginForm({ next }: { next?: string }) {
  const t = useTranslations("Auth");
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())) {
      setError(t("emailInvalid"));
      return;
    }
    if (!password) {
      setError(t("passwordRequired"));
      return;
    }
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
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
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
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </div>
      <button type="submit" className={ui.primary} disabled={busy}>
        {busy ? t("submitting") : t("submit")}
      </button>
    </form>
  );
}

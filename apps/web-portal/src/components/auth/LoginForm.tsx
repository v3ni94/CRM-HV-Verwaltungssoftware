"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { adoptAccountLocale } from "@/lib/locale-sync";
import { ui } from "@/lib/ui";

import { MagicLinkForm } from "./MagicLinkForm";

/** Login step 1 (e-mail and password); the second factor follows on the next page. Offers the
 *  magic link (M21-01) as an alternative, next to the password (never a replacement). */
export function LoginForm({ next }: { next?: string }) {
  const t = useTranslations("Auth");
  const [mode, setMode] = useState<"password" | "magic-link">("password");
  if (mode === "magic-link") {
    return (
      <div className="flex flex-col gap-3">
        <MagicLinkForm />
        <button
          type="button"
          className="text-xs text-accent-strong underline underline-offset-2 hover:no-underline"
          onClick={() => setMode("password")}
        >
          {t("magicLink.backToPassword")}
        </button>
      </div>
    );
  }
  return <PasswordLoginForm next={next} onMagicLink={() => setMode("magic-link")} />;
}

function PasswordLoginForm({ next, onMagicLink }: { next?: string; onMagicLink: () => void }) {
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
    if (result.data.status === "ok") {
      // Password alone was enough (no second factor enabled, or a remembered device): the
      // session cookies are already set, no second factor step needed.
      const target = next && next.startsWith("/") && !next.startsWith("//") ? next : "/start";
      await adoptAccountLocale();
      router.push(target);
      router.refresh();
      return;
    }
    const params = new URLSearchParams();
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
      <button type="button" className="text-xs text-accent-strong underline underline-offset-2 hover:no-underline" onClick={onMagicLink}>
        {t("magicLink.useInstead")}
      </button>
    </form>
  );
}

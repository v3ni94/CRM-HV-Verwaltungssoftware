"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** M21-01: requests a one time login link by e-mail, as an alternative to the password. The
 *  answer is identical whether or not the address has a portal account (no enumeration), so the
 *  form always shows the same confirmation. */
export function MagicLinkForm() {
  const t = useTranslations("Auth");
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())) {
      setError(t("emailInvalid"));
      return;
    }
    setBusy(true);
    const result = await bff<null>("/api/session/magic-link/request", {
      method: "POST",
      body: JSON.stringify({ email: email.trim() }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setSent(true);
  }

  if (sent) {
    return (
      <p className={ui.success} role="status" data-testid="magic-link-sent">
        {t("magicLink.sent")}
      </p>
    );
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-3" aria-label={t("magicLink.title")}>
      <p className="text-sm text-muted">{t("magicLink.hint")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div>
        <label htmlFor="magic-link-email" className={ui.label}>
          {t("email")}
        </label>
        <input
          id="magic-link-email"
          type="email"
          autoComplete="username"
          autoFocus
          className={ui.input}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </div>
      <button type="submit" className={ui.primary} disabled={busy}>
        {busy ? t("submitting") : t("magicLink.request")}
      </button>
    </form>
  );
}

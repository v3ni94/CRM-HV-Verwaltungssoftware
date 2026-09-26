"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Einladung annehmen (A56): Einladungscode (aus dem Link oder von Hand) und neues Passwort.
 *  Danach folgt die normale Anmeldung mit E-Mail und Passwort. */
export function InvitationForm({ code }: { code?: string }) {
  const t = useTranslations("Invitation");
  const router = useRouter();
  const [token, setToken] = useState(code ?? "");
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (token.trim().length < 10) {
      setError(t("codeRequired"));
      return;
    }
    if (password.length < 12) {
      setError(t("passwordTooShort"));
      return;
    }
    if (password !== repeat) {
      setError(t("passwordMismatch"));
      return;
    }
    setBusy(true);
    const result = await bff<{ status: string }>("/api/session/invitation", {
      method: "POST",
      body: JSON.stringify({ token: token.trim(), password }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setDone(true);
    setPassword("");
    setRepeat("");
  }

  if (done) {
    return (
      <div className="flex flex-col gap-3">
        <p className={ui.success} role="status">
          {t("done")}
        </p>
        <button type="button" className={ui.primary} onClick={() => router.push("/anmelden")}>
          {t("toLogin")}
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} noValidate aria-busy={busy} className="flex flex-col gap-3" aria-label={t("title")}>
      <p className="text-sm text-muted">{t("hint")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div>
        <label htmlFor="invitation-code" className={ui.label}>
          {t("code")}
        </label>
        <input id="invitation-code" className={ui.input} autoComplete="off" aria-required="true" value={token} onChange={(e) => setToken(e.target.value)} />
      </div>
      <div>
        <label htmlFor="invitation-password" className={ui.label}>
          {t("password")}
        </label>
        <input
          id="invitation-password"
          type="password"
          aria-required="true"
          autoComplete="new-password"
          className={ui.input}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </div>
      <div>
        <label htmlFor="invitation-repeat" className={ui.label}>
          {t("passwordRepeat")}
        </label>
        <input
          id="invitation-repeat"
          type="password"
          aria-required="true"
          autoComplete="new-password"
          className={ui.input}
          value={repeat}
          onChange={(e) => setRepeat(e.target.value)}
        />
      </div>
      <button type="submit" className={ui.primary} disabled={busy}>
        {busy ? t("submitting") : t("submit")}
      </button>
    </form>
  );
}

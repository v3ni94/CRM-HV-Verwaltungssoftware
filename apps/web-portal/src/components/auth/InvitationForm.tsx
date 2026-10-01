"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

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
  // AC06: once the tenant has published terms, the API answers MHVP-CONT-0020 and names the
  // version; the form then asks for the acceptance and sends it with the next attempt.
  const [termsVersion, setTermsVersion] = useState<string | null>(null);
  const [termsAccepted, setTermsAccepted] = useState(false);

  // AD03-01 / AE34: the invitation code starts with the tenant id (32 hex characters); with it
  // the published terms version is read from the public endpoint before the form is sent, so
  // the acceptance is visible from the start. A miss changes nothing: the MHVP-CONT-0020 answer
  // below remains the fallback.
  const tenantId = /^([0-9a-f]{32})\./i.exec(token.trim())?.[1]?.toLowerCase() ?? null;
  useEffect(() => {
    if (!tenantId) return;
    let cancelled = false;
    void bff<{ terms_version: string }>(`/api/session/terms?tenant=${tenantId}`).then((result) => {
      if (!cancelled && result.ok && result.data.terms_version) setTermsVersion(result.data.terms_version);
    });
    return () => {
      cancelled = true;
    };
  }, [tenantId]);

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
    if (termsVersion && !termsAccepted) {
      setError(t("termsNeeded"));
      return;
    }
    setBusy(true);
    const result = await bff<{ status: string }>("/api/session/invitation", {
      method: "POST",
      body: JSON.stringify({
        token: token.trim(),
        password,
        ...(termsVersion && termsAccepted ? { accept_terms: true, terms_version: termsVersion } : {}),
      }),
    });
    setBusy(false);
    if (!result.ok) {
      if (result.problem?.code === "MHVP-CONT-0020") {
        const version = /Fassung\s+(\S+?)\s+annehmen/.exec(result.problem.detail ?? "")?.[1];
        setTermsVersion(version ?? null);
        setError(version ? t("termsNeeded") : t("termsMissingVersion"));
        return;
      }
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
      {termsVersion ? (
        <label className="flex items-start gap-2 text-sm">
          <input type="checkbox" className="mt-1" checked={termsAccepted} onChange={(e) => setTermsAccepted(e.target.checked)} />
          <span>{t("termsAccept", { version: termsVersion })}</span>
        </label>
      ) : null}
      {termsVersion ? <p className="text-xs text-muted">{t("termsEvidence")}</p> : null}
      <button type="submit" className={ui.primary} disabled={busy}>
        {busy ? t("submitting") : t("submit")}
      </button>
    </form>
  );
}

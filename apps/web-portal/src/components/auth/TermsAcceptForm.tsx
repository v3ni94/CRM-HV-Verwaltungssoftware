"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Annahmemaske der Nutzungsbedingungen (AC06, GA02-06, MHVP-CONT-0020): zeigt die
 *  veröffentlichte Fassung und nimmt sie per POST /portal/terms/accept an. Den Text der
 *  Nutzungsbedingungen legt der Mandant fest (offene Entscheidung AC06-03), hier steht nur
 *  die Annahme der Fassung. */
export function TermsAcceptForm({ version, next = "/start" }: { version: string; next?: string }) {
  const t = useTranslations("Terms");
  const router = useRouter();
  const [accepted, setAccepted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!accepted) {
      setError(t("mustAccept"));
      return;
    }
    setBusy(true);
    const result = await bff<{ accepted: boolean }>("/api/bff/portal/terms/accept", {
      method: "POST",
      body: JSON.stringify({ accept_terms: true, terms_version: version }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    router.push(next);
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} noValidate aria-busy={busy} className="flex flex-col gap-3" aria-label={t("title")}>
      <p className="text-sm text-muted">{t("hint")}</p>
      <p className="text-sm font-medium">{t("version", { version })}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" className="mt-1" checked={accepted} onChange={(e) => setAccepted(e.target.checked)} />
        <span>{t("accept")}</span>
      </label>
      <p className="text-xs text-muted">{t("evidence")}</p>
      <button type="submit" className={ui.primary} disabled={busy}>
        {busy ? t("submitting") : t("submit")}
      </button>
    </form>
  );
}

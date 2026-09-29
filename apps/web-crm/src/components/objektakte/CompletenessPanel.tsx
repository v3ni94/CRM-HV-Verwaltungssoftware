"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { LetterRecordForm } from "@/components/documents/LetterRecordForm";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type MissingClass = { document_category_id: string; code: string; name: string };
type Completeness = {
  property_id: string;
  management_type: string;
  missing: MissingClass[];
  satisfied: MissingClass[];
};

/** M35 Stufe 3 part 4 (Vollständigkeitsprüfung): additive Karte auf der Objektseite, zeigt
 * fehlende Pflichtunterlagen je Verwaltungsart und erzeugt bei Bedarf einen
 * Nachforderungsschreiben-Entwurf (nur Text, wird nie automatisch versendet). Mit
 * `canCreateLetter` (documents:create) zusätzlich das Schreiben auf dem Briefbogen als PDF
 * mit Versandnachweis und Ticketbezug (M12 Lücken, 29.09.2026); der Versand selbst bleibt
 * außerhalb der Plattform beziehungsweise hinter der Mailfreigabe. */
export function CompletenessPanel({ propertyId, canCreateLetter = false }: { propertyId: string; canCreateLetter?: boolean }) {
  const t = useTranslations("Objektakte");
  const [result, setResult] = useState<Completeness | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showLetter, setShowLetter] = useState(false);

  useEffect(() => {
    void (async () => {
      const res = await bff<Completeness>(
        `/api/bff/objektakte/properties/${propertyId}/completeness`,
      );
      if (res.ok) setResult(res.data);
      else setError(res.message);
    })();
  }, [propertyId]);

  const requestDraft = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<{ draft: boolean; text: string | null }>(
      `/api/bff/objektakte/properties/${propertyId}/completeness/nachforderungsschreiben`,
      { method: "POST" },
    );
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setDraft(res.data.text);
  };

  if (error) {
    return (
      <p role="alert" className={ui.alert}>
        {error}
      </p>
    );
  }
  if (!result) return null;

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-label={t("completeness.title")}>
      <h2 className="text-sm font-semibold">{t("completeness.title")}</h2>
      {result.missing.length === 0 ? (
        <p className="text-sm text-muted">{t("completeness.complete")}</p>
      ) : (
        <>
          <ul className="flex flex-col gap-1">
            {result.missing.map((m) => (
              <li key={m.document_category_id} className="text-sm">
                {m.name}
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap gap-2">
            <button type="button" className={ui.buttonSm} onClick={() => void requestDraft()} disabled={busy}>
              {t("completeness.draftAction")}
            </button>
            <button type="button" className={ui.buttonSm} onClick={() => setShowLetter((v) => !v)} data-testid="completeness-letter-toggle">
              {t("completeness.letterAnchor")}
            </button>
          </div>
        </>
      )}
      <div id="objektakte-letter">
        {showLetter && result.missing.length > 0 ? (
          <LetterRecordForm
            path={`objektakte/properties/${propertyId}/completeness/nachforderungsschreiben/pdf`}
            recipient={{ kind: "search" }}
            canCreate={canCreateLetter}
            requiredPermission="documents:create"
          />
        ) : null}
      </div>
      {result.satisfied.length > 0 ? (
        <p className="text-xs text-muted">
          {t("completeness.satisfiedCount", { count: result.satisfied.length })}
        </p>
      ) : null}
      {draft ? (
        <div className="rounded-md border border-border p-3">
          <p className="mhvp-label mb-2">{t("completeness.draftLabel")}</p>
          <pre className="whitespace-pre-wrap text-sm">{draft}</pre>
        </div>
      ) : null}
    </section>
  );
}

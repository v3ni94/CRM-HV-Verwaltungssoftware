"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type Candidate = { open_item_id: string; remaining: string; reasons: string[]; allocation_reason?: string };
type CandidatesOut = { candidates: Candidate[] };

/** Marker texts of `banking/allocation.py` (REASON_DETERMINED, REASON_LOCATION_MISMATCH). */
export const REASON_DETERMINED = "Bestimmung aus Verwendungszweck";
export const REASON_LOCATION_MISMATCH = "Einheit oder Objekt im Verwendungszweck weicht ab";

export type DeterminationState = { conflict: boolean; reason: string };

/** Tilgungsbestimmung des Zahlers (GAM-202, D39, 7.4 Nr. 5): zeigt, welche offenen Posten der
 *  Verwendungszweck serverseitig bestimmt (Rechnungs- oder Sollstellungsnummer, Periode, Einheit).
 *  Wählt die Person andere Posten, erscheint ein Prüfhinweis mit Begründungspflicht. Die
 *  Begründung wird dem Buchungstext vorangestellt; die API prüft die Zuordnung weiter selbst. */
export function AllocationDetermination({
  txId,
  selectedItemIds,
  onChange,
}: {
  txId: string;
  selectedItemIds: string[];
  onChange: (state: DeterminationState) => void;
}) {
  const t = useTranslations("BankActions.determination");
  const [candidates, setCandidates] = useState<Candidate[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState("");

  useEffect(() => {
    let cancelled = false;
    void bff<CandidatesOut>(`/api/bff/banking/transactions/${txId}/candidates`).then((res) => {
      if (cancelled) return;
      if (res.ok) setCandidates(res.data.candidates ?? []);
      else setError(res.message);
    });
    return () => {
      cancelled = true;
    };
  }, [txId]);

  const determined = (candidates ?? []).filter((c) => c.allocation_reason === REASON_DETERMINED || c.reasons.includes(REASON_DETERMINED));
  const determinedIds = new Set(determined.map((c) => c.open_item_id));
  const deviating = determined.length > 0 && selectedItemIds.length > 0 && selectedItemIds.some((id) => !determinedIds.has(id));
  const missingDetermined = determined.length > 0 && selectedItemIds.length > 0 && determined.some((c) => !selectedItemIds.includes(c.open_item_id));
  const conflict = deviating || missingDetermined;

  useEffect(() => {
    onChange({ conflict, reason: reason.trim() });
  }, [conflict, reason, onChange]);

  if (error) return <p className="text-xs text-muted">{t("unavailable")}</p>;
  if (candidates === null) return null;
  if (determined.length === 0) {
    return (
      <section className="mt-4 flex flex-col gap-1" data-testid="allocation-determination">
        <h3 className={ui.h3}>{t("title")}</h3>
        <p className="text-xs text-muted">{t("none")}</p>
      </section>
    );
  }
  return (
    <section className="mt-4 flex flex-col gap-1" data-testid="allocation-determination">
      <h3 className={ui.h3}>{t("title")}</h3>
      <p className="text-xs text-muted">{t("hint")}</p>
      <ul className="flex flex-col gap-1 text-xs">
        {determined.map((c) => (
          <li key={c.open_item_id} className="rounded border border-border p-1">
            <span className="font-medium">{t("remaining", { amount: formatEur(c.remaining) })}</span>
            {selectedItemIds.includes(c.open_item_id) ? <span className={`ml-2 ${ui.badgeInfo}`}>{t("selected")}</span> : null}
            <ul className="ml-4 list-disc text-muted">
              {c.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
            {c.reasons.includes(REASON_LOCATION_MISMATCH) ? <span className="text-warning-fg">{t("locationMismatch")}</span> : null}
          </li>
        ))}
      </ul>
      {conflict ? (
        <div className="flex flex-col gap-1" data-testid="determination-conflict">
          <p className="text-xs text-warning-fg" role="note">
            {t("conflict")}
          </p>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("reasonLabel")}</span>
            <input className={ui.input} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
        </div>
      ) : null}
    </section>
  );
}

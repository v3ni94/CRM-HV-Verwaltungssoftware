"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { MajorityCheckLine, type MajorityCheck } from "@/components/hoa/MajorityCheckLine";
import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

/** Mirrors mhvp.hoa.correction.CORRECTION_REASONS. */
export const CORRECTION_REASONS = ["resolution_changed", "court_invalid", "calculation_error", "other"] as const;

type ResolutionOption = { id: string; number: number | string | null; subject: string; decided_on: string | null };
type NewVersionOut = { id: string; version: number; correction_majority_check: MajorityCheck | null };

/**
 * GAH-402 (AH05): "Neue Version" einer WEG-Jahresabrechnung mit Korrekturgrund, Grundlage und
 * optionalem Korrekturbeschluss derselben GdWE. Zeigt die Mehrheitsprüfung des Beschlusses an
 * (nur Anzeigevermerk, kein Statuswechsel).
 */
export function StatementNewVersionDialog({
  statementId,
  legalEntityId,
  disabled,
}: {
  statementId: string;
  legalEntityId: string;
  disabled?: boolean;
}) {
  const t = useTranslations("HoaNewVersion");
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [basis, setBasis] = useState("");
  const [resolutionId, setResolutionId] = useState("");
  const [resolutions, setResolutions] = useState<ResolutionOption[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<NewVersionOut | null>(null);

  useEffect(() => {
    if (!open || !legalEntityId) return;
    let active = true;
    void bff<ResolutionOption[]>(`/api/bff/hoa/resolutions?legal_entity_id=${encodeURIComponent(legalEntityId)}`).then(
      (r) => {
        if (!active) return;
        if (r.ok) setResolutions(r.data);
        else setError(t("loadFailed"));
      },
    );
    return () => {
      active = false;
    };
  }, [open, legalEntityId, t]);

  const submit = async () => {
    setBusy(true);
    setError(null);
    const body: Record<string, string> = {};
    if (reason) body.reason = reason;
    if (basis.trim()) body.basis = basis.trim();
    if (resolutionId) body.resolution_id = resolutionId;
    const res = await bff<NewVersionOut>(`/api/bff/hoa/statements/${statementId}/new-version`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setResult(res.data);
    setOpen(false);
    router.refresh();
  };

  return (
    <div className="flex flex-col gap-2" data-testid="statement-new-version">
      {!open ? (
        <button type="button" className={ui.button} onClick={() => setOpen(true)} disabled={disabled || busy}>
          {t("open")}
        </button>
      ) : (
        <div role="dialog" aria-label={t("title")} className="flex flex-col gap-2 rounded border p-3">
          <span className="font-medium">{t("title")}</span>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("reason")}</span>
            <select className={ui.input} value={reason} onChange={(e) => setReason(e.target.value)}>
              <option value="">{t("reasonNone")}</option>
              {CORRECTION_REASONS.map((r) => (
                <option key={r} value={r}>
                  {t(`reasons.${r}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("basis")}</span>
            <textarea className={ui.input} maxLength={2000} value={basis} onChange={(e) => setBasis(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("resolution")}</span>
            <select className={ui.input} value={resolutionId} onChange={(e) => setResolutionId(e.target.value)}>
              <option value="">{t("resolutionNone")}</option>
              {resolutions.map((r) => (
                <option key={r.id} value={r.id}>
                  {`${r.number ?? ""} ${r.subject}${r.decided_on ? ` (${formatDate(r.decided_on)})` : ""}`.trim()}
                </option>
              ))}
            </select>
          </label>
          <span className={ui.help}>{t("resolutionHint")}</span>
          <div className="flex gap-2">
            <button type="button" className={ui.primary} onClick={submit} disabled={busy}>
              {t("submit")}
            </button>
            <button type="button" className={ui.button} onClick={() => setOpen(false)} disabled={busy}>
              {t("cancel")}
            </button>
          </div>
        </div>
      )}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {result ? (
        <div className="flex flex-col gap-1" role="status">
          <span className="text-sm">{t("created", { version: result.version })}</span>
          {result.correction_majority_check ? <MajorityCheckLine check={result.correction_majority_check} /> : null}
        </div>
      ) : null}
    </div>
  );
}

"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

type ResolutionRow = { id: string; number: number; decided_on: string | null; subject: string; status: string };

/** Auswahlfeld Beschluss für die Startregel Beschluss (V03, U11-01): setzt
 *  `retention_resolution_id` des Dokuments. Es wird nur ein vorhandener Beschluss der
 *  Beschluss-Sammlung des Rechtsträgers verknüpft; die Frist berechnet der Server. */
export function RetentionResolutionSelect({
  documentId,
  legalEntityId,
  current,
  onSaved,
}: {
  documentId: string;
  legalEntityId: string;
  current: string | null;
  onSaved?: (resolutionId: string | null) => void;
}) {
  const t = useTranslations("RetentionStatus");
  const [rows, setRows] = useState<ResolutionRow[] | null>(null);
  const [value, setValue] = useState(current ?? "");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    void bff<ResolutionRow[]>(`/api/bff/hoa/resolutions?legal_entity_id=${encodeURIComponent(legalEntityId)}`).then((res) => {
      if (!active) return;
      if (res.ok) setRows(res.data);
      else setError(t("resolutionError"));
    });
    return () => {
      active = false;
    };
  }, [legalEntityId, t]);

  const save = async () => {
    setBusy(true);
    setError(null);
    setMessage(null);
    const res = await bff(`/api/bff/documents/${encodeURIComponent(documentId)}`, {
      method: "PATCH",
      body: JSON.stringify({ retention_resolution_id: value || null }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setMessage(t("resolutionSaved"));
    onSaved?.(value || null);
  };

  return (
    <div className="mt-2 flex flex-col gap-1 text-sm" data-testid="retention-resolution-select">
      <label className="flex flex-col">
        {t("resolutionPick")}
        <select className={ui.input} value={value} onChange={(e) => setValue(e.target.value)} disabled={rows === null}>
          <option value="">{t("resolutionNone")}</option>
          {(rows ?? []).map((r) => (
            <option key={r.id} value={r.id}>
              {t("resolutionOption", {
                number: r.number,
                date: r.decided_on ? formatDate(r.decided_on) : "",
                subject: r.subject,
              })}
            </option>
          ))}
        </select>
      </label>
      <p className="text-xs text-muted">{t("resolutionHint")}</p>
      <div>
        <button type="button" className={ui.button} disabled={busy || value === (current ?? "")} onClick={() => void save()}>
          {t("resolutionSave")}
        </button>
      </div>
      {message ? <p role="status">{message}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </div>
  );
}

"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

import { RetentionResolutionSelect } from "./RetentionResolutionSelect";

/** GET /documents/{id}/retention-status (S711-06, U11-01). */
export type RetentionStatus = {
  document_id: string;
  retention_until: string | null;
  retention_hold_reason: string | null;
  retention_hold_kind: string | null;
  procedure_hold: string | null;
  ticket_hold: string | null;
  permanent_record: boolean;
  deletion_blocker: string | null;
  retention_resolution_id?: string | null;
  hold_set_by_four_eyes_required?: boolean;
};

type Loaded = { state: "loading" } | { state: "error" } | { state: "ready"; data: RetentionStatus };

const KINDS = ["litigation", "tax_procedure", "evidence", "legal_matter", "other"];

/** Lock status of a document: period end, reason of every hold (manual, ticket, automatic
 *  procedure, permanent record) and the four eyes note. GAG-26: a manual hold is set with
 *  `documents:update` (POST /documents/{id}/hold, reason and kind) and lifted with
 *  `documents:approve` (DELETE, reason); the API refuses lifting by the person who set it. */
export function RetentionStatusCard({
  documentId,
  legalEntityId,
  canSetHold = false,
  canClearHold = false,
}: {
  documentId: string;
  legalEntityId?: string | null;
  canSetHold?: boolean;
  canClearHold?: boolean;
}) {
  const t = useTranslations("RetentionStatus");
  const [loaded, setLoaded] = useState<Loaded>({ state: "loading" });
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let active = true;
    void bff<RetentionStatus>(`/api/bff/documents/${encodeURIComponent(documentId)}/retention-status`).then((res) => {
      if (active) setLoaded(res.ok && res.data ? { state: "ready", data: res.data } : { state: "error" });
    });
    return () => {
      active = false;
    };
  }, [documentId, reload]);

  if (loaded.state === "loading") return <p className={ui.help}>{t("loading")}</p>;
  if (loaded.state === "error")
    return (
      <p role="alert" className={ui.alert}>
        {t("unavailable")}
      </p>
    );
  const d = loaded.data;
  const holds: { key: string; label: string; reason: string }[] = [];
  if (d.retention_hold_reason) holds.push({ key: "manual", label: t("manualHold"), reason: d.retention_hold_reason });
  if (d.ticket_hold) holds.push({ key: "ticket", label: t("ticketHold"), reason: d.ticket_hold });
  if (d.procedure_hold) holds.push({ key: "procedure", label: t("procedureHold"), reason: d.procedure_hold });
  if (d.permanent_record) holds.push({ key: "permanent", label: t("permanent"), reason: "" });
  const kind = d.retention_hold_kind && KINDS.includes(d.retention_hold_kind) ? t(`kind.${d.retention_hold_kind}`) : d.retention_hold_kind;
  return (
    <section className={ui.card} data-testid="retention-status">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className="mt-1 text-sm tabular-nums">
        {t("until")}: {d.retention_until ? formatDate(d.retention_until) : t("untilNone")}
      </p>
      {d.retention_resolution_id ? (
        <p className="text-xs text-subtle" data-testid="retention-resolution">
          {t("resolution")}: {t("resolutionRef", { id: d.retention_resolution_id })}
        </p>
      ) : null}
      {legalEntityId ? (
        <RetentionResolutionSelect
          documentId={documentId}
          legalEntityId={legalEntityId}
          current={d.retention_resolution_id ?? null}
        />
      ) : null}
      {holds.length === 0 ? (
        <p className="mt-1 text-sm">{t("none")}</p>
      ) : (
        <ul className="mt-1 flex flex-col gap-1 text-sm" data-testid="retention-holds">
          {holds.map((h) => (
            <li key={h.key}>
              <span className={ui.badgeGold}>{h.label}</span>
              {h.reason ? ` ${h.reason}` : ""}
            </li>
          ))}
        </ul>
      )}
      {d.retention_hold_reason && kind ? <p className="text-xs text-subtle">{t("holdKind", { kind })}</p> : null}
      <p className="mt-2 text-sm" data-testid="retention-blocker">
        {d.deletion_blocker ? t("blocked", { reason: d.deletion_blocker }) : t("deletable")}
      </p>
      {canSetHold && !d.retention_hold_reason ? (
        <HoldForm documentId={documentId} mode="set" onDone={() => setReload((n) => n + 1)} />
      ) : null}
      {canClearHold && d.retention_hold_reason ? (
        <HoldForm documentId={documentId} mode="clear" onDone={() => setReload((n) => n + 1)} />
      ) : null}
      {d.hold_set_by_four_eyes_required ? (
        <p className={ui.notice} data-testid="retention-four-eyes">
          {t("fourEyes")}
        </p>
      ) : null}
    </section>
  );
}

/** Set (reason and kind) or lift (reason) the manual hold; the reason needs 5 to 500 chars. */
function HoldForm({ documentId, mode, onDone }: { documentId: string; mode: "set" | "clear"; onDone: () => void }) {
  const t = useTranslations("RetentionStatus");
  const [reason, setReason] = useState("");
  const [kind, setKind] = useState("other");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const valid = reason.trim().length >= 5 && reason.trim().length <= 500;

  const submit = async () => {
    setBusy(true);
    setError(null);
    const body = mode === "set" ? { reason: reason.trim(), kind } : { reason: reason.trim() };
    const res = await bff(`/api/bff/documents/${encodeURIComponent(documentId)}/hold`, {
      method: mode === "set" ? "POST" : "DELETE",
      body: JSON.stringify(body),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setReason("");
    onDone();
  };

  return (
    <div className="mt-3 flex flex-col gap-1 text-sm" data-testid={mode === "set" ? "retention-hold-set" : "retention-hold-clear"}>
      <p className={ui.subtitle}>{mode === "set" ? t("holdSetTitle") : t("holdClearTitle")}</p>
      {mode === "set" ? (
        <label className="flex flex-col">
          {t("holdKindLabel")}
          <select className={ui.input} value={kind} onChange={(e) => setKind(e.target.value)}>
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {t(`kind.${k}`)}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      <label className="flex flex-col">
        {t("holdReasonLabel")}
        <textarea className={ui.input} value={reason} maxLength={500} rows={2} onChange={(e) => setReason(e.target.value)} />
      </label>
      <p className="text-xs text-muted">{mode === "set" ? t("holdSetHint") : t("holdClearHint")}</p>
      <div>
        <button type="button" className={ui.button} disabled={busy || !valid} onClick={() => void submit()}>
          {mode === "set" ? t("holdSet") : t("holdClear")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </div>
  );
}

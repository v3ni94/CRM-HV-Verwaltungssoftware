"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type ChangeRequestRow = {
  id: string;
  kind: string;
  status: "proposed" | "accepted" | "rejected" | string;
  payload: Record<string, string>;
  contact_id: string;
  created_at: string;
  decision_note: string | null;
  /** Belegentwurf einer angenommenen Rechnungseinreichung (Belegeingang). */
  receipt_draft_id?: string | null;
};

export type MandateProposalRow = {
  id: string;
  reference: string;
  creditor_id: string;
  holder: string;
  iban_masked: string;
  confirmed_at: string;
  status: "proposed" | "accepted" | "rejected" | string;
  evidence_document_id: string;
  decision_note: string | null;
  contact_bank_account_id: string | null;
};

type Loaded =
  | { state: "loading" }
  | { state: "error" }
  | { state: "ready"; requests: ChangeRequestRow[]; mandates: MandateProposalRow[] };

/** Vorschläge aus dem Portal für diesen Kontakt (M21-02 Adressänderung, M3-02 Portalstufe
 *  SEPA-Mandat): Liste mit Annehmen und Ablehnen. Das Annehmen eines Mandats legt nur eine
 *  Bankverbindung mit Mandatsnachweis an (IBAN bleibt bis zur Vier-Augen-Freigabe "zur
 *  Freigabe"), nie ein aktives Einzugsmandat (G2). */
export function PortalProposalsPanel({ contactId, canDecide }: { contactId: string; canDecide: boolean }) {
  const t = useTranslations("Contacts.portalProposals");
  const [loaded, setLoaded] = useState<Loaded>({ state: "loading" });
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    const [requests, mandates] = await Promise.all([
      bff<ChangeRequestRow[]>(`/api/bff/portal-admin/change-requests?contact_id=${encodeURIComponent(contactId)}`),
      bff<MandateProposalRow[]>(`/api/bff/portal-admin/sepa-mandate-proposals?contact_id=${encodeURIComponent(contactId)}`),
    ]);
    if (!requests.ok || !mandates.ok) {
      setLoaded({ state: "error" });
      return;
    }
    setLoaded({ state: "ready", requests: requests.data, mandates: mandates.data });
  }, [contactId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function decide(path: string, id: string, accept: boolean) {
    setBusy(id);
    setError(null);
    const result = await bff(`/api/bff/portal-admin/${path}/${id}/decide`, {
      method: "POST",
      body: JSON.stringify({ accept, note: notes[id]?.trim() || null }),
    });
    setBusy(null);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    await load();
  }

  function describe(row: ChangeRequestRow): string {
    const p = row.payload;
    if (row.kind === "address") {
      const line = [p.street, p.house_number].filter(Boolean).join(" ");
      const town = [p.postal_code, p.city].filter(Boolean).join(" ");
      return `${line}, ${town}${p.valid_from ? ` (${t("validFrom")} ${formatDate(p.valid_from)})` : ""}`;
    }
    return Object.entries(p)
      .map(([k, v]) => `${k}: ${v}`)
      .join(", ");
  }

  if (loaded.state === "loading") return <p className={ui.help}>{t("loading")}</p>;
  if (loaded.state === "error")
    return (
      <p role="alert" className={ui.alert}>
        {t("loadError")}
      </p>
    );
  const open = (s: string) => s === "proposed";
  const decision = (id: string, path: string) =>
    canDecide ? (
      <div className="mt-2 flex flex-wrap items-end gap-2">
        <div className="min-w-48 flex-1">
          <label htmlFor={`note-${id}`} className={ui.label}>
            {t("note")}
          </label>
          <input id={`note-${id}`} className={ui.input} value={notes[id] ?? ""} onChange={(e) => setNotes((prev) => ({ ...prev, [id]: e.target.value }))} />
        </div>
        <button type="button" className={ui.primary} disabled={busy === id} onClick={() => decide(path, id, true)}>
          {t("accept")}
        </button>
        <button type="button" className={ui.secondary} disabled={busy === id} onClick={() => decide(path, id, false)}>
          {t("reject")}
        </button>
      </div>
    ) : null;
  return (
    <div className="flex flex-col gap-4">
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <section>
        <h3 className={ui.h3}>{t("mandates")}</h3>
        <p className={ui.help}>{t("mandateHint")}</p>
        {loaded.mandates.length === 0 ? <p className={ui.help}>{t("noMandates")}</p> : null}
        <ul className="mt-2 flex flex-col gap-2">
          {loaded.mandates.map((m) => (
            <li key={m.id} className={ui.card}>
              <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                <span className="flex flex-col">
                  <span className={ui.mono}>{m.reference}</span>
                  <span className="text-xs text-muted">
                    {m.holder} · {m.iban_masked} · {t("creditorId")} {m.creditor_id}
                  </span>
                  <span className="text-xs text-muted">
                    {t("confirmedAt")} {formatDateTime(m.confirmed_at)}
                  </span>
                </span>
                <span className="flex items-center gap-2">
                  <span className="text-xs">{t(`status.${m.status}`)}</span>
                  <a href={`/dokumente/${m.evidence_document_id}`} className={ui.buttonSm}>
                    {t("evidence")}
                  </a>
                </span>
              </div>
              {open(m.status) ? decision(m.id, "sepa-mandate-proposals") : m.decision_note ? <p className="mt-1 text-xs text-muted">{m.decision_note}</p> : null}
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h3 className={ui.h3}>{t("changes")}</h3>
        {loaded.requests.length === 0 ? <p className={ui.help}>{t("noChanges")}</p> : null}
        <ul className="mt-2 flex flex-col gap-2">
          {loaded.requests.map((r) => (
            <li key={r.id} className={ui.card}>
              <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                <span className="flex flex-col">
                  <span className="font-medium">{t(`kind.${r.kind}`)}</span>
                  <span className="text-xs text-muted">{describe(r)}</span>
                  {r.payload.document_id ? (
                    <a href={`/dokumente/${r.payload.document_id}`} className="text-xs underline">
                      {t("evidence")}
                    </a>
                  ) : null}
                  {r.receipt_draft_id ? (
                    <a href={`/rechnungen/belegeingang?entwurf=${r.receipt_draft_id}`} className="text-xs underline" data-testid="receipt-draft-link">
                      {t("receiptDraft")}
                    </a>
                  ) : null}
                </span>
                <span className="text-xs">{t(`status.${r.status}`)}</span>
              </div>
              {open(r.status) ? decision(r.id, "change-requests") : r.decision_note ? <p className="mt-1 text-xs text-muted">{r.decision_note}</p> : null}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

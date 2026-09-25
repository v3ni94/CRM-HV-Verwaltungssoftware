"use client";

import type { components } from "@mhvp/api-client";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

type Mandate = components["schemas"]["MandateOut"];
type BankAccount = components["schemas"]["ContactOut"]["bank_accounts"][number];
type Party = components["schemas"]["PartyOut"];
type LegalEntity = { id: string; name: string };

const CHANNELS = ["phone", "letter", "email", "other"] as const;
type Channel = (typeof CHANNELS)[number];

/** SEPA mandates of a contact (M5): recording with evidence only, either an uploaded PDF or
 *  the recorded way of granting (channel plus note). Collecting stays locked until G2. */
export function SepaMandatePanel({
  bankAccounts,
  parties,
  legalEntities,
  mandates,
}: {
  bankAccounts: BankAccount[];
  parties: Party[];
  legalEntities: LegalEntity[];
  mandates: Mandate[];
}) {
  const t = useTranslations("Contacts.sepa");
  const tc = useTranslations("Contacts");
  const router = useRouter();
  const [bankAccountId, setBankAccountId] = useState(bankAccounts[0]?.id ?? "");
  const [partyId, setPartyId] = useState(parties[0]?.id ?? "");
  const [legalEntityId, setLegalEntityId] = useState("");
  const [reference, setReference] = useState("");
  const [creditorId, setCreditorId] = useState("");
  const [signedAt, setSignedAt] = useState("");
  const [evidenceKind, setEvidenceKind] = useState<"document" | "recorded">("document");
  const [file, setFile] = useState<File | null>(null);
  const [channel, setChannel] = useState<Channel>("email");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const accountLabel = (id: string) => {
    const a = bankAccounts.find((b) => b.id === id);
    return a ? [a.iban_masked, a.holder].filter(Boolean).join(", ") : id;
  };

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!bankAccountId || !partyId || !legalEntityId || !reference.trim() || !creditorId.trim() || !/^\d{4}-\d{2}-\d{2}$/.test(signedAt)) {
      setError(t("requiredMissing"));
      return;
    }
    if (evidenceKind === "document" && !file) {
      setError(t("fileMissing"));
      return;
    }
    setBusy(true);
    let documentId: string | null = null;
    if (evidenceKind === "document" && file) {
      const form = new FormData();
      form.append("file", file);
      const doc = await bff<{ id: string }>("/api/bff/documents", { method: "POST", body: form });
      if (!doc.ok) {
        setBusy(false);
        setError(doc.message);
        return;
      }
      documentId = doc.data.id;
    }
    const body: Record<string, unknown> = {
      party_id: partyId,
      legal_entity_id: legalEntityId,
      contact_bank_account_id: bankAccountId,
      reference: reference.trim(),
      creditor_id: creditorId.trim(),
      signed_at: signedAt,
      type: "core",
      sequence: "recurring",
    };
    if (documentId) body.document_id = documentId;
    else {
      body.evidence_channel = channel;
      if (note.trim()) body.evidence_note = note.trim();
    }
    const result = await bff<Mandate>("/api/bff/sepa-mandates", { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setReference("");
    setFile(null);
    setNote("");
    router.refresh();
  }

  async function revoke(id: string) {
    if (!window.confirm(t("revokeConfirm"))) return;
    setError(null);
    const result = await bff(`/api/bff/sepa-mandates/${id}/revoke`, { method: "POST" });
    if (!result.ok) {
      setError(result.message);
      return;
    }
    router.refresh();
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs text-muted">{t("lockedHint")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {mandates.length ? (
        <table className="w-full text-sm">
          <thead className="border-b border-border text-left text-xs text-muted">
            <tr>
              <th className="py-1 pr-3 font-medium">{t("reference")}</th>
              <th className="py-1 pr-3 font-medium">{t("creditorId")}</th>
              <th className="py-1 pr-3 font-medium">{t("bankAccount")}</th>
              <th className="py-1 pr-3 font-medium">{t("signedAt")}</th>
              <th className="py-1 pr-3 font-medium">{t("evidence")}</th>
              <th className="py-1 pr-3 font-medium">{t("status")}</th>
              <th className="py-1" />
            </tr>
          </thead>
          <tbody>
            {mandates.map((m) => (
              <tr key={m.id} className="border-b border-border">
                <td className="py-1 pr-3 font-mono">{m.reference}</td>
                <td className="py-1 pr-3 font-mono">{m.creditor_id}</td>
                <td className="py-1 pr-3 font-mono">{m.iban_masked ?? accountLabel(m.contact_bank_account_id)}</td>
                <td className="py-1 pr-3">{formatDate(m.signed_at)}</td>
                <td className="py-1 pr-3">
                  {m.document_id ? (
                    // conditional: no document download route in the CRM yet (reads stay
                    // outside the BFF allowlist), so the stored PDF is only referenced.
                    <span title={m.document_id}>{t("evidencePdf")}</span>
                  ) : (
                    <>
                      {t("evidenceRecorded", {
                        channel: t(`channel.${(m.evidence_channel as Channel | null) ?? "other"}`),
                        date: formatDate(m.signed_at),
                      })}
                      {m.evidence_note ? <span className="text-xs text-muted"> ({m.evidence_note})</span> : null}
                      <br />
                      <span className="text-xs text-muted">{t("recordedHint")}</span>
                    </>
                  )}
                </td>
                <td className="py-1 pr-3">{t(`statusValue.${m.status}`)}</td>
                <td className="py-1 text-right">
                  {m.status === "active" ? (
                    <button type="button" className={ui.button} onClick={() => void revoke(m.id)}>
                      {t("revoke")}
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="text-sm text-muted">{tc("none")}</p>
      )}

      {bankAccounts.length ? (
        <form onSubmit={submit} className="flex flex-col gap-3" aria-label={t("add")}>
          <h2 className="text-sm font-semibold">{t("add")}</h2>
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label htmlFor="sepa-account" className={ui.label}>
                {t("bankAccount")}
              </label>
              <select id="sepa-account" className={ui.input} value={bankAccountId} onChange={(e) => setBankAccountId(e.target.value)}>
                {bankAccounts.map((b) => (
                  <option key={b.id} value={b.id}>
                    {accountLabel(b.id)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="sepa-party" className={ui.label}>
                {t("party")}
              </label>
              <select id="sepa-party" className={ui.input} value={partyId} onChange={(e) => setPartyId(e.target.value)}>
                {parties.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="sepa-entity" className={ui.label}>
                {t("legalEntity")}
              </label>
              <select id="sepa-entity" className={ui.input} value={legalEntityId} onChange={(e) => setLegalEntityId(e.target.value)}>
                <option value="">{t("legalEntitySelect")}</option>
                {legalEntities.map((le) => (
                  <option key={le.id} value={le.id}>
                    {le.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label htmlFor="sepa-reference" className={ui.label}>
                {t("reference")}
              </label>
              <input
                id="sepa-reference"
                className={ui.input}
                value={reference}
                maxLength={35}
                onChange={(e) => setReference(e.target.value)}
                title={t("referenceHint")}
              />
            </div>
            <div>
              <label htmlFor="sepa-creditor" className={ui.label}>
                {t("creditorId")}
              </label>
              <input
                id="sepa-creditor"
                className={ui.input}
                value={creditorId}
                maxLength={35}
                onChange={(e) => setCreditorId(e.target.value)}
                placeholder={t("creditorIdHint")}
              />
            </div>
            <div>
              <label htmlFor="sepa-signed" className={ui.label}>
                {t("signedAt")}
              </label>
              <input id="sepa-signed" type="date" className={ui.input} value={signedAt} onChange={(e) => setSignedAt(e.target.value)} />
            </div>
          </div>
          <fieldset className="flex flex-col gap-2">
            <legend className={ui.label}>{t("evidenceKind")}</legend>
            <div className="flex flex-wrap gap-4 text-sm">
              <label className="flex items-center gap-1">
                <input
                  type="radio"
                  name="sepa-evidence"
                  checked={evidenceKind === "document"}
                  onChange={() => setEvidenceKind("document")}
                />
                {t("evidenceKindDocument")}
              </label>
              <label className="flex items-center gap-1">
                <input
                  type="radio"
                  name="sepa-evidence"
                  checked={evidenceKind === "recorded"}
                  onChange={() => setEvidenceKind("recorded")}
                />
                {t("evidenceKindRecorded")}
              </label>
            </div>
            {evidenceKind === "document" ? (
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("file")}</span>
                <input type="file" accept="application/pdf,.pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              </label>
            ) : (
              <div className="flex flex-wrap items-end gap-3">
                <div>
                  <label htmlFor="sepa-channel" className={ui.label}>
                    {t("channelLabel")}
                  </label>
                  <select id="sepa-channel" className={ui.input} value={channel} onChange={(e) => setChannel(e.target.value as Channel)}>
                    {CHANNELS.map((c) => (
                      <option key={c} value={c}>
                        {t(`channel.${c}`)}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="sepa-note" className={ui.label}>
                    {t("note")}
                  </label>
                  <input
                    id="sepa-note"
                    className={ui.input}
                    value={note}
                    maxLength={500}
                    placeholder={t("noteHint")}
                    onChange={(e) => setNote(e.target.value)}
                  />
                </div>
                <p className="text-xs text-muted">{t("recordedHint")}</p>
              </div>
            )}
          </fieldset>
          <div>
            <button type="submit" className={ui.primary} disabled={busy}>
              {t("save")}
            </button>
          </div>
        </form>
      ) : (
        <p className="text-sm text-muted">{t("noBankAccount")}</p>
      )}
    </div>
  );
}

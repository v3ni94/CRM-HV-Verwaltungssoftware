"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Contract = { id: string; kind: string; number: string };
type Preview = {
  contract_id: string;
  contract_number: string;
  creditor_name: string;
  creditor_id: string;
  reference: string;
  scheme: string;
  sequence: string;
  text: string;
};
export type MandateProposal = {
  id: string;
  reference: string;
  iban_masked: string;
  status: "proposed" | "accepted" | "rejected" | string;
  confirmed_at: string;
  evidence_document_id: string;
};

/** IBAN check per ISO 13616 (mod 97) on the client; the API validates again. */
export function ibanValid(raw: string): boolean {
  const iban = raw.replace(/\s+/g, "").toUpperCase();
  if (!/^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$/.test(iban)) return false;
  const rearranged = iban.slice(4) + iban.slice(0, 4);
  let remainder = 0;
  for (const ch of rearranged) {
    const value = ch >= "A" ? String(ch.charCodeAt(0) - 55) : ch;
    for (const digit of value) remainder = (remainder * 10 + Number(digit)) % 97;
  }
  return remainder === 1;
}

/** Digitales SEPA-Lastschriftmandat (M3-02 Portalstufe): Mandatstext mit Gläubiger-ID und
 *  Mandatsreferenz je Vertrag, IBAN mit Prüfung, Bestätigung durch den Kontoinhaber. Das
 *  Ergebnis ist ein Vorschlag mit Textform-Nachweis; aktiv wird das Mandat erst nach Freigabe
 *  im CRM (G2). */
export function SepaMandateForm({ contracts, proposals }: { contracts: Contract[]; proposals: MandateProposal[] }) {
  const t = useTranslations("SepaMandate");
  const [contractId, setContractId] = useState(contracts[0]?.id ?? "");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [holder, setHolder] = useState("");
  const [iban, setIban] = useState("");
  const [bic, setBic] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<MandateProposal | null>(null);
  const [mine, setMine] = useState<MandateProposal[]>(proposals);

  useEffect(() => {
    setPreview(null);
  }, [contractId]);

  async function loadText() {
    setError(null);
    if (!contractId) {
      setError(t("errorContract"));
      return;
    }
    const result = await bff<Preview>(`/api/bff/portal/sepa-mandates/preview?contract_id=${encodeURIComponent(contractId)}`);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setPreview(result.data);
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (!preview) {
      setError(t("errorContract"));
      return;
    }
    if (holder.trim().length < 2) {
      setError(t("errorHolder"));
      return;
    }
    if (!ibanValid(iban)) {
      setError(t("errorIban"));
      return;
    }
    if (!confirmed) {
      setError(t("errorConfirm"));
      return;
    }
    setBusy(true);
    const result = await bff<MandateProposal>("/api/bff/portal/sepa-mandates", {
      method: "POST",
      body: JSON.stringify({
        contract_id: preview.contract_id,
        iban: iban.replace(/\s+/g, "").toUpperCase(),
        holder: holder.trim(),
        bic: bic.trim() ? bic.trim().toUpperCase() : null,
        confirmed: true,
      }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    setDone(result.data);
    setMine((prev) => [result.data, ...prev]);
    setPreview(null);
    setHolder("");
    setIban("");
    setBic("");
    setConfirmed(false);
  }

  return (
    <div className={ui.pageGap}>
      <p className={ui.notice}>{t("intro")}</p>
      <form onSubmit={onSubmit} noValidate className={`${ui.card} flex flex-col gap-3`}>
        {error ? (
          <p role="alert" className={ui.alert}>
            {error}
          </p>
        ) : null}
        {done ? <p className={ui.success}>{t("submitted")}</p> : null}
        <div>
          <label htmlFor="mandate-contract" className={ui.label}>
            {t("contract")}
          </label>
          <select id="mandate-contract" className={ui.input} value={contractId} onChange={(e) => setContractId(e.target.value)}>
            {contracts.map((c) => (
              <option key={c.id} value={c.id}>
                {c.number}
              </option>
            ))}
          </select>
        </div>
        {!preview ? (
          <div className={ui.formActions}>
            <button type="button" className={`${ui.secondary} ${ui.actionFull}`} onClick={loadText}>
              {t("loadText")}
            </button>
          </div>
        ) : (
          <>
            <dl className="grid gap-1 text-sm sm:grid-cols-2">
              <dt className={ui.label}>{t("creditorId")}</dt>
              <dd className={ui.mono}>{preview.creditor_id}</dd>
              <dt className={ui.label}>{t("reference")}</dt>
              <dd className={ui.mono}>{preview.reference}</dd>
              <dt className={ui.label}>{t("sequence")}</dt>
              <dd>{t("recurrent")}</dd>
            </dl>
            <pre className="whitespace-pre-wrap rounded-md border border-hairline bg-surface p-3 text-xs text-fg" data-testid="mandate-text">
              {preview.text}
            </pre>
            <div>
              <label htmlFor="mandate-holder" className={ui.label}>
                {t("holder")}
              </label>
              <input id="mandate-holder" className={ui.input} value={holder} onChange={(e) => setHolder(e.target.value)} autoComplete="name" />
            </div>
            <div>
              <label htmlFor="mandate-iban" className={ui.label}>
                {t("iban")}
              </label>
              <input id="mandate-iban" className={ui.input} value={iban} onChange={(e) => setIban(e.target.value)} inputMode="text" autoComplete="off" />
            </div>
            <div>
              <label htmlFor="mandate-bic" className={ui.label}>
                {t("bic")}
              </label>
              <input id="mandate-bic" className={ui.input} value={bic} onChange={(e) => setBic(e.target.value)} autoComplete="off" />
            </div>
            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" className="mt-1" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
              <span>{t("confirm")}</span>
            </label>
            <div className={ui.formActions}>
              <button type="submit" className={`${ui.primary} ${ui.actionFull}`} disabled={busy}>
                {t("submit")}
              </button>
            </div>
          </>
        )}
      </form>
      <section className={ui.pageGap}>
        <h2 className={ui.h2}>{t("mine")}</h2>
        {mine.length === 0 ? <p className={ui.notice}>{t("empty")}</p> : null}
        <ul className="flex flex-col gap-2">
          {mine.map((m) => (
            <li key={m.id} className={`${ui.card} flex flex-wrap items-center justify-between gap-2 text-sm`}>
              <span className="flex flex-col">
                <span className={ui.mono}>{m.reference}</span>
                <span className="text-xs text-subtle">
                  {m.iban_masked} · {t(`status.${m.status}`)}
                </span>
              </span>
              <a href={`/api/portal-files/portal/documents/${m.evidence_document_id}/download`} className={ui.buttonSm}>
                {t("evidence")}
              </a>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

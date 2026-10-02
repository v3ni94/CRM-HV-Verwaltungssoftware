"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

type Certificate = {
  contract_id: string;
  year: number;
  share_percent: string;
  labor_total: string;
  material_total: string;
  labor_by_kind: Record<string, string>;
  notice: string;
};

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** GAF-09: Ausweis nach § 35a je Mietvertrag (Einschätzung, Entwurf). Anzeige der Summen und
 *  PDF-Entwurf mit Wasserzeichen; nichts wird versendet oder gebucht. Rechtsprüfung durch die
 *  Steuerberatung. */
export function Section35aCertificate() {
  const t = useTranslations("Section35aCertificate");
  const [contractId, setContractId] = useState("");
  const [year, setYear] = useState(String(new Date().getFullYear() - 1));
  const [share, setShare] = useState("100");
  const [cert, setCert] = useState<Certificate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const valid = UUID.test(contractId.trim()) && /^\d{4}$/.test(year) && share !== "";
  const query = () =>
    new URLSearchParams({ contract_id: contractId.trim(), year, share_percent: share }).toString();

  async function calculate(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setCert(null);
    const res = await bff<Certificate>(`/api/bff/accounting/tax/section35a/certificate?${query()}`);
    setBusy(false);
    if (!res.ok) setError(res.message);
    else setCert(res.data);
  }

  return (
    <section className={ui.card} aria-labelledby="s35a-title" data-testid="s35a-certificate">
      <h2 id="s35a-title" className={ui.h2}>
        {t("title")}
      </h2>
      <p className={ui.help}>{t("help")}</p>
      <form onSubmit={calculate} className="mt-3 grid gap-3 sm:grid-cols-3">
        <label className="flex flex-col gap-1 sm:col-span-3">
          <span className={ui.label}>{t("contract")}</span>
          <input className={ui.input} value={contractId} onChange={(e) => setContractId(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("year")}</span>
          <input className={ui.input} inputMode="numeric" value={year} onChange={(e) => setYear(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("share")}</span>
          <input className={ui.input} inputMode="decimal" value={share} onChange={(e) => setShare(e.target.value)} />
        </label>
        <div className={`${ui.formActions} sm:self-end`}>
          <button type="submit" className={ui.primary} disabled={busy || !valid}>
            {t("calculate")}
          </button>
        </div>
      </form>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {cert ? (
        <div className="mt-3 text-sm" data-testid="s35a-result">
          <p>
            {t("labor")}: {formatEur(cert.labor_total)} · {t("material")}: {formatEur(cert.material_total)}
          </p>
          <p className={ui.help}>{cert.notice}</p>
          <a
            className={ui.buttonSm}
            href={`/api/bff/accounting/tax/section35a/certificate.pdf?${query()}`}
            data-testid="s35a-pdf"
          >
            {t("pdf")}
          </a>
        </div>
      ) : null}
    </section>
  );
}

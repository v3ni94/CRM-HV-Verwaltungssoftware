"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatDecimal, formatEur } from "@/lib/format";
import { centsToDecimal, parseCents } from "@/lib/money";
import { useBusy } from "@/lib/use-busy";
import { ui } from "@/lib/ui";

type Agreement = { index_name: string; base_index: string; base_month: string; source: string | null };
type Step = { valid_from: string; net: string; note: string | null };
type Terms = {
  index_agreement: Agreement | null;
  graduated_steps: Step[];
  latest_index_month: string | null;
  latest_index_value: string | null;
};
type Proposal = { id: string; basis: string; current_rent: string; target_rent: string; effective_date: string };
type Mode = "none" | "index" | "graduated";

/** Indexklausel oder Staffel eines Mietvertrags (AO03, GAK-203). Die Felder sind nur Eingaben für
 *  den Tagesjob, der bei eingeschaltetem Mandantenschalter Vorschläge als Entwurf anlegt. Die Miete
 *  ändert sich dadurch nie; Wartefrist und Wirksamkeit sind nicht festgelegt (AN18-01). */
export function ContractIndexTermsPanel({ contractId, canUpdate }: { contractId: string; canUpdate: boolean }) {
  const t = useTranslations("ContractIndexTerms");
  const tc = useTranslations("Common");
  const url = `/api/bff/letting/contracts/${contractId}/index-terms`;
  const [terms, setTerms] = useState<Terms | null>(null);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [mode, setMode] = useState<Mode>("none");
  const [indexName, setIndexName] = useState("");
  const [baseIndex, setBaseIndex] = useState("");
  const [baseMonth, setBaseMonth] = useState("");
  const [source, setSource] = useState("");
  const [steps, setSteps] = useState<{ valid_from: string; net: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const { busy, guard } = useBusy();

  const apply = useCallback((data: Terms) => {
    setTerms(data);
    const a = data.index_agreement;
    setMode(a ? "index" : data.graduated_steps.length ? "graduated" : "none");
    setIndexName(a?.index_name ?? "");
    setBaseIndex(a?.base_index ?? "");
    setBaseMonth(a ? a.base_month.slice(0, 7) : "");
    setSource(a?.source ?? "");
    setSteps(data.graduated_steps.map((s) => ({ valid_from: s.valid_from, net: s.net })));
  }, []);

  const load = useCallback(async () => {
    const res = await bff<Terms>(url);
    if (res.ok) apply(res.data);
    else setError(res.message);
    const props = await bff<Proposal[]>(`/api/bff/letting/rent-increase-proposals?contract_id=${contractId}`);
    if (props.ok) setProposals(props.data);
  }, [apply, contractId, url]);

  useEffect(() => {
    void load();
  }, [load]);

  const save = guard(async (event?: React.FormEvent) => {
    event?.preventDefault();
    setError(null);
    setSaved(false);
    const body: Record<string, unknown> = { index_agreement: null, graduated_steps: [] };
    if (mode === "index") {
      body.index_agreement = {
        index_name: indexName.trim(),
        base_index: baseIndex.trim().replace(",", "."),
        base_month: `${baseMonth}-01`,
        source: source.trim() || null,
      };
    } else if (mode === "graduated") {
      const out = [];
      for (const s of steps) {
        const cents = parseCents(s.net);
        if (cents === null || cents <= 0n || !s.valid_from) {
          setError(t("invalidStep"));
          return;
        }
        out.push({ valid_from: s.valid_from, net: centsToDecimal(cents) });
      }
      body.graduated_steps = out;
    }
    const res = await bff<Terms>(url, { method: "PUT", body: JSON.stringify(body) });
    if (res.ok) {
      apply(res.data);
      setSaved(true);
    } else setError(res.message);
  });

  return (
    <section className={`${ui.card} flex flex-col gap-3`} data-testid="contract-index-terms" aria-labelledby="index-terms-title">
      <h2 id="index-terms-title" className="font-medium">
        {t("title")}
      </h2>
      <p className={ui.help}>{t("hint")}</p>
      {terms?.latest_index_month ? (
        <p className="text-sm" data-testid="latest-index">
          {t("latest", { month: formatDate(terms.latest_index_month).slice(3), value: formatDecimal(terms.latest_index_value, 1) })}
        </p>
      ) : null}
      <form onSubmit={save} className="flex flex-col gap-3">
        <fieldset className="flex flex-wrap gap-4" disabled={!canUpdate}>
          <legend className={ui.label}>{t("mode")}</legend>
          {(["none", "index", "graduated"] as const).map((m) => (
            <label key={m} className="flex items-center gap-2">
              <input type="radio" name="index-mode" checked={mode === m} onChange={() => setMode(m)} />
              {t(`modes.${m}`)}
            </label>
          ))}
        </fieldset>
        {mode === "index" ? (
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("indexName")}</span>
              <input className={ui.input} value={indexName} onChange={(e) => setIndexName(e.target.value)} required pattern="[A-Za-z0-9_.\-]{1,40}" disabled={!canUpdate} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("baseIndex")}</span>
              <input className={ui.input} inputMode="decimal" value={baseIndex} onChange={(e) => setBaseIndex(e.target.value)} required disabled={!canUpdate} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("baseMonth")}</span>
              <input className={ui.input} type="month" value={baseMonth} onChange={(e) => setBaseMonth(e.target.value)} required disabled={!canUpdate} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("source")}</span>
              <input className={ui.input} value={source} onChange={(e) => setSource(e.target.value)} maxLength={500} disabled={!canUpdate} />
            </label>
          </div>
        ) : null}
        {mode === "graduated" ? (
          <div className="flex flex-col gap-2">
            {steps.length === 0 ? <p className={ui.help}>{tc("emptyList")}</p> : null}
            {steps.map((s, i) => (
              <div key={i} className="flex flex-wrap items-end gap-3" data-testid="graduated-step">
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("validFrom")}</span>
                  <input className={ui.input} type="date" value={s.valid_from} onChange={(e) => setSteps(steps.map((x, j) => (j === i ? { ...x, valid_from: e.target.value } : x)))} required disabled={!canUpdate} />
                </label>
                <label className="flex flex-col gap-1">
                  <span className={ui.label}>{t("net")}</span>
                  <input className={ui.input} inputMode="decimal" value={s.net} onChange={(e) => setSteps(steps.map((x, j) => (j === i ? { ...x, net: e.target.value } : x)))} required disabled={!canUpdate} />
                </label>
                {canUpdate ? (
                  <button type="button" className={ui.secondary} onClick={() => setSteps(steps.filter((_, j) => j !== i))}>
                    {t("remove")}
                  </button>
                ) : null}
              </div>
            ))}
            {canUpdate ? (
              <button type="button" className={`${ui.secondary} self-start`} onClick={() => setSteps([...steps, { valid_from: "", net: "" }])}>
                {t("addStep")}
              </button>
            ) : null}
          </div>
        ) : null}
        {canUpdate ? (
          <button type="submit" className={`${ui.primary} self-start`} disabled={busy}>
            {t("save")}
          </button>
        ) : null}
      </form>
      {saved ? <p className={ui.success}>{t("saved")}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <h3 className="font-medium">{t("proposals")}</h3>
      {proposals.length === 0 ? (
        <p className={ui.help}>{t("noProposals")}</p>
      ) : (
        <ul className="flex flex-col gap-1 text-sm" data-testid="index-proposals">
          {proposals.map((p) => (
            <li key={p.id}>
              <Link className="underline" href={`/vermietung/mieterhoehung/${p.id}`}>
                {t("proposalLine", {
                  basis: t(`modes.${p.basis === "index" ? "index" : "graduated"}`),
                  date: formatDate(p.effective_date),
                  from: formatEur(p.current_rent),
                  to: formatEur(p.target_rent),
                })}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

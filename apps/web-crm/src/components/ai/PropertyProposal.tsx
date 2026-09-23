"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { partyName, paymentTypes, propertyPreview, vatMap, type ImportRun, type Proposal } from "@/lib/ai";
import { bff } from "@/lib/bff";
import { formatDate, formatDecimal, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

import { ImportResult } from "./ImportResult";

const MANAGEMENT = ["rental", "hoa", "hoa_with_sev"] as const;

/** Tree preview of an extracted property (10.2 step 3) with the confirmations of step 5. */
export function PropertyProposal({ proposal, onDecided }: { proposal: Proposal; onDecided?: () => void }) {
  const t = useTranslations("Ai");
  const preview = propertyPreview(proposal.proposed);
  const codes = paymentTypes(preview);
  const [number, setNumber] = useState(preview.property.number ?? "");
  const [name, setName] = useState(preview.property.name ?? "");
  const [management, setManagement] = useState<string>(preview.property.management_type ?? "");
  const [asOf, setAsOf] = useState("");
  const [vat, setVat] = useState<Record<string, string>>(() => Object.fromEntries(codes.map((c) => [c, ""])));
  const [result, setResult] = useState<ImportRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [decision, setDecision] = useState(proposal.decision);

  const { map, invalid } = vatMap(vat);
  const numberValid = /^\d{3}$/.test(number);
  const missing: string[] = [];
  if (!numberValid) missing.push(t("missingNumber"));
  if (!management) missing.push(t("missingManagement"));
  if (!asOf) missing.push(t("missingAsOf"));
  if (invalid.length) missing.push(t("invalidVat"));
  const skipped = codes.filter((c) => !(c in map));

  const apply = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<ImportRun>(`/api/bff/ai/proposals/${proposal.id}/apply`, {
      method: "POST",
      body: JSON.stringify({
        property: {
          number,
          name: name.trim() || null,
          management_type: management,
          as_of: asOf,
          vat_percent_by_payment_type: map,
        },
      }),
    });
    setBusy(false);
    if (res.ok) {
      setResult(res.data);
      setDecision("modified");
      onDecided?.();
    } else setError(res.message);
  };

  const reject = async () => {
    setBusy(true);
    const res = await bff<Proposal>(`/api/bff/ai/proposals/${proposal.id}/reject`, { method: "POST" });
    setBusy(false);
    if (res.ok) {
      setDecision(res.data.decision);
      onDecided?.();
    } else setError(res.message);
  };

  if (result) return <ImportResult importRun={result} />;

  const p = preview.property;
  const address = [[p.street, p.house_number].filter(Boolean).join(" "), [p.postal_code, p.city].filter(Boolean).join(" ")]
    .filter(Boolean)
    .join(", ");
  const buildings = preview.buildings.length ? preview.buildings : [""];

  return (
    <section className="flex flex-col gap-3" aria-label={t("propertyPreviewTitle")}>
      <h3 className="text-sm font-semibold">{t("propertyPreviewTitle")}</h3>
      {preview.questions.length > 0 ? (
        <div className={ui.notice}>
          <p className="font-medium">{t("openQuestions")}</p>
          <ul className="list-disc pl-4">
            {preview.questions.map((q, i) => (
              <li key={i}>{q}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {preview.notes.length > 0 ? (
        <div className={ui.notice}>
          <p className="font-medium">{t("notes")}</p>
          <ul className="list-disc pl-4">
            {preview.notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <ul className="text-sm" aria-label={t("tree")}>
        <li>
          <span className="font-medium">{t("treeProperty", { name: p.name || t("noName") })}</span>
          {address ? <span className="text-muted">, {address}</span> : null}
          <ul className="ml-4 border-l border-border pl-3">
            {buildings.map((b) => {
              const units = preview.units.filter((u) => (preview.buildings.length ? (u.building ?? preview.buildings[0]) === b : true));
              return (
                <li key={b || "default"}>
                  <span>{b ? t("treeBuilding", { name: b }) : t("treeBuildingDefault")}</span>
                  <ul className="ml-4 border-l border-border pl-3">
                    {units.map((u) => (
                      <li key={u.number}>
                        <span>
                          {t("treeUnit", { number: u.number })}
                          {u.label ? `, ${u.label}` : ""} ({t(`unitType.${u.unit_type}`)})
                        </span>
                        <span className="text-xs text-muted">
                          {u.living_area_sqm ? `, ${formatDecimal(u.living_area_sqm, 2)} m²` : ""}
                          {u.mea ? `, ${t("mea", { value: formatDecimal(u.mea, 4) })}` : `, ${t("meaMissing")}`}
                          {u.source ? `, ${t("source", { source: u.source })}` : ""}
                        </span>
                        <ul className="ml-4 border-l border-border pl-3">
                          {preview.parties
                            .filter((party) => party.unit_number === u.number)
                            .map((party, k) => (
                              <li key={k}>
                                <span>
                                  {t(`role.${party.role}`)}: {partyName(party) || t("noName")}
                                </span>
                                <span className="text-xs text-muted">
                                  {party.start_date ? `, ${t("start", { date: formatDate(party.start_date) })}` : `, ${t("startMissing")}`}
                                </span>
                                {party.payments.length > 0 ? (
                                  <ul className="ml-4 text-xs">
                                    {party.payments.map((pay, m) => (
                                      <li key={m}>
                                        {t(`paymentType.${pay.payment_type_code}`)}: {formatEur(pay.gross)} {t("gross")}
                                        {pay.valid_from ? `, ${t("validFrom", { date: formatDate(pay.valid_from) })}` : ""}
                                      </li>
                                    ))}
                                  </ul>
                                ) : null}
                              </li>
                            ))}
                        </ul>
                      </li>
                    ))}
                  </ul>
                </li>
              );
            })}
          </ul>
        </li>
      </ul>
      {preview.parties.some((party) => !preview.units.some((u) => u.number === party.unit_number)) ? (
        <p className="text-xs text-muted">{t("partiesWithoutUnit")}</p>
      ) : null}

      {decision === "pending" ? (
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (missing.length === 0) void apply();
          }}
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label htmlFor="prop-number" className={ui.label}>
                {t("fieldNumber")}
              </label>
              <input
                id="prop-number"
                className={ui.input}
                inputMode="numeric"
                maxLength={3}
                value={number}
                onChange={(e) => setNumber(e.target.value.replace(/\D/g, ""))}
                aria-invalid={!numberValid}
              />
              {!numberValid ? <p className={ui.error}>{t("numberHint")}</p> : null}
            </div>
            <div>
              <label htmlFor="prop-name" className={ui.label}>
                {t("fieldName")}
              </label>
              <input id="prop-name" className={ui.input} value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div>
              <label htmlFor="prop-management" className={ui.label}>
                {t("fieldManagement")}
              </label>
              <select id="prop-management" className={ui.input} value={management} onChange={(e) => setManagement(e.target.value)}>
                <option value="">{t("choose")}</option>
                {MANAGEMENT.map((m) => (
                  <option key={m} value={m}>
                    {t(`management.${m}`)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="prop-asof" className={ui.label}>
                {t("fieldAsOf")}
              </label>
              <input id="prop-asof" type="date" className={ui.input} value={asOf} onChange={(e) => setAsOf(e.target.value)} />
            </div>
          </div>
          {codes.length > 0 ? (
            <fieldset className="flex flex-col gap-2">
              <legend className="text-sm font-medium">{t("vatTitle")}</legend>
              <p className="text-xs text-muted">{t("vatHint")}</p>
              <div className="grid gap-2 sm:grid-cols-2">
                {codes.map((code) => (
                  <div key={code}>
                    <label htmlFor={`vat-${code}`} className={ui.label}>
                      {t("vatFor", { type: t(`paymentType.${code}`) })}
                    </label>
                    <input
                      id={`vat-${code}`}
                      className={ui.input}
                      inputMode="decimal"
                      placeholder={t("vatPlaceholder")}
                      value={vat[code] ?? ""}
                      onChange={(e) => setVat((prev) => ({ ...prev, [code]: e.target.value }))}
                      aria-invalid={invalid.includes(code)}
                    />
                    {invalid.includes(code) ? <p className={ui.error}>{t("vatInvalid")}</p> : null}
                    {!(code in map) && !invalid.includes(code) ? (
                      <p className="text-xs text-muted" data-testid={`vat-skip-${code}`}>
                        {t("vatSkipped")}
                      </p>
                    ) : null}
                  </div>
                ))}
              </div>
              {skipped.length > 0 ? (
                <p className={ui.notice} data-testid="vat-summary">
                  {t("vatSummary", { list: skipped.map((c) => t(`paymentType.${c}`)).join(", ") })}
                </p>
              ) : null}
            </fieldset>
          ) : null}
          {missing.length > 0 ? <p className="text-xs text-muted">{t("stillMissing", { list: missing.join(", ") })}</p> : null}
          {error ? (
            <p role="alert" className={ui.alert}>
              {error}
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <button type="submit" className={ui.primary} disabled={busy || missing.length > 0}>
              {t("confirmApply")}
            </button>
            <button type="button" className={ui.button} onClick={reject} disabled={busy}>
              {t("reject")}
            </button>
            <p className="self-center text-xs text-muted">{t("applyHint")}</p>
          </div>
        </form>
      ) : (
        <p className="text-sm text-muted">{t(`decision.${decision}`)}</p>
      )}
    </section>
  );
}

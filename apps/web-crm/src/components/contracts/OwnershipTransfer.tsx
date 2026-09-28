"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatDecimal, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

/**
 * Eigentümerwechsel (operator 28.09.2026, Master-Prompt D16, D17): Dialog auf der Vertrags-
 * und der Einheitenseite. Erwerber suchen oder als Kontakt anlegen, Eigentumsübergang, Nutzen
 * und Lasten, Erwerbsart, Nachweis, Notiz; Vorschau aus
 * GET /contracts/{id}/ownership-transfer/preview (altes Eigentum endet am Vortag, neues beginnt
 * am Übergang, übernommene Sollbeträge, Zahlungsplan und Umlagewerte ab dem Übergang); Bestätigung
 * ruft POST /contracts/{id}/ownership-transfer. Keine Aufteilung der Abrechnung zwischen
 * Veräußerer und Erwerber (Regel W07 nicht freigegeben, Freigabepunkt P01 offen).
 */

export type TransferContract = {
  id: string;
  kind: string;
  number: string;
  party_id: string;
  party_name?: string | null;
  unit_id: string;
  start_date: string;
  end_date: string | null;
  sev_enabled: boolean;
};

export type TransferPreview = {
  contract_id: string;
  party_id: string;
  party_name: string | null;
  title_transfer_date: string;
  old_end_date: string;
  new_start_date: string;
  payments: { id: string; payment_type_code: string; gross: string; valid_from: string; valid_to: string | null }[];
  schedules: { id: string; interval: string; due_day_rule: string; due_day: number; valid_from: string; valid_to: string | null }[];
  allocation_values: { id: string; allocation_key_code: string | null; allocation_key_name: string | null; unit_of_measure: string | null; value: string; valid_from: string }[];
  statement_split: "not_implemented";
};

type Hit = { id: string; display_name: string };
const ACQUISITION_KINDS = ["purchase", "first_acquisition", "inheritance", "foreclosure", "gift", "other"] as const;
type AcquisitionKind = (typeof ACQUISITION_KINDS)[number];

/** Erwerber: Kontaktsuche (Name, Datensparsamkeit) oder Anlage eines neuen Kontakts. */
function AcquirerField({ value, onChange }: { value: Hit | null; onChange: (hit: Hit | null) => void }) {
  const t = useTranslations("OwnershipTransfer");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [kind, setKind] = useState<"person" | "company">("person");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [companyName, setCompanyName] = useState("");

  async function search() {
    const q = query.trim();
    if (q.length < 2) return;
    setBusy(true);
    setError(null);
    const res = await bff<{ items: Hit[] }>(`/api/bff/contacts?q=${encodeURIComponent(q)}&page_size=10`);
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setHits(res.data.items.map((c) => ({ id: c.id, display_name: c.display_name })));
    if (res.data.items.length === 0) setError(t("acquirer.noResults"));
  }

  async function create() {
    setBusy(true);
    setError(null);
    const body = kind === "person" ? { kind, first_name: firstName.trim(), last_name: lastName.trim() } : { kind, company_name: companyName.trim() };
    const res = await bff<Hit>("/api/bff/contacts", { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    onChange({ id: res.data.id, display_name: res.data.display_name });
    setCreating(false);
  }

  const createValid = kind === "person" ? lastName.trim() !== "" : companyName.trim() !== "";

  if (value) {
    return (
      <div className="flex flex-col gap-1">
        <span className={ui.label}>{t("acquirer.label")}</span>
        <span className="flex items-center gap-2 text-sm" data-testid="acquirer-picked">
          <span className={ui.badgeGold}>{value.display_name}</span>
          <button type="button" className={ui.buttonSm} onClick={() => onChange(null)}>
            {t("acquirer.clear")}
          </button>
        </span>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("acquirer.label")}</span>
        <span className="flex gap-2">
          <input
            className={ui.input}
            value={query}
            placeholder={t("acquirer.placeholder")}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void search();
              }
            }}
          />
          <button type="button" className={ui.buttonSm} disabled={busy || query.trim().length < 2} onClick={() => void search()}>
            {t("acquirer.search")}
          </button>
        </span>
      </label>
      {hits.length > 0 ? (
        <ul className="flex flex-wrap gap-1" aria-label={t("acquirer.results")}>
          {hits.map((h) => (
            <li key={h.id}>
              <button
                type="button"
                className={ui.buttonSm}
                onClick={() => {
                  onChange(h);
                  setHits([]);
                  setQuery("");
                }}
              >
                {h.display_name}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {!creating ? (
        <button type="button" className={`${ui.buttonSm} self-start`} onClick={() => setCreating(true)}>
          {t("acquirer.createToggle")}
        </button>
      ) : (
        <div className="flex flex-col gap-2 border-l-2 border-border pl-3" data-testid="acquirer-create">
          <label className={ui.label}>
            {t("acquirer.kind")}
            <select className={ui.input} value={kind} onChange={(e) => setKind(e.target.value as "person" | "company")}>
              <option value="person">{t("acquirer.kinds.person")}</option>
              <option value="company">{t("acquirer.kinds.company")}</option>
            </select>
          </label>
          {kind === "person" ? (
            <div className="grid gap-2 sm:grid-cols-2">
              <label className={ui.label}>
                {t("acquirer.firstName")}
                <input className={ui.input} value={firstName} onChange={(e) => setFirstName(e.target.value)} />
              </label>
              <label className={ui.label}>
                {t("acquirer.lastName")}
                <input className={ui.input} value={lastName} onChange={(e) => setLastName(e.target.value)} />
              </label>
            </div>
          ) : (
            <label className={ui.label}>
              {t("acquirer.companyName")}
              <input className={ui.input} value={companyName} onChange={(e) => setCompanyName(e.target.value)} />
            </label>
          )}
          <p className={ui.help}>{t("acquirer.createHint")}</p>
          <div className={ui.formActions}>
            <button type="button" className={ui.buttonSm} disabled={busy || !createValid} onClick={() => void create()}>
              {t("acquirer.create")}
            </button>
            <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => setCreating(false)}>
              {t("cancel")}
            </button>
          </div>
        </div>
      )}
      {error ? (
        <p role="alert" className={ui.error}>
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function OwnershipTransfer({ contractId, sevAllowed, canUpdate }: { contractId: string; sevAllowed: boolean; canUpdate: boolean }) {
  const t = useTranslations("OwnershipTransfer");
  const tc = useTranslations("ContractForm");
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [contract, setContract] = useState<TransferContract | null>(null);
  const [step, setStep] = useState<"form" | "preview">("form");
  const [preview, setPreview] = useState<TransferPreview | null>(null);
  const [acquirer, setAcquirer] = useState<Hit | null>(null);
  const [titleDate, setTitleDate] = useState("");
  const [benefitDate, setBenefitDate] = useState("");
  const [acquisitionKind, setAcquisitionKind] = useState<AcquisitionKind>("purchase");
  const [sevEnabled, setSevEnabled] = useState(false);
  const [liability, setLiability] = useState(false);
  const [carryOver, setCarryOver] = useState(true);
  const [notes, setNotes] = useState("");
  const [document, setDocument] = useState<{ id: string; title: string } | null>(null);
  const [uploading, setUploading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!canUpdate) return null;

  async function start() {
    setBusy(true);
    setError(null);
    const res = await bff<TransferContract>(`/api/bff/contracts/${contractId}`);
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setContract(res.data);
    setSevEnabled(sevAllowed && res.data.sev_enabled);
    setOpen(true);
  }

  function reset() {
    setOpen(false);
    setStep("form");
    setPreview(null);
    setAcquirer(null);
    setTitleDate("");
    setBenefitDate("");
    setAcquisitionKind("purchase");
    setLiability(false);
    setCarryOver(true);
    setNotes("");
    setDocument(null);
    setError(null);
  }

  async function upload(file: File) {
    if (!contract) return;
    setUploading(true);
    setError(null);
    const form = new FormData();
    form.set("file", file);
    form.set("title", file.name);
    form.set("links", JSON.stringify([{ entity_type: "unit", entity_id: contract.unit_id, role: "evidence" }]));
    const res = await bff<{ id: string; title: string }>("/api/bff/documents", { method: "POST", body: form });
    setUploading(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setDocument({ id: res.data.id, title: res.data.title ?? file.name });
  }

  async function loadPreview() {
    setBusy(true);
    setError(null);
    const res = await bff<TransferPreview>(`/api/bff/contracts/${contractId}/ownership-transfer/preview?title_transfer_date=${titleDate}`);
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setPreview(res.data);
    setStep("preview");
  }

  async function save() {
    if (!acquirer) return;
    setBusy(true);
    setError(null);
    const body: Record<string, unknown> = {
      new_contact_id: acquirer.id,
      title_transfer_date: titleDate,
      acquisition_kind: acquisitionKind,
      special_succession_liability: liability,
      sev_enabled: sevEnabled,
      carry_over_amounts: carryOver,
    };
    if (benefitDate) body.benefit_burden_date = benefitDate;
    if (notes.trim()) body.notes = notes.trim();
    if (document) body.document_id = document.id;
    const res = await bff<{ id: string }>(`/api/bff/contracts/${contractId}/ownership-transfer`, { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      setStep("form");
      return;
    }
    reset();
    router.push(`/vertraege/${res.data.id}?hinweis=${encodeURIComponent(t("done"))}`);
    router.refresh();
  }

  const dateMissing = titleDate === "";
  const dateTooEarly = !dateMissing && contract !== null && titleDate <= contract.start_date;
  const benefitWrong = benefitDate !== "" && titleDate !== "" && benefitDate > titleDate;
  const hint = dateMissing ? t("errors.dateRequired") : dateTooEarly ? t("errors.dateAfterStart", { date: formatDate(contract?.start_date) }) : !acquirer ? t("errors.acquirerRequired") : null;
  const canPreview = !dateMissing && !dateTooEarly && !benefitWrong && acquirer !== null && !uploading;
  const paymentLabel = (code: string) => (t.has(`paymentTypes.${code}`) ? t(`paymentTypes.${code}`) : code);

  return (
    <section className={ui.card} data-testid="ownership-transfer">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className={ui.subtitle}>{t("title")}</h2>
        {!open ? (
          <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void start()}>
            {t("open")}
          </button>
        ) : null}
      </div>
      <p className="mt-1 text-sm text-muted">{t("intro")}</p>
      {open && contract ? (
        contract.kind !== "ownership" ? (
          <p className={`${ui.notice} mt-3`}>{t("notOwnership")}</p>
        ) : contract.end_date ? (
          <p className={`${ui.notice} mt-3`}>{t("alreadyEnded", { date: formatDate(contract.end_date) })}</p>
        ) : (
          <div role="dialog" aria-modal="false" aria-labelledby="ownership-transfer-title" className="mt-3 flex flex-col gap-3 border-t border-border pt-3" data-testid="ownership-transfer-dialog">
            <h3 id="ownership-transfer-title" className="font-medium">
              {step === "preview" ? t("previewTitle") : t("formTitle", { number: contract.number, party: contract.party_name ?? "" })}
            </h3>
            {step === "preview" && preview ? (
              <>
                <ul className="flex flex-col gap-1 text-sm" data-testid="transfer-preview">
                  <li>{t("preview.oldEnds", { party: preview.party_name ?? "", date: formatDate(preview.old_end_date) })}</li>
                  <li>{t("preview.newStarts", { party: acquirer?.display_name ?? "", date: formatDate(preview.new_start_date) })}</li>
                  <li>{t("preview.receivablesStay")}</li>
                </ul>
                <div className="text-sm">
                  <p className="font-medium">{carryOver ? t("preview.carriedTitle", { date: formatDate(preview.new_start_date) }) : t("preview.notCarriedTitle")}</p>
                  {preview.payments.length === 0 && preview.schedules.length === 0 && preview.allocation_values.length === 0 ? (
                    <p className="text-muted">{t("preview.nothingToCarry")}</p>
                  ) : (
                    <ul className={`mt-1 flex flex-col gap-0.5 ${carryOver ? "" : "text-muted line-through"}`} data-testid="transfer-amounts">
                      {preview.payments.map((p) => (
                        <li key={p.id}>
                          {paymentLabel(p.payment_type_code)}: {formatEur(p.gross)}
                          {p.valid_to ? ` (${t("preview.until", { date: formatDate(p.valid_to) })})` : ""}
                        </li>
                      ))}
                      {preview.schedules.map((s) => (
                        <li key={s.id}>
                          {t("preview.schedule")}: {tc(`intervals.${s.interval}`)}, {tc(`dueDayRules.${s.due_day_rule}`)} {s.due_day}
                        </li>
                      ))}
                      {preview.allocation_values.map((v) => (
                        <li key={v.id}>
                          {v.allocation_key_name ?? v.allocation_key_code ?? ""}: {formatDecimal(v.value, 2)} {v.unit_of_measure ?? ""}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <p className={ui.notice} data-testid="transfer-w07">
                  {t("preview.noSplit")}
                </p>
                <p className={ui.help}>{t("preview.followUp")}</p>
                <div className={ui.formActions}>
                  <button type="button" className={ui.primary} disabled={busy} onClick={() => void save()}>
                    {t("confirm")}
                  </button>
                  <button type="button" className={ui.button} disabled={busy} onClick={() => setStep("form")}>
                    {t("back")}
                  </button>
                </div>
              </>
            ) : (
              <>
                <AcquirerField value={acquirer} onChange={setAcquirer} />
                <div className="grid gap-3 sm:grid-cols-3">
                  <label className={ui.label}>
                    {t("titleDate")}
                    <input type="date" className={ui.input} value={titleDate} onChange={(e) => setTitleDate(e.target.value)} />
                  </label>
                  <label className={ui.label}>
                    {t("benefitDate")}
                    <input type="date" className={ui.input} value={benefitDate} onChange={(e) => setBenefitDate(e.target.value)} />
                  </label>
                  <label className={ui.label}>
                    {t("acquisitionKind")}
                    <select className={ui.input} value={acquisitionKind} onChange={(e) => setAcquisitionKind(e.target.value as AcquisitionKind)}>
                      {ACQUISITION_KINDS.map((k) => (
                        <option key={k} value={k}>
                          {tc(`acquisitionKinds.${k}`)}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <div className="flex flex-col gap-1 text-sm">
                  <label className="flex items-center gap-2">
                    <input type="checkbox" checked={carryOver} onChange={(e) => setCarryOver(e.target.checked)} />
                    {t("carryOver")}
                  </label>
                  <p className={ui.help}>{t("carryOverHelp")}</p>
                  <label className="flex items-center gap-2">
                    <input type="checkbox" checked={liability} onChange={(e) => setLiability(e.target.checked)} />
                    {t("liability")}
                  </label>
                  {sevAllowed ? (
                    <label className="flex items-center gap-2">
                      <input type="checkbox" checked={sevEnabled} onChange={(e) => setSevEnabled(e.target.checked)} />
                      {t("sevEnabled")}
                    </label>
                  ) : null}
                </div>
                <div className="flex flex-col gap-1">
                  <span className={ui.label}>{t("document")}</span>
                  {document ? (
                    <span className="flex items-center gap-2 text-sm">
                      <span>{t("uploaded", { title: document.title })}</span>
                      <button type="button" className={ui.buttonSm} onClick={() => setDocument(null)}>
                        {t("removeDocument")}
                      </button>
                    </span>
                  ) : (
                    <label className="text-sm">
                      <span className="sr-only">{t("upload")}</span>
                      <input
                        type="file"
                        aria-label={t("upload")}
                        disabled={uploading}
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) void upload(file);
                        }}
                      />
                      {uploading ? <span className="ml-2 text-muted">{t("uploading")}</span> : null}
                    </label>
                  )}
                  <p className={ui.help}>{t("documentHelp")}</p>
                </div>
                <label className={ui.label}>
                  {t("notes")}
                  <textarea className={ui.input} rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
                </label>
                {benefitWrong ? <p className={ui.help}>{t("errors.benefitAfterTitle")}</p> : hint ? <p className={ui.help}>{hint}</p> : null}
                <div className={ui.formActions}>
                  <button type="button" className={ui.primary} disabled={!canPreview || busy} onClick={() => void loadPreview()}>
                    {t("next")}
                  </button>
                  <button type="button" className={ui.button} disabled={busy} onClick={reset}>
                    {t("cancel")}
                  </button>
                </div>
              </>
            )}
            {error ? (
              <p role="alert" className={ui.error}>
                {error}
              </p>
            ) : null}
          </div>
        )
      ) : null}
      {!open && error ? (
        <p role="alert" className={`${ui.error} mt-2`}>
          {error}
        </p>
      ) : null}
    </section>
  );
}

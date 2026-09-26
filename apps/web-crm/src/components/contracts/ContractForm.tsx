"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { fieldPath, type Problem } from "@/lib/problem";
import { ui } from "@/lib/ui";

/* ---------------------------------------------------------------------------------------
 * Types mirroring mhvp.contracts.schemas (ContractIn, ContractVersionIn, TerminationIn,
 * ScheduleIn, DepositIn, ContractOut). The API has no PATCH on a contract: changes after the
 * start are a new version (POST /contracts/{id}/versions), the end is a termination
 * (POST /contracts/{id}/termination). Unit, party, start and ownership data are fixed.
 * ------------------------------------------------------------------------------------- */

export type ContractKind = "tenancy" | "ownership";
export type ContractVatOption = "none" | "commercial_no_vat" | "commercial_full_vat" | "commercial_reduced_vat";
export type AcquisitionKind = "purchase" | "first_acquisition" | "inheritance" | "foreclosure" | "gift" | "other";
export type PaymentInterval = "monthly" | "quarterly" | "semiannual" | "annual";
export type DueDayRule = "day" | "workday" | "last_day" | "day_next_month";
export type DepositKind = "cash" | "savings_book" | "insurance" | "guarantee" | "fixed_deposit" | "letter_of_comfort" | "other";
export type ManagementType = "rental" | "hoa" | "hoa_with_sev";

export type ScheduleOut = {
  id: string;
  interval: PaymentInterval;
  due_day_rule: DueDayRule;
  due_day: number;
  valid_from: string;
  valid_to: string | null;
};

export type ContractOut = {
  id: string;
  kind: ContractKind;
  number: string;
  version: number;
  property_id: string;
  unit_id: string;
  party_id: string;
  legal_entity_id: string;
  start_date: string;
  end_date: string | null;
  termination_date: string | null;
  termination_reason: string | null;
  direct_debit: boolean;
  sepa_mandate_id: string | null;
  dunning_block: boolean;
  dunning_block_reason: string | null;
  rent_increase_block_until: string | null;
  user_change_fee: boolean;
  allocation_loss_risk: boolean;
  vat_option: ContractVatOption;
  sev_enabled: boolean;
  sev_fee_debtor_party_id: string | null;
  title_transfer_date: string | null;
  benefit_burden_date: string | null;
  acquisition_kind: AcquisitionKind | null;
  special_succession_liability: boolean;
  notes: string | null;
  schedules: ScheduleOut[];
};

export type PropertyOption = { id: string; label: string; management_type: ManagementType };
export type UnitOption = { id: string; number: string; label: string | null; unit_type: string };
export type LegalEntityOption = { id: string; name: string; kind: string };
export type ContactOption = { id: string; display_name: string; roles?: string[] };
export type MandateOption = { id: string; reference: string; iban_masked: string | null; status: string; legal_entity_id: string };

const VAT_OPTIONS: ContractVatOption[] = ["none", "commercial_no_vat", "commercial_full_vat", "commercial_reduced_vat"];
const ACQUISITION_KINDS: AcquisitionKind[] = ["purchase", "first_acquisition", "inheritance", "foreclosure", "gift", "other"];
const INTERVALS: PaymentInterval[] = ["monthly", "quarterly", "semiannual", "annual"];
const DUE_DAY_RULES: DueDayRule[] = ["day", "workday", "last_day", "day_next_month"];
const DEPOSIT_KINDS: DepositKind[] = ["cash", "savings_book", "insurance", "guarantee", "fixed_deposit", "letter_of_comfort", "other"];
const ROLES = ["mieter", "eigentuemer"] as const;
type Role = (typeof ROLES)[number] | "";

/** "1.234,56" or "1234,56" or "1234.56" -> "1234.56" (string, no float); null when invalid. */
export function parseAmount(input: string): string | null {
  const raw = input.trim().replace(/\s|EUR|€/g, "");
  if (!raw) return null;
  let normalised: string;
  if (raw.includes(",")) normalised = raw.replace(/\./g, "").replace(",", ".");
  else if (/^\d+\.\d{1,2}$/.test(raw)) normalised = raw;
  else normalised = raw.replace(/\./g, "");
  if (!/^\d+(\.\d{1,2})?$/.test(normalised)) return null;
  const [int, frac = ""] = normalised.split(".");
  return `${int}.${frac.padEnd(2, "0")}`;
}

type FieldErrors = Record<string, string>;

/** Maps RFC 9457 field errors (location ["body", "start_date"]) to form fields; unmapped
 *  messages are returned for the form level. Model validators of the API report the whole
 *  body, so their text lands in the general message. */
export function splitProblem(problem: Problem | null, known: readonly string[]): { fields: FieldErrors; rest: string[] } {
  const fields: FieldErrors = {};
  const rest: string[] = [];
  for (const item of problem?.errors ?? []) {
    const path = fieldPath(item.location);
    if (path && known.includes(path)) fields[path] = item.message;
    else rest.push(item.message);
  }
  return { fields, rest };
}

function Field({ label, error, help, children }: { label: string; error?: string; help?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{label}</span>
        {children}
      </label>
      {help ? <span className={ui.help}>{help}</span> : null}
      {error ? (
        <span role="alert" className={ui.error}>
          {error}
        </span>
      ) : null}
    </div>
  );
}

function Check({ label, checked, onChange, disabled }: { label: string; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span>{label}</span>
    </label>
  );
}

/** Contact search by name with role filter (Mieter, Eigentümer). Reports the picked contact. */
function PartyPicker({
  label,
  role,
  onRole,
  onPick,
  error,
}: {
  label: string;
  role: Role;
  onRole: (r: Role) => void;
  onPick: (c: ContactOption) => void;
  error?: string;
}) {
  const t = useTranslations("ContractForm");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ContactOption[]>([]);
  const [busy, setBusy] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  async function search() {
    const q = query.trim();
    if (q.length < 2) return;
    setBusy(true);
    setSearchError(null);
    const params = new URLSearchParams({ q, page_size: "10" });
    if (role) params.set("role", role);
    const res = await bff<{ items: ContactOption[] }>(`/api/bff/contacts?${params.toString()}`);
    setBusy(false);
    if (!res.ok) {
      setSearchError(res.message);
      return;
    }
    setResults(res.data.items);
    if (res.data.items.length === 0) setSearchError(t("party.noResults"));
  }

  return (
    <div className="flex flex-col gap-1">
      <span className={ui.label}>{label}</span>
      <div className="flex flex-col gap-2 sm:flex-row">
        <select className={`${ui.input} sm:w-44`} aria-label={t("party.role")} value={role} onChange={(e) => onRole(e.target.value as Role)}>
          <option value="">{t("party.roleAny")}</option>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {t(`roles.${r}`)}
            </option>
          ))}
        </select>
        <input
          className={ui.input}
          aria-label={t("party.search")}
          placeholder={t("party.placeholder")}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void search();
            }
          }}
        />
        <button type="button" className={ui.button} disabled={busy || query.trim().length < 2} onClick={() => void search()}>
          {t("party.searchButton")}
        </button>
      </div>
      {searchError ? <p className={ui.help}>{searchError}</p> : null}
      {error ? (
        <p role="alert" className={ui.error}>
          {error}
        </p>
      ) : null}
      {results.length > 0 ? (
        <ul className="flex flex-wrap gap-1" aria-label={t("party.results")}>
          {results.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                className={ui.buttonSm}
                onClick={() => {
                  onPick(c);
                  setResults([]);
                  setQuery("");
                }}
              >
                {c.display_name}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/* ---------------------------------------------------------------------------------------
 * Create
 * ------------------------------------------------------------------------------------- */

const CREATE_FIELDS = [
  "kind",
  "unit_id",
  "party_id",
  "start_date",
  "end_date",
  "legal_entity_id",
  "direct_debit",
  "sepa_mandate_id",
  "dunning_block",
  "dunning_block_reason",
  "rent_increase_block_until",
  "user_change_fee",
  "allocation_loss_risk",
  "vat_option",
  "sev_enabled",
  "sev_fee_debtor_party_id",
  "title_transfer_date",
  "benefit_burden_date",
  "acquisition_kind",
  "special_succession_liability",
  "notes",
] as const;

type ScheduleState = { enabled: boolean; interval: PaymentInterval; due_day_rule: DueDayRule; due_day: string; valid_from: string; valid_to: string };
type DepositState = { enabled: boolean; kind: DepositKind; amount: string; installments: string; valid_from: string; interest_rule: string };

function ScheduleFields({ value, onChange, errors }: { value: ScheduleState; onChange: (s: ScheduleState) => void; errors: FieldErrors }) {
  const t = useTranslations("ContractForm");
  return (
    <div className="flex flex-wrap gap-3">
      <Field label={t("schedule.interval")} error={errors["interval"]}>
        <select className={ui.input} value={value.interval} onChange={(e) => onChange({ ...value, interval: e.target.value as PaymentInterval })}>
          {INTERVALS.map((i) => (
            <option key={i} value={i}>
              {t(`intervals.${i}`)}
            </option>
          ))}
        </select>
      </Field>
      <Field label={t("schedule.dueDayRule")} error={errors["due_day_rule"]}>
        <select className={ui.input} value={value.due_day_rule} onChange={(e) => onChange({ ...value, due_day_rule: e.target.value as DueDayRule })}>
          {DUE_DAY_RULES.map((r) => (
            <option key={r} value={r}>
              {t(`dueDayRules.${r}`)}
            </option>
          ))}
        </select>
      </Field>
      <Field label={t("schedule.dueDay")} error={errors["due_day"]}>
        <input className={ui.input} type="number" min={1} max={31} value={value.due_day} onChange={(e) => onChange({ ...value, due_day: e.target.value })} />
      </Field>
      <Field label={t("schedule.validFrom")} error={errors["valid_from"]}>
        <input className={ui.input} type="date" value={value.valid_from} onChange={(e) => onChange({ ...value, valid_from: e.target.value })} />
      </Field>
      <Field label={t("schedule.validTo")} error={errors["valid_to"]}>
        <input className={ui.input} type="date" value={value.valid_to} onChange={(e) => onChange({ ...value, valid_to: e.target.value })} />
      </Field>
    </div>
  );
}

function scheduleBody(s: ScheduleState) {
  return {
    interval: s.interval,
    due_day_rule: s.due_day_rule,
    due_day: Number(s.due_day),
    valid_from: s.valid_from,
    valid_to: s.valid_to || null,
  };
}

/** Vertrag anlegen: Mietvertrag, Eigentum (WEG) oder Eigentum mit SEV. POST /contracts, then
 *  optional POST .../schedules and .../deposits, then the detail page. */
export function ContractCreateForm({ properties, initialPropertyId, initialUnitId }: { properties: PropertyOption[]; initialPropertyId?: string; initialUnitId?: string }) {
  const t = useTranslations("ContractForm");
  const router = useRouter();
  const today = new Date().toISOString().slice(0, 10);

  const [kind, setKind] = useState<ContractKind>("tenancy");
  const [propertyId, setPropertyId] = useState(initialPropertyId ?? "");
  const [units, setUnits] = useState<UnitOption[]>([]);
  const [unitId, setUnitId] = useState(initialUnitId ?? "");
  const [entities, setEntities] = useState<LegalEntityOption[]>([]);
  const [legalEntityId, setLegalEntityId] = useState("");
  const [role, setRole] = useState<Role>("mieter");
  const [party, setParty] = useState<ContactOption | null>(null);
  const [startDate, setStartDate] = useState(today);
  const [endDate, setEndDate] = useState("");
  const [directDebit, setDirectDebit] = useState(false);
  const [mandates, setMandates] = useState<MandateOption[]>([]);
  const [mandateId, setMandateId] = useState("");
  const [dunningBlock, setDunningBlock] = useState(false);
  const [dunningReason, setDunningReason] = useState("");
  const [rentBlockUntil, setRentBlockUntil] = useState("");
  const [userChangeFee, setUserChangeFee] = useState(false);
  const [allocationLossRisk, setAllocationLossRisk] = useState(false);
  const [vatOption, setVatOption] = useState<ContractVatOption>("none");
  const [sevEnabled, setSevEnabled] = useState(false);
  const [sevDebtor, setSevDebtor] = useState<ContactOption | null>(null);
  const [titleTransfer, setTitleTransfer] = useState("");
  const [benefitBurden, setBenefitBurden] = useState("");
  const [acquisitionKind, setAcquisitionKind] = useState<AcquisitionKind | "">("");
  const [succession, setSuccession] = useState(false);
  const [notes, setNotes] = useState("");
  const [schedule, setSchedule] = useState<ScheduleState>({ enabled: false, interval: "monthly", due_day_rule: "day", due_day: "3", valid_from: today, valid_to: "" });
  const [deposit, setDeposit] = useState<DepositState>({ enabled: false, kind: "cash", amount: "", installments: "1", valid_from: today, interest_rule: "" });

  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const property = properties.find((p) => p.id === propertyId) ?? null;
  const sevPossible = property?.management_type === "hoa_with_sev";

  useEffect(() => {
    if (!propertyId) {
      setUnits([]);
      setEntities([]);
      return;
    }
    let cancelled = false;
    void Promise.all([
      bff<UnitOption[]>(`/api/bff/properties/${propertyId}/units`),
      bff<LegalEntityOption[]>(`/api/bff/properties/${propertyId}/legal-entities`),
    ]).then(([u, e]) => {
      if (cancelled) return;
      setUnits(u.ok ? u.data : []);
      setEntities(e.ok ? e.data : []);
      if (!u.ok) setFormError(u.message);
    });
    return () => {
      cancelled = true;
    };
  }, [propertyId]);

  useEffect(() => {
    if (!party || !directDebit) {
      setMandates([]);
      return;
    }
    let cancelled = false;
    void bff<MandateOption[]>(`/api/bff/sepa-mandates?party_id=${party.id}&status=active`).then((res) => {
      if (!cancelled) setMandates(res.ok ? res.data : []);
    });
    return () => {
      cancelled = true;
    };
  }, [party, directDebit]);

  function pickKind(next: ContractKind) {
    setKind(next);
    setRole(next === "tenancy" ? "mieter" : "eigentuemer");
    setParty(null);
    if (next === "tenancy") {
      setSevEnabled(false);
      setSevDebtor(null);
      setTitleTransfer("");
      setBenefitBurden("");
      setAcquisitionKind("");
      setSuccession(false);
    }
  }

  function validate(): FieldErrors {
    const e: FieldErrors = {};
    if (!unitId) e["unit_id"] = t("errors.unitRequired");
    if (!party) e["party_id"] = t("errors.partyRequired");
    if (!startDate) e["start_date"] = t("errors.startRequired");
    if (endDate && startDate && endDate < startDate) e["end_date"] = t("errors.endBeforeStart");
    if (kind === "ownership") {
      if (!titleTransfer) e["title_transfer_date"] = t("errors.titleTransferRequired");
      else if (startDate && titleTransfer > startDate) e["title_transfer_date"] = t("errors.titleTransferAfterStart");
    }
    if (dunningBlock && !dunningReason.trim()) e["dunning_block_reason"] = t("errors.dunningReasonRequired");
    if (directDebit && !mandateId) e["sepa_mandate_id"] = t("errors.mandateRequired");
    if (schedule.enabled) {
      const day = Number(schedule.due_day);
      if (!Number.isInteger(day) || day < 1 || day > 31) e["due_day"] = t("errors.dueDay");
      if (!schedule.valid_from) e["valid_from"] = t("errors.validFromRequired");
    }
    if (deposit.enabled) {
      const amount = parseAmount(deposit.amount);
      if (!amount || amount === "0.00") e["amount_due"] = t("errors.amount");
      const n = Number(deposit.installments);
      if (!Number.isInteger(n) || n < 1 || n > 12) e["installments"] = t("errors.installments");
    }
    return e;
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setFormError(null);
    const clientErrors = validate();
    setErrors(clientErrors);
    if (Object.keys(clientErrors).length > 0) {
      setFormError(t("errors.checkFields"));
      return;
    }
    const body: Record<string, unknown> = {
      kind,
      unit_id: unitId,
      party_id: party!.id,
      start_date: startDate,
      end_date: endDate || null,
      legal_entity_id: legalEntityId || null,
      direct_debit: directDebit,
      sepa_mandate_id: directDebit && mandateId ? mandateId : null,
      dunning_block: dunningBlock,
      dunning_block_reason: dunningBlock ? dunningReason.trim() : null,
      rent_increase_block_until: rentBlockUntil || null,
      user_change_fee: userChangeFee,
      allocation_loss_risk: allocationLossRisk,
      vat_option: vatOption,
      notes: notes.trim() || null,
    };
    if (kind === "ownership") {
      Object.assign(body, {
        sev_enabled: sevEnabled,
        sev_fee_debtor_party_id: sevEnabled && sevDebtor ? sevDebtor.id : null,
        title_transfer_date: titleTransfer,
        benefit_burden_date: benefitBurden || null,
        acquisition_kind: acquisitionKind || null,
        special_succession_liability: succession,
      });
    }
    setBusy(true);
    const res = await bff<ContractOut>("/api/bff/contracts", { method: "POST", body: JSON.stringify(body) });
    if (!res.ok) {
      setBusy(false);
      const { fields, rest } = splitProblem(res.problem, CREATE_FIELDS);
      setErrors(fields);
      setFormError([res.message, ...rest].join(" "));
      return;
    }
    const contract = res.data;
    const followUp: string[] = [];
    if (schedule.enabled) {
      const s = await bff<ScheduleOut>(`/api/bff/contracts/${contract.id}/schedules`, { method: "POST", body: JSON.stringify(scheduleBody(schedule)) });
      if (!s.ok) followUp.push(t("errors.scheduleFailed", { message: s.message }));
    }
    if (deposit.enabled) {
      const d = await bff<{ id: string }>(`/api/bff/contracts/${contract.id}/deposits`, {
        method: "POST",
        body: JSON.stringify({
          kind: deposit.kind,
          amount_due: parseAmount(deposit.amount),
          installments: Number(deposit.installments),
          valid_from: deposit.valid_from,
          interest_rule: deposit.interest_rule.trim() || null,
        }),
      });
      if (!d.ok) followUp.push(t("errors.depositFailed", { message: d.message }));
    }
    setBusy(false);
    const query = followUp.length ? `?hinweis=${encodeURIComponent(followUp.join(" "))}` : "";
    router.push(`/vertraege/${contract.id}${query}`);
    router.refresh();
  }

  const depositAmount = parseAmount(deposit.amount);

  return (
    <form onSubmit={submit} className={`${ui.card} ${ui.sectionGap}`} data-testid="contract-form" noValidate>
      <p className={ui.notice}>{t("hint")}</p>

      <fieldset className={ui.sectionGap}>
        <legend className={ui.h2}>{t("sections.base")}</legend>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("fields.kind")} error={errors["kind"]}>
            <select className={ui.input} value={kind} onChange={(e) => pickKind(e.target.value as ContractKind)}>
              <option value="tenancy">{t("kinds.tenancy")}</option>
              <option value="ownership">{t("kinds.ownership")}</option>
            </select>
          </Field>
          <Field label={t("fields.property")} error={errors["property_id"]}>
            <select
              className={ui.input}
              value={propertyId}
              onChange={(e) => {
                setPropertyId(e.target.value);
                setUnitId("");
                setLegalEntityId("");
              }}
            >
              <option value="">{t("choose")}</option>
              {properties.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t("fields.unit")} error={errors["unit_id"]}>
            <select className={ui.input} value={unitId} disabled={!propertyId} onChange={(e) => setUnitId(e.target.value)}>
              <option value="">{t("choose")}</option>
              {units.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.number}
                  {u.label ? ` ${u.label}` : ""}
                </option>
              ))}
            </select>
          </Field>
          {entities.length > 1 ? (
            <Field label={t("fields.legalEntity")} help={t("fields.legalEntityHelp")} error={errors["legal_entity_id"]}>
              <select className={ui.input} value={legalEntityId} onChange={(e) => setLegalEntityId(e.target.value)}>
                <option value="">{t("fields.legalEntityAuto")}</option>
                {entities.map((le) => (
                  <option key={le.id} value={le.id}>
                    {le.name}
                  </option>
                ))}
              </select>
            </Field>
          ) : null}
        </div>
        <PartyPicker label={t("fields.party")} role={role} onRole={setRole} onPick={setParty} error={errors["party_id"]} />
        {party ? (
          <p className="text-sm" data-testid="picked-party">
            {t("party.picked")} <strong>{party.display_name}</strong>{" "}
            <button type="button" className={ui.buttonSm} onClick={() => setParty(null)}>
              {t("party.remove")}
            </button>
          </p>
        ) : null}
      </fieldset>

      <fieldset className={ui.sectionGap}>
        <legend className={ui.h2}>{t("sections.term")}</legend>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label={t("fields.startDate")} error={errors["start_date"]}>
            <input className={ui.input} type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </Field>
          <Field label={t("fields.endDate")} help={t("fields.endDateHelp")} error={errors["end_date"]}>
            <input className={ui.input} type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
          </Field>
          {kind === "tenancy" ? (
            <Field label={t("fields.rentIncreaseBlockUntil")} error={errors["rent_increase_block_until"]}>
              <input className={ui.input} type="date" value={rentBlockUntil} onChange={(e) => setRentBlockUntil(e.target.value)} />
            </Field>
          ) : null}
        </div>
      </fieldset>

      {kind === "ownership" ? (
        <fieldset className={ui.sectionGap}>
          <legend className={ui.h2}>{t("sections.ownership")}</legend>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label={t("fields.titleTransferDate")} help={t("fields.titleTransferHelp")} error={errors["title_transfer_date"]}>
              <input className={ui.input} type="date" value={titleTransfer} onChange={(e) => setTitleTransfer(e.target.value)} />
            </Field>
            <Field label={t("fields.benefitBurdenDate")} error={errors["benefit_burden_date"]}>
              <input className={ui.input} type="date" value={benefitBurden} onChange={(e) => setBenefitBurden(e.target.value)} />
            </Field>
            <Field label={t("fields.acquisitionKind")} error={errors["acquisition_kind"]}>
              <select className={ui.input} value={acquisitionKind} onChange={(e) => setAcquisitionKind(e.target.value as AcquisitionKind | "")}>
                <option value="">{t("choose")}</option>
                {ACQUISITION_KINDS.map((k) => (
                  <option key={k} value={k}>
                    {t(`acquisitionKinds.${k}`)}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <Check label={t("fields.specialSuccessionLiability")} checked={succession} onChange={setSuccession} />
          {sevPossible ? (
            <>
              <Check label={t("fields.sevEnabled")} checked={sevEnabled} onChange={setSevEnabled} />
              {sevEnabled ? (
                <>
                  <PartyPicker label={t("fields.sevFeeDebtor")} role={role} onRole={setRole} onPick={setSevDebtor} error={errors["sev_fee_debtor_party_id"]} />
                  {sevDebtor ? (
                    <p className="text-sm">
                      {t("party.picked")} <strong>{sevDebtor.display_name}</strong>{" "}
                      <button type="button" className={ui.buttonSm} onClick={() => setSevDebtor(null)}>
                        {t("party.remove")}
                      </button>
                    </p>
                  ) : null}
                </>
              ) : null}
            </>
          ) : (
            <p className={ui.help}>{t("fields.sevNotPossible")}</p>
          )}
        </fieldset>
      ) : null}

      <fieldset className={ui.sectionGap}>
        <legend className={ui.h2}>{t("sections.payment")}</legend>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("fields.vatOption")} error={errors["vat_option"]}>
            <select className={ui.input} value={vatOption} onChange={(e) => setVatOption(e.target.value as ContractVatOption)}>
              {VAT_OPTIONS.map((v) => (
                <option key={v} value={v}>
                  {t(`vatOptions.${v}`)}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <Check label={t("fields.directDebit")} checked={directDebit} onChange={setDirectDebit} />
        {directDebit ? (
          <Field label={t("fields.sepaMandate")} help={t("fields.sepaMandateHelp")} error={errors["sepa_mandate_id"]}>
            <select className={ui.input} value={mandateId} onChange={(e) => setMandateId(e.target.value)} disabled={!party}>
              <option value="">{party ? (mandates.length ? t("choose") : t("fields.noMandates")) : t("fields.pickPartyFirst")}</option>
              {mandates.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.reference}
                  {m.iban_masked ? ` (${m.iban_masked})` : ""}
                </option>
              ))}
            </select>
          </Field>
        ) : null}
        <Check label={t("fields.dunningBlock")} checked={dunningBlock} onChange={setDunningBlock} />
        {dunningBlock ? (
          <Field label={t("fields.dunningBlockReason")} error={errors["dunning_block_reason"]}>
            <input className={ui.input} value={dunningReason} onChange={(e) => setDunningReason(e.target.value)} />
          </Field>
        ) : null}
        {kind === "tenancy" ? (
          <>
            <Check label={t("fields.userChangeFee")} checked={userChangeFee} onChange={setUserChangeFee} />
            <Check label={t("fields.allocationLossRisk")} checked={allocationLossRisk} onChange={setAllocationLossRisk} />
          </>
        ) : null}
      </fieldset>

      <fieldset className={ui.sectionGap}>
        <legend className={ui.h2}>{t("sections.schedule")}</legend>
        <p className={ui.help}>{t("schedule.help")}</p>
        <Check label={t("schedule.enable")} checked={schedule.enabled} onChange={(v) => setSchedule({ ...schedule, enabled: v })} />
        {schedule.enabled ? <ScheduleFields value={schedule} onChange={setSchedule} errors={errors} /> : null}
      </fieldset>

      {kind === "tenancy" ? (
        <fieldset className={ui.sectionGap}>
          <legend className={ui.h2}>{t("sections.deposit")}</legend>
          <Check label={t("deposit.enable")} checked={deposit.enabled} onChange={(v) => setDeposit({ ...deposit, enabled: v })} />
          {deposit.enabled ? (
            <div className="flex flex-wrap gap-3">
              <Field label={t("deposit.kind")} error={errors["kind_deposit"]}>
                <select className={ui.input} value={deposit.kind} onChange={(e) => setDeposit({ ...deposit, kind: e.target.value as DepositKind })}>
                  {DEPOSIT_KINDS.map((k) => (
                    <option key={k} value={k}>
                      {t(`depositKinds.${k}`)}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={t("deposit.amount")} help={depositAmount ? formatEur(depositAmount) : t("deposit.amountHelp")} error={errors["amount_due"]}>
                <input className={ui.input} inputMode="decimal" placeholder="1.234,56" value={deposit.amount} onChange={(e) => setDeposit({ ...deposit, amount: e.target.value })} />
              </Field>
              <Field label={t("deposit.installments")} error={errors["installments"]}>
                <input className={ui.input} type="number" min={1} max={12} value={deposit.installments} onChange={(e) => setDeposit({ ...deposit, installments: e.target.value })} />
              </Field>
              <Field label={t("deposit.validFrom")} error={errors["valid_from_deposit"]}>
                <input className={ui.input} type="date" value={deposit.valid_from} onChange={(e) => setDeposit({ ...deposit, valid_from: e.target.value })} />
              </Field>
              <Field label={t("deposit.interestRule")} error={errors["interest_rule"]}>
                <input className={ui.input} value={deposit.interest_rule} onChange={(e) => setDeposit({ ...deposit, interest_rule: e.target.value })} />
              </Field>
            </div>
          ) : null}
        </fieldset>
      ) : null}

      <Field label={t("fields.notes")} error={errors["notes"]}>
        <textarea className={ui.input} rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </Field>

      {formError ? (
        <p role="alert" className={ui.alert}>
          {formError}
        </p>
      ) : null}
      <div className={ui.formActions}>
        <button type="submit" className={`${ui.primary} ${ui.actionFull}`} disabled={busy}>
          {t("actions.create")}
        </button>
        <Link href="/vertraege" className={`${ui.button} ${ui.actionFull}`}>
          {t("actions.cancel")}
        </Link>
      </div>
    </form>
  );
}

/* ---------------------------------------------------------------------------------------
 * Edit: new version, termination, additional schedule
 * ------------------------------------------------------------------------------------- */

const VERSION_FIELDS = [
  "effective_date",
  "direct_debit",
  "sepa_mandate_id",
  "dunning_block",
  "dunning_block_reason",
  "rent_increase_block_until",
  "user_change_fee",
  "allocation_loss_risk",
  "vat_option",
  "notes",
] as const;

const TERMINATION_FIELDS = ["end_date", "termination_date", "termination_reason"] as const;
const SCHEDULE_FIELDS = ["interval", "due_day_rule", "due_day", "valid_from", "valid_to"] as const;

/** Vertrag bearbeiten: the API keeps posted versions; a change after the start creates a
 *  new version from an effective date (ContractVersionIn). Tenancies can be ended with a
 *  termination; ownership ends only by an ownership transfer. */
export function ContractEditForm({ contract, partyName, unitLabel, propertyLabel }: { contract: ContractOut; partyName: string; unitLabel: string; propertyLabel: string }) {
  const t = useTranslations("ContractForm");
  const router = useRouter();
  const today = new Date().toISOString().slice(0, 10);

  const [effectiveDate, setEffectiveDate] = useState(today);
  const [directDebit, setDirectDebit] = useState(contract.direct_debit);
  const [mandates, setMandates] = useState<MandateOption[]>([]);
  const [mandateId, setMandateId] = useState(contract.sepa_mandate_id ?? "");
  const [dunningBlock, setDunningBlock] = useState(contract.dunning_block);
  const [dunningReason, setDunningReason] = useState(contract.dunning_block_reason ?? "");
  const [rentBlockUntil, setRentBlockUntil] = useState(contract.rent_increase_block_until ?? "");
  const [userChangeFee, setUserChangeFee] = useState(contract.user_change_fee);
  const [allocationLossRisk, setAllocationLossRisk] = useState(contract.allocation_loss_risk);
  const [vatOption, setVatOption] = useState<ContractVatOption>(contract.vat_option);
  const [notes, setNotes] = useState(contract.notes ?? "");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [termEnd, setTermEnd] = useState("");
  const [termDate, setTermDate] = useState(today);
  const [termReason, setTermReason] = useState("");
  const [termErrors, setTermErrors] = useState<FieldErrors>({});
  const [termError, setTermError] = useState<string | null>(null);

  const [schedule, setSchedule] = useState<ScheduleState>({ enabled: true, interval: "monthly", due_day_rule: "day", due_day: "3", valid_from: today, valid_to: "" });
  const [scheduleErrors, setScheduleErrors] = useState<FieldErrors>({});
  const [scheduleError, setScheduleError] = useState<string | null>(null);
  const [scheduleDone, setScheduleDone] = useState<ScheduleOut[]>(contract.schedules);

  useEffect(() => {
    if (!directDebit) return;
    let cancelled = false;
    void bff<MandateOption[]>(`/api/bff/sepa-mandates?party_id=${contract.party_id}&status=active`).then((res) => {
      if (!cancelled) setMandates(res.ok ? res.data : []);
    });
    return () => {
      cancelled = true;
    };
  }, [directDebit, contract.party_id]);

  async function submitVersion(event: React.FormEvent) {
    event.preventDefault();
    setFormError(null);
    const e: FieldErrors = {};
    if (!effectiveDate) e["effective_date"] = t("errors.effectiveDateRequired");
    else if (effectiveDate <= contract.start_date) e["effective_date"] = t("errors.effectiveDateAfterStart");
    else if (contract.end_date && effectiveDate > contract.end_date) e["effective_date"] = t("errors.effectiveDateBeforeEnd");
    if (dunningBlock && !dunningReason.trim()) e["dunning_block_reason"] = t("errors.dunningReasonRequired");
    if (directDebit && !mandateId) e["sepa_mandate_id"] = t("errors.mandateRequired");
    setErrors(e);
    if (Object.keys(e).length > 0) {
      setFormError(t("errors.checkFields"));
      return;
    }
    const body = {
      effective_date: effectiveDate,
      direct_debit: directDebit,
      sepa_mandate_id: directDebit && mandateId ? mandateId : null,
      dunning_block: dunningBlock,
      dunning_block_reason: dunningBlock ? dunningReason.trim() : null,
      rent_increase_block_until: rentBlockUntil || null,
      user_change_fee: userChangeFee,
      allocation_loss_risk: allocationLossRisk,
      vat_option: vatOption,
      notes: notes.trim() || null,
    };
    setBusy(true);
    const res = await bff<ContractOut>(`/api/bff/contracts/${contract.id}/versions`, { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) {
      const { fields, rest } = splitProblem(res.problem, VERSION_FIELDS);
      setErrors(fields);
      setFormError([res.message, ...rest].join(" "));
      return;
    }
    router.push(`/vertraege/${res.data.id}`);
    router.refresh();
  }

  async function submitTermination(event: React.FormEvent) {
    event.preventDefault();
    setTermError(null);
    const e: FieldErrors = {};
    if (!termEnd) e["end_date"] = t("errors.endRequired");
    else if (termEnd < contract.start_date) e["end_date"] = t("errors.endBeforeStart");
    setTermErrors(e);
    if (Object.keys(e).length > 0) return;
    setBusy(true);
    const res = await bff<ContractOut>(`/api/bff/contracts/${contract.id}/termination`, {
      method: "POST",
      body: JSON.stringify({ end_date: termEnd, termination_date: termDate || null, termination_reason: termReason.trim() || null }),
    });
    setBusy(false);
    if (!res.ok) {
      const { fields, rest } = splitProblem(res.problem, TERMINATION_FIELDS);
      setTermErrors(fields);
      setTermError([res.message, ...rest].join(" "));
      return;
    }
    router.push(`/vertraege/${res.data.id}`);
    router.refresh();
  }

  async function submitSchedule(event: React.FormEvent) {
    event.preventDefault();
    setScheduleError(null);
    const e: FieldErrors = {};
    const day = Number(schedule.due_day);
    if (!Number.isInteger(day) || day < 1 || day > 31) e["due_day"] = t("errors.dueDay");
    if (!schedule.valid_from) e["valid_from"] = t("errors.validFromRequired");
    setScheduleErrors(e);
    if (Object.keys(e).length > 0) return;
    setBusy(true);
    const res = await bff<ScheduleOut>(`/api/bff/contracts/${contract.id}/schedules`, { method: "POST", body: JSON.stringify(scheduleBody(schedule)) });
    setBusy(false);
    if (!res.ok) {
      const { fields, rest } = splitProblem(res.problem, SCHEDULE_FIELDS);
      setScheduleErrors(fields);
      setScheduleError([res.message, ...rest].join(" "));
      return;
    }
    setScheduleDone((prev) => [...prev, res.data]);
  }

  const ended = contract.end_date !== null;

  return (
    <div className={ui.sectionGap}>
      <section className={ui.card} data-testid="contract-fixed">
        <h2 className={ui.h2}>{t("edit.fixedTitle")}</h2>
        <p className={ui.help}>{t("edit.fixedHelp")}</p>
        <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
          <dt className={ui.label}>{t("fields.number")}</dt>
          <dd>
            {contract.number} ({t("edit.version", { n: contract.version })})
          </dd>
          <dt className={ui.label}>{t("fields.kind")}</dt>
          <dd>{t(`kinds.${contract.kind}`)}</dd>
          <dt className={ui.label}>{t("fields.property")}</dt>
          <dd>{propertyLabel}</dd>
          <dt className={ui.label}>{t("fields.unit")}</dt>
          <dd>{unitLabel}</dd>
          <dt className={ui.label}>{t("fields.party")}</dt>
          <dd>{partyName}</dd>
          <dt className={ui.label}>{t("fields.startDate")}</dt>
          <dd>{formatDate(contract.start_date)}</dd>
          <dt className={ui.label}>{t("fields.endDate")}</dt>
          <dd>{contract.end_date ? formatDate(contract.end_date) : t("edit.openEnd")}</dd>
          {contract.kind === "ownership" ? (
            <>
              <dt className={ui.label}>{t("fields.titleTransferDate")}</dt>
              <dd>{formatDate(contract.title_transfer_date)}</dd>
              <dt className={ui.label}>{t("fields.sevEnabled")}</dt>
              <dd>{contract.sev_enabled ? t("yes") : t("no")}</dd>
            </>
          ) : null}
        </dl>
      </section>

      <form onSubmit={submitVersion} className={`${ui.card} ${ui.sectionGap}`} data-testid="contract-version-form" noValidate>
        <h2 className={ui.h2}>{t("edit.versionTitle")}</h2>
        <p className={ui.help}>{t("edit.versionHelp")}</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("fields.effectiveDate")} error={errors["effective_date"]}>
            <input className={ui.input} type="date" value={effectiveDate} onChange={(e) => setEffectiveDate(e.target.value)} />
          </Field>
          <Field label={t("fields.vatOption")} error={errors["vat_option"]}>
            <select className={ui.input} value={vatOption} onChange={(e) => setVatOption(e.target.value as ContractVatOption)}>
              {VAT_OPTIONS.map((v) => (
                <option key={v} value={v}>
                  {t(`vatOptions.${v}`)}
                </option>
              ))}
            </select>
          </Field>
          {contract.kind === "tenancy" ? (
            <Field label={t("fields.rentIncreaseBlockUntil")} error={errors["rent_increase_block_until"]}>
              <input className={ui.input} type="date" value={rentBlockUntil} onChange={(e) => setRentBlockUntil(e.target.value)} />
            </Field>
          ) : null}
        </div>
        <Check label={t("fields.directDebit")} checked={directDebit} onChange={setDirectDebit} />
        {directDebit ? (
          <Field label={t("fields.sepaMandate")} help={t("fields.sepaMandateHelp")} error={errors["sepa_mandate_id"]}>
            <select className={ui.input} value={mandateId} onChange={(e) => setMandateId(e.target.value)}>
              <option value="">{mandates.length ? t("choose") : t("fields.noMandates")}</option>
              {mandates.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.reference}
                  {m.iban_masked ? ` (${m.iban_masked})` : ""}
                </option>
              ))}
            </select>
          </Field>
        ) : null}
        <Check label={t("fields.dunningBlock")} checked={dunningBlock} onChange={setDunningBlock} />
        {dunningBlock ? (
          <Field label={t("fields.dunningBlockReason")} error={errors["dunning_block_reason"]}>
            <input className={ui.input} value={dunningReason} onChange={(e) => setDunningReason(e.target.value)} />
          </Field>
        ) : null}
        {contract.kind === "tenancy" ? (
          <>
            <Check label={t("fields.userChangeFee")} checked={userChangeFee} onChange={setUserChangeFee} />
            <Check label={t("fields.allocationLossRisk")} checked={allocationLossRisk} onChange={setAllocationLossRisk} />
          </>
        ) : null}
        <Field label={t("fields.notes")} error={errors["notes"]}>
          <textarea className={ui.input} rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Field>
        {formError ? (
          <p role="alert" className={ui.alert}>
            {formError}
          </p>
        ) : null}
        <div className={ui.formActions}>
          <button type="submit" className={`${ui.primary} ${ui.actionFull}`} disabled={busy}>
            {t("actions.saveVersion")}
          </button>
          <Link href={`/vertraege/${contract.id}`} className={`${ui.button} ${ui.actionFull}`}>
            {t("actions.cancel")}
          </Link>
        </div>
      </form>

      <form onSubmit={submitSchedule} className={`${ui.card} ${ui.sectionGap}`} data-testid="contract-schedule-form" noValidate>
        <h2 className={ui.h2}>{t("sections.schedule")}</h2>
        {scheduleDone.length > 0 ? (
          <ul className="text-sm" aria-label={t("schedule.existing")}>
            {scheduleDone.map((s) => (
              <li key={s.id}>
                {t(`intervals.${s.interval}`)}, {t(`dueDayRules.${s.due_day_rule}`)} {s.due_day}, {t("schedule.from")} {formatDate(s.valid_from)}
                {s.valid_to ? ` ${t("schedule.to")} ${formatDate(s.valid_to)}` : ""}
              </li>
            ))}
          </ul>
        ) : (
          <p className={ui.help}>{t("schedule.none")}</p>
        )}
        <p className={ui.help}>{t("schedule.help")}</p>
        <ScheduleFields value={schedule} onChange={setSchedule} errors={scheduleErrors} />
        {scheduleError ? (
          <p role="alert" className={ui.alert}>
            {scheduleError}
          </p>
        ) : null}
        <div className={ui.formActions}>
          <button type="submit" className={`${ui.secondary} ${ui.actionFull}`} disabled={busy}>
            {t("actions.addSchedule")}
          </button>
        </div>
      </form>

      {contract.kind === "tenancy" ? (
        <form onSubmit={submitTermination} className={`${ui.card} ${ui.sectionGap}`} data-testid="contract-termination-form" noValidate>
          <h2 className={ui.h2}>{t("termination.title")}</h2>
          <p className={ui.notice}>{t("termination.approval")}</p>
          {ended ? <p className={ui.help}>{t("termination.alreadyEnded", { date: formatDate(contract.end_date) })}</p> : null}
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label={t("termination.endDate")} error={termErrors["end_date"]}>
              <input className={ui.input} type="date" value={termEnd} onChange={(e) => setTermEnd(e.target.value)} />
            </Field>
            <Field label={t("termination.terminationDate")} error={termErrors["termination_date"]}>
              <input className={ui.input} type="date" value={termDate} onChange={(e) => setTermDate(e.target.value)} />
            </Field>
            <Field label={t("termination.reason")} error={termErrors["termination_reason"]}>
              <input className={ui.input} value={termReason} onChange={(e) => setTermReason(e.target.value)} />
            </Field>
          </div>
          {termError ? (
            <p role="alert" className={ui.alert}>
              {termError}
            </p>
          ) : null}
          <div className={ui.formActions}>
            <button type="submit" className={`${ui.danger} ${ui.actionFull}`} disabled={busy}>
              {t("actions.terminate")}
            </button>
          </div>
        </form>
      ) : (
        <p className={ui.notice}>{t("termination.ownershipHint")}</p>
      )}
    </div>
  );
}

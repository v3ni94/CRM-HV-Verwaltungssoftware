"use client";
/** Einrichtung in drei Schritten (Bank, Regel M11-08): (1) Bankzugang wählen, FinTS-Verbindung
 *  oder Kontoauszug per Datei, (2) Konto wählen, (3) Objekt und Kontoart; der Rechtsträger
 *  folgt aus dem Objekt (WEG-Konto und Rücklagenkonto der GdWE, Mietkonto und Kautionskonto
 *  dem Eigentümer, 6.9.1). Danach zeigt der Abschluss, was mit den Umsätzen passiert.
 *  Bestehende Endpunkte: `POST /banking/fints/accounts/{id}/assign` (Objekt, Rechtsträger,
 *  Kontoart, Inhaber) und `POST /properties/{id}/bank-accounts` für den Dateiweg. Lesend
 *  gegenüber der Bank; keine Zahlung, keine Buchung. */
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import { FinTsConnectDialog, type FinTsAccount, type FinTsConnection } from "./FinTsConnections";

type Source = "fints" | "file";
export type SetupKind = "rent" | "hoa" | "reserve" | "deposit";
type LegalEntity = { id: string; kind: string; name: string };
type PropertySummary = { id: string; number: string; name: string; management_type: string };

export const KINDS: SetupKind[] = ["rent", "hoa", "reserve", "deposit"];

/** Owner kinds per account kind (mirror of `properties.services.ACCOUNT_OWNERS`, 6.9.1). */
export const OWNER_KINDS: Record<SetupKind, string[]> = {
  hoa: ["hoa"],
  reserve: ["hoa"],
  rent: ["rental_owner", "sev_owner"],
  deposit: ["rental_owner", "sev_owner"],
};

/** Inline form of the FinTS table also offers `other` (any legal entity kind may hold it,
 *  `ACCOUNT_OWNERS[OTHER]` in `properties.services`, GAH-404). */
export type InlineKind = SetupKind | "other";
export const INLINE_KINDS: InlineKind[] = [...KINDS, "other"];

export function ownersFor(kind: InlineKind, entities: LegalEntity[]): LegalEntity[] {
  if (kind === "other") return entities;
  return entities.filter((e) => OWNER_KINDS[kind].includes(e.kind));
}

export function todayIso(): string {
  return new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Berlin" }).format(new Date());
}

const IBAN = /^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$/;

export function normaliseIban(value: string): string {
  return value.replace(/\s+/g, "").toUpperCase();
}

export function BankSetupWizard() {
  const t = useTranslations("BankSetup");
  const tk = useTranslations("BankAccounts.kind");
  const te = useTranslations("Properties.entityKind");
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);
  const [source, setSource] = useState<Source>("fints");
  const [connections, setConnections] = useState<FinTsConnection[] | null>(null);
  const [connectDialog, setConnectDialog] = useState(false);
  const [account, setAccount] = useState<{ link: FinTsAccount; bank: string } | null>(null);
  const [iban, setIban] = useState("");
  const [bankName, setBankName] = useState("");
  const [properties, setProperties] = useState<PropertySummary[]>([]);
  const [propertyId, setPropertyId] = useState("");
  const [entities, setEntities] = useState<LegalEntity[]>([]);
  const [kind, setKind] = useState<SetupKind>("hoa");
  const [legalEntityId, setLegalEntityId] = useState("");
  const [holder, setHolder] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ ibanMasked: string } | null>(null);

  /** Deep link from the FinTS account table (GAG-01): `?setup=fints&link=<id>` opens the
   *  wizard with that bank account preselected and jumps to step 3. */
  const [deepLink, setDeepLink] = useState<string | null>(null);
  useEffect(() => {
    try {
      const q = new URLSearchParams(window.location.search);
      const link = q.get("link");
      if (q.get("setup") === "fints" && link) {
        setDeepLink(link);
        setSource("fints");
        setOpen(true);
      }
    } catch {
      /* no location (tests, SSR) */
    }
  }, []);

  const loadConnections = useCallback(async () => {
    const res = await bff<FinTsConnection[]>("/api/bff/banking/fints/connections");
    setConnections(res.ok ? res.data : []);
  }, []);

  useEffect(() => {
    if (!open) return;
    void loadConnections();
    bff<{ items: PropertySummary[] }>("/api/bff/properties?page_size=200").then((r) => {
      if (r.ok) setProperties(r.data.items);
    });
  }, [open, loadConnections]);

  useEffect(() => {
    if (!propertyId) {
      setEntities([]);
      return;
    }
    bff<LegalEntity[]>(`/api/bff/properties/${propertyId}/legal-entities`).then((r) => setEntities(r.ok ? r.data : []));
  }, [propertyId]);

  const owners = useMemo(() => ownersFor(kind, entities), [kind, entities]);
  useEffect(() => {
    const first = owners[0];
    if (!first) {
      setLegalEntityId("");
      return;
    }
    if (!owners.some((o) => o.id === legalEntityId)) setLegalEntityId(first.id);
  }, [owners, legalEntityId]);
  useEffect(() => {
    const entity = owners.find((o) => o.id === legalEntityId);
    if (entity && !holder) setHolder(entity.name);
  }, [owners, legalEntityId, holder]);

  const unassigned = useMemo(
    () => (connections ?? []).flatMap((c) => c.accounts.filter((a) => !a.property_bank_account_id).map((a) => ({ link: a, bank: c.bank_name }))),
    [connections],
  );
  useEffect(() => {
    if (!deepLink || connections === null) return;
    const hit = unassigned.find((u) => u.link.id === deepLink);
    setDeepLink(null);
    if (hit) {
      setAccount(hit);
      setStep(3);
    }
  }, [deepLink, connections, unassigned]);
  const ibanClean = normaliseIban(iban);
  const ibanValid = IBAN.test(ibanClean);
  const stepTwoReady = source === "fints" ? account !== null : ibanValid;
  const property = properties.find((p) => p.id === propertyId) ?? null;

  function reset() {
    setStep(1);
    setAccount(null);
    setIban("");
    setBankName("");
    setPropertyId("");
    setKind("hoa");
    setLegalEntityId("");
    setHolder("");
    setError(null);
    setDone(null);
  }

  async function submit() {
    if (!propertyId || !legalEntityId || holder.trim().length < 2) return;
    setBusy(true);
    setError(null);
    const body = { property_id: propertyId, legal_entity_id: legalEntityId, kind, holder: holder.trim() };
    const res =
      source === "fints" && account
        ? await bff<{ iban_suffix: string }>(`/api/bff/banking/fints/accounts/${account.link.id}/assign`, { method: "POST", body: JSON.stringify(body) })
        : await bff<{ iban_masked: string }>(`/api/bff/properties/${propertyId}/bank-accounts`, {
            method: "POST",
            body: JSON.stringify({ legal_entity_id: legalEntityId, kind, iban: ibanClean, holder: holder.trim(), bank_name: bankName.trim() || null, valid_from: todayIso() }),
          });
    setBusy(false);
    if (!res.ok) {
      setError(res.status === 403 ? t("noPermission") : res.message);
      return;
    }
    const data = res.data as { iban_suffix?: string; iban_masked?: string };
    setDone({ ibanMasked: data.iban_masked ?? `…${data.iban_suffix ?? ibanClean.slice(-4)}` });
    setStep(4);
    await loadConnections();
  }

  return (
    <section className={ui.card} data-testid="bank-setup">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className={ui.h2}>{t("title")}</h2>
        <button type="button" className={ui.primary} onClick={() => { reset(); setOpen((v) => !v); }}>
          {open ? t("close") : t("start")}
        </button>
      </div>
      <p className="mt-1 text-sm text-muted">{t("intro")}</p>
      {open ? (
        <div className="mt-3 flex flex-col gap-4">
          <ol className="flex flex-wrap gap-3 text-sm" aria-label={t("steps")}>
            {([1, 2, 3, 4] as const).map((n) => (
              <li key={n} className={n === step ? "font-semibold" : "text-muted"} aria-current={n === step ? "step" : undefined}>
                {t(`step${n}`)}
              </li>
            ))}
          </ol>
          {error ? <p role="alert" className={ui.alert}>{error}</p> : null}

          {step === 1 ? (
            <div className="flex flex-col gap-3">
              <fieldset className="flex flex-col gap-2">
                <legend className={ui.label}>{t("sourceLabel")}</legend>
                <label className="flex items-start gap-2 text-sm">
                  <input type="radio" name="bank-setup-source" checked={source === "fints"} onChange={() => setSource("fints")} />
                  <span><span className="font-medium">{t("sourceFints")}</span><span className="block text-muted">{t("sourceFintsHelp")}</span></span>
                </label>
                <label className="flex items-start gap-2 text-sm">
                  <input type="radio" name="bank-setup-source" checked={source === "file"} onChange={() => setSource("file")} />
                  <span><span className="font-medium">{t("sourceFile")}</span><span className="block text-muted">{t("sourceFileHelp")}</span></span>
                </label>
              </fieldset>
              {source === "fints" ? (
                <div className="flex flex-col gap-2 text-sm">
                  {connections === null ? <p className="text-muted">{t("loading")}</p> : null}
                  {connections && connections.length === 0 ? <p className="text-muted">{t("noConnections")}</p> : null}
                  {connections && connections.length > 0 ? (
                    <ul className="flex flex-col gap-1">
                      {connections.map((c) => (
                        <li key={c.id}>
                          <span className="font-medium">{c.bank_name}</span> <span className="text-muted">{t("accountsCount", { count: c.accounts.length })}</span>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  <div>
                    <button type="button" className={ui.buttonSm} onClick={() => setConnectDialog(true)}>
                      {t("connectNew")}
                    </button>
                  </div>
                </div>
              ) : null}
              <div className={ui.formActions}>
                <button type="button" className={ui.primary} disabled={source === "fints" && unassigned.length === 0} onClick={() => setStep(2)}>
                  {t("next")}
                </button>
              </div>
              {source === "fints" && connections && unassigned.length === 0 && connections.length > 0 ? <p className={ui.help}>{t("allAssigned")}</p> : null}
            </div>
          ) : null}

          {step === 2 ? (
            <div className="flex flex-col gap-3">
              {source === "fints" ? (
                <fieldset className="flex flex-col gap-2">
                  <legend className={ui.label}>{t("chooseAccount")}</legend>
                  {unassigned.map(({ link, bank }) => (
                    <label key={link.id} className="flex items-center gap-2 text-sm">
                      <input type="radio" name="bank-setup-account" checked={account?.link.id === link.id} onChange={() => setAccount({ link, bank })} />
                      <span className={ui.mono}>…{link.iban_suffix}</span>
                      <span className="text-muted">{bank}{link.bic ? `, ${link.bic}` : ""}</span>
                    </label>
                  ))}
                </fieldset>
              ) : (
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className={ui.label}>
                    {t("iban")}
                    <input className={ui.input} value={iban} onChange={(e) => setIban(e.target.value)} placeholder="DE00 0000 0000 0000 0000 00" aria-invalid={iban.length > 0 && !ibanValid} />
                  </label>
                  <label className={ui.label}>
                    {t("bankName")}
                    <input className={ui.input} value={bankName} onChange={(e) => setBankName(e.target.value)} />
                  </label>
                  <p className={`${ui.help} sm:col-span-2`}>{t("fileHelp")}</p>
                </div>
              )}
              <div className={ui.formActions}>
                <button type="button" className={ui.button} onClick={() => setStep(1)}>{t("back")}</button>
                <button type="button" className={ui.primary} disabled={!stepTwoReady} onClick={() => setStep(3)}>{t("next")}</button>
              </div>
            </div>
          ) : null}

          {step === 3 ? (
            <div className="flex flex-col gap-3">
              <div className="grid gap-3 sm:grid-cols-2">
                <label className={ui.label}>
                  {t("property")}
                  <select className={ui.input} value={propertyId} onChange={(e) => { setPropertyId(e.target.value); setHolder(""); }}>
                    <option value="">{t("chooseProperty")}</option>
                    {properties.map((p) => (
                      <option key={p.id} value={p.id}>{p.number} {p.name}</option>
                    ))}
                  </select>
                </label>
                <label className={ui.label}>
                  {t("kind")}
                  <select className={ui.input} value={kind} onChange={(e) => { setKind(e.target.value as SetupKind); setHolder(""); }}>
                    {KINDS.map((k) => (
                      <option key={k} value={k}>{tk(k)}</option>
                    ))}
                  </select>
                </label>
                <label className={ui.label}>
                  {t("legalEntity")}
                  {owners.length > 1 ? (
                    <select className={ui.input} value={legalEntityId} onChange={(e) => { setLegalEntityId(e.target.value); setHolder(""); }}>
                      {owners.map((o) => (
                        <option key={o.id} value={o.id}>{te(o.kind)}: {o.name}</option>
                      ))}
                    </select>
                  ) : (
                    <span className="block text-sm" data-testid="bank-setup-entity">
                      {owners[0] ? `${te(owners[0].kind)}: ${owners[0].name}` : propertyId ? t("noOwner", { kind: tk(kind) }) : t("chooseFirst")}
                    </span>
                  )}
                  <span className={ui.help}>{t("legalEntityHelp")}</span>
                </label>
                <label className={ui.label}>
                  {t("holder")}
                  <input className={ui.input} value={holder} onChange={(e) => setHolder(e.target.value)} />
                </label>
              </div>
              <div className={ui.formActions}>
                <button type="button" className={ui.button} onClick={() => setStep(2)}>{t("back")}</button>
                <button type="button" className={ui.primary} disabled={busy || !propertyId || !legalEntityId || holder.trim().length < 2} onClick={submit}>
                  {t("finish")}
                </button>
              </div>
            </div>
          ) : null}

          {step === 4 && done && property ? (
            <div className="flex flex-col gap-2 text-sm" data-testid="bank-setup-done">
              <p className={ui.success}>{t("doneTitle", { iban: done.ibanMasked, kind: tk(kind), property: `${property.number} ${property.name}` })}</p>
              <h3 className={ui.h3}>{t("nextTitle")}</h3>
              <ul className="list-disc pl-5">
                <li>{source === "fints" ? t("nextFints") : t("nextFile")}</li>
                <li>{t("nextPosting")}</li>
                <li>{t("nextCreditors")}</li>
                <li>{t("nextGate")}</li>
              </ul>
              <p>
                <Link href={`/objekte/${property.id}`} className="hover:underline">{t("toProperty")}</Link>
              </p>
              <div className={ui.formActions}>
                <button type="button" className={ui.button} onClick={reset}>{t("another")}</button>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
      {connectDialog ? (
        <FinTsConnectDialog
          onClose={() => setConnectDialog(false)}
          onChanged={async () => {
            await loadConnections();
          }}
        />
      ) : null}
    </section>
  );
}

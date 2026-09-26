"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import { BankAccountCard } from "./BankAccountCard";
import { BankAccountSelect } from "./BankAccountSelect";
import { accountsUrl, type BankAccountOption } from "./bankAccountTypes";

type PropertySummary = { id: string; number: string; name: string };

/** Bankseite: Kontenauswahl je Objekt und Rechtsträger mit Kontostand und letzten Umsätzen.
 *  Lesend; Zuordnungen werden auf der Objektseite (Reiter Bank) gepflegt. */
export function BankAccountOverview() {
  const t = useTranslations("BankAccounts");
  const [properties, setProperties] = useState<PropertySummary[]>([]);
  const [accounts, setAccounts] = useState<BankAccountOption[] | null>(null);
  const [propertyId, setPropertyId] = useState("");
  const [legalEntityId, setLegalEntityId] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    bff<{ items: PropertySummary[] }>("/api/bff/properties?page_size=200").then((r) => {
      if (r.ok) setProperties(r.data.items);
    });
  }, []);

  useEffect(() => {
    let cancelled = false;
    setAccounts(null);
    bff<BankAccountOption[]>(accountsUrl({ propertyId: propertyId || null, legalEntityId: legalEntityId || null })).then((r) => {
      if (cancelled) return;
      if (r.ok) setAccounts(r.data);
      else {
        setAccounts([]);
        setError(r.message);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [propertyId, legalEntityId]);

  const legalEntities = useMemo(() => {
    const seen = new Map<string, string>();
    for (const a of accounts ?? []) if (a.legal_entity_name) seen.set(a.legal_entity_id, a.legal_entity_name);
    return [...seen.entries()].sort((x, y) => x[1].localeCompare(y[1], "de"));
  }, [accounts]);

  const selected = accounts?.find((a) => a.id === selectedId) ?? null;

  return (
    <section className={ui.card} data-testid="bank-account-overview">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className="mt-1 text-sm text-muted">{t("intro")}</p>
      {error ? (
        <p role="alert" className={`${ui.alert} mt-2`}>
          {error}
        </p>
      ) : null}
      <div className="mt-3 grid gap-3 md:grid-cols-3">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("property")}</span>
          <select
            className={ui.input}
            value={propertyId}
            onChange={(e) => {
              setPropertyId(e.target.value);
              setSelectedId(null);
            }}
          >
            <option value="">{t("allProperties")}</option>
            {properties.map((p) => (
              <option key={p.id} value={p.id}>
                {p.number} {p.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("legalEntity")}</span>
          <select
            className={ui.input}
            value={legalEntityId}
            onChange={(e) => {
              setLegalEntityId(e.target.value);
              setSelectedId(null);
            }}
          >
            <option value="">{t("allLegalEntities")}</option>
            {legalEntities.map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <BankAccountSelect label={t("select")} options={accounts ?? undefined} value={selectedId} onChange={(a) => setSelectedId(a?.id ?? null)} />
      </div>
      {selected ? (
        <div className="mt-3">
          <BankAccountCard account={selected} />
        </div>
      ) : null}
    </section>
  );
}

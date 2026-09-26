"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useTranslations } from "next-intl";

import { bff } from "@/lib/bff";
import { formatDate, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

import { accountLabel, accountMatches, accountsUrl, propertyAccountsUrl, type BankAccountOption } from "./bankAccountTypes";

type Props = {
  /** Selected account id (controlled). */
  value: string | null;
  onChange: (account: BankAccountOption | null) => void;
  /** Explicit options; when omitted the component loads them itself. */
  options?: BankAccountOption[];
  /** Restrict the loaded list to accounts selectable for this property. */
  propertyId?: string | null;
  /** Restrict the loaded list to accounts of this legal entity. */
  legalEntityId?: string | null;
  label?: string;
  placeholder?: string;
  disabled?: boolean;
  showBalance?: boolean;
  id?: string;
};

/** Wiederverwendbare Bankkontenauswahl: Dropdown mit Suche über Inhaber, Bank, IBAN-Ende,
 *  Objekt und Rechtsträger. Zeigt Kontoart, Standardmarkierungen und optional den Kontostand.
 *  Nur lesend; die Auswahl selbst löst keinen Zahlungsverkehr aus. */
export function BankAccountSelect({
  value,
  onChange,
  options,
  propertyId,
  legalEntityId,
  label,
  placeholder,
  disabled,
  showBalance = true,
  id,
}: Props) {
  const t = useTranslations("BankAccounts");
  const generatedId = useId();
  const inputId = id ?? `bank-account-select-${generatedId}`;
  const listId = `${inputId}-listbox`;
  const [loaded, setLoaded] = useState<BankAccountOption[] | null>(options ?? null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (options) {
      setLoaded(options);
      return;
    }
    let cancelled = false;
    setLoaded(null);
    setLoadError(null);
    const url = propertyId ? propertyAccountsUrl(propertyId, legalEntityId) : accountsUrl({ legalEntityId });
    bff<BankAccountOption[]>(url).then((result) => {
      if (cancelled) return;
      if (result.ok) setLoaded(result.data);
      else {
        setLoaded([]);
        setLoadError(result.message);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [options, propertyId, legalEntityId]);

  useEffect(() => {
    function onClick(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const all = useMemo(() => loaded ?? [], [loaded]);
  const selected = useMemo(() => all.find((a) => a.id === value) ?? null, [all, value]);
  const filtered = useMemo(() => all.filter((a) => accountMatches(a, query)), [all, query]);

  useEffect(() => {
    setActive(0);
  }, [query, open]);

  function choose(account: BankAccountOption | null) {
    onChange(account);
    setQuery("");
    setOpen(false);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(i + 1, Math.max(filtered.length - 1, 0)));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (event.key === "Enter") {
      if (open && filtered[active]) {
        event.preventDefault();
        choose(filtered[active]);
      }
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  const displayValue = open || query ? query : selected ? accountLabel(selected) : "";

  return (
    <div ref={rootRef} className="relative flex flex-col gap-1">
      {label ? (
        <label htmlFor={inputId} className={ui.label}>
          {label}
        </label>
      ) : null}
      <div className="flex gap-1">
        <input
          id={inputId}
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={open && filtered[active] ? `${listId}-${filtered[active].id}` : undefined}
          className={ui.input}
          placeholder={placeholder ?? t("searchPlaceholder")}
          value={displayValue}
          disabled={disabled}
          onFocus={() => setOpen(true)}
          onClick={() => setOpen(true)}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onKeyDown={onKeyDown}
        />
        {selected && !disabled ? (
          <button type="button" className={ui.buttonSm} onClick={() => choose(null)} aria-label={t("clear")}>
            ×
          </button>
        ) : null}
      </div>
      {open ? (
        <ul
          id={listId}
          role="listbox"
          className="absolute top-full z-20 mt-1 max-h-72 w-full overflow-auto rounded-md border border-border bg-bg p-1 shadow-card"
        >
          {loaded === null ? (
            <li className="px-2 py-1 text-sm text-muted">{t("loading")}</li>
          ) : loadError ? (
            <li className="px-2 py-1 text-sm text-danger-fg">{loadError}</li>
          ) : all.length === 0 ? (
            <li className="px-2 py-1 text-sm text-muted">{t("noAccounts")}</li>
          ) : filtered.length === 0 ? (
            <li className="px-2 py-1 text-sm text-muted">{t("noResults")}</li>
          ) : (
            filtered.map((a, index) => (
              <li
                key={a.id}
                id={`${listId}-${a.id}`}
                role="option"
                aria-selected={a.id === value}
                className={`cursor-pointer rounded px-2 py-1.5 text-sm ${index === active ? "bg-surface" : ""} ${a.id === value ? "font-medium" : ""}`}
                onMouseEnter={() => setActive(index)}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => choose(a)}
              >
                <div className="flex flex-wrap items-baseline justify-between gap-x-2">
                  <span>{accountLabel(a)}</span>
                  {showBalance ? (
                    <span className="tabular-nums text-muted">{a.balance !== null ? formatEur(a.balance) : t("balanceUnknown")}</span>
                  ) : null}
                </div>
                <div className="mt-0.5 flex flex-wrap gap-1 text-xs text-muted">
                  <span>{t(`kind.${a.kind}`)}</span>
                  <span>{t(`source.${a.source}`)}</span>
                  {a.property_number ? <span>{t("homeProperty")}: {a.property_number}</span> : null}
                  {a.legal_entity_name ? <span>{a.legal_entity_name}</span> : null}
                  {a.default_for_legal_entity ? <span className={ui.badgeGold}>{t("defaultLegalEntity")}</span> : null}
                  {a.assignments
                    .filter((x) => x.is_default)
                    .map((x) => (
                      <span key={x.property_id} className={ui.badgeGold}>
                        {t("defaultProperty", { purpose: t(`purpose.${x.purpose}`) })}
                        {x.property_number ? ` (${x.property_number})` : ""}
                      </span>
                    ))}
                  {showBalance && a.balance_as_of ? <span>{t("asOf", { date: formatDate(a.balance_as_of) })}</span> : null}
                </div>
              </li>
            ))
          )}
        </ul>
      ) : null}
    </div>
  );
}

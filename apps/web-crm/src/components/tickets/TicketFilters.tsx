"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";

import { STATUSES, PRIORITIES } from "@/components/tickets/TicketForms";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Member = { user_id: string; display_name: string };
type PropertyOption = { id: string; number: string; name: string };
type UnitOption = { id: string; number: string; label: string | null };
type ContactOption = { id: string; display_name: string };

const ROLES = ["owner", "tenant"] as const;

/** Query keys this filter bar owns in the URL, kept in sync so filters are shareable and
 * survive reloads (operator 25.09.2026, Tickets Suche und Filter). Additive to the API's
 * GET /tickets params; `q` is debounced client side before it reaches the URL. */
const KEYS = [
  "q",
  "assignee_user_id",
  "property_id",
  "unit_id",
  "contact_id",
  "contact_role",
  "status",
  "priority",
  "category",
  "team_id",
  "created_from",
  "created_to",
  "mine",
] as const;

export type TicketFilterValues = Record<(typeof KEYS)[number], string>;

const EMPTY: TicketFilterValues = KEYS.reduce((acc, key) => ({ ...acc, [key]: "" }), {} as TicketFilterValues);

function readFromParams(params: URLSearchParams): TicketFilterValues {
  const out = { ...EMPTY };
  for (const key of KEYS) out[key] = params.get(key) ?? "";
  return out;
}

export function TicketFilters({ meUserId }: { meUserId: string | null }) {
  const t = useTranslations("Tickets");
  const router = useRouter();
  const searchParams = useSearchParams();
  const [values, setValues] = useState<TicketFilterValues>(() => readFromParams(searchParams));
  const [qInput, setQInput] = useState(values.q);
  const [members, setMembers] = useState<Member[]>([]);
  const [properties, setProperties] = useState<PropertyOption[]>([]);
  const [units, setUnits] = useState<UnitOption[]>([]);
  const [contactQuery, setContactQuery] = useState("");
  const [contactResults, setContactResults] = useState<ContactOption[]>([]);
  const [contactLabel, setContactLabel] = useState("");
  const [expanded, setExpanded] = useState(false);
  // Operator 26.09.2026: done, closed and rejected tickets are hidden unless erledigt=1.
  const showClosed = searchParams.get("erledigt") === "1";

  useEffect(() => {
    setValues(readFromParams(searchParams));
    setQInput(searchParams.get("q") ?? "");
  }, [searchParams]);

  useEffect(() => {
    void bff<Member[]>("/api/bff/tenant/members").then((res) => {
      if (res.ok) setMembers(res.data);
    });
    void bff<{ items: PropertyOption[] }>("/api/bff/properties?page_size=200").then((res) => {
      if (res.ok) setProperties(res.data.items ?? []);
    });
  }, []);

  useEffect(() => {
    if (!values.property_id) {
      setUnits([]);
      return;
    }
    void bff<UnitOption[]>(`/api/bff/properties/${values.property_id}/units`).then((res) => {
      if (res.ok) setUnits(res.data);
    });
  }, [values.property_id]);

  useEffect(() => {
    const term = contactQuery.trim();
    if (term.length < 2) {
      setContactResults([]);
      return;
    }
    const handle = setTimeout(() => {
      void bff<{ items: ContactOption[] }>(`/api/bff/contacts?q=${encodeURIComponent(term)}&page_size=10`).then((res) => {
        if (res.ok) setContactResults(res.data.items ?? []);
      });
    }, 300);
    return () => clearTimeout(handle);
  }, [contactQuery]);

  // Debounce the free text search before it changes the URL (operator: search field debounced).
  useEffect(() => {
    const handle = setTimeout(() => {
      if (qInput !== values.q) apply({ ...values, q: qInput });
    }, 350);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qInput]);

  function apply(next: TicketFilterValues) {
    setValues(next);
    const params = new URLSearchParams();
    for (const key of KEYS) {
      if (next[key]) params.set(key, next[key]);
    }
    // Toggles owned by the page stay as they are when a filter changes.
    for (const key of ["erledigt", "merged"]) {
      const value = searchParams.get(key);
      if (value) params.set(key, value);
    }
    router.push(`/tickets${params.toString() ? `?${params.toString()}` : ""}`);
  }

  function set(key: (typeof KEYS)[number], value: string) {
    apply({ ...values, [key]: value });
  }

  function reset() {
    setQInput("");
    setContactLabel("");
    setContactQuery("");
    router.push("/tickets");
  }

  function toggleClosed() {
    const params = new URLSearchParams(searchParams.toString());
    params.delete("page");
    if (showClosed) params.delete("erledigt");
    else params.set("erledigt", "1");
    router.push(`/tickets${params.toString() ? `?${params.toString()}` : ""}`);
  }

  function toggleMine() {
    if (values.mine === "1") {
      set("mine", "");
    } else {
      apply({ ...values, mine: "1", assignee_user_id: meUserId ?? "" });
    }
  }

  const activeCount = useMemo(() => KEYS.filter((key) => values[key]).length, [values]);

  return (
    <div className={`${ui.card} flex flex-col gap-3`} data-testid="ticket-filters">
      <div className="flex items-center justify-between gap-2">
        <label className="flex-1">
          <span className="sr-only">{t("filters.search")}</span>
          <input
            className={ui.input}
            placeholder={t("filters.searchPlaceholder")}
            value={qInput}
            onChange={(e) => setQInput(e.target.value)}
            data-testid="filter-q"
          />
        </label>
        <button
          type="button"
          className={`${ui.buttonSm} sm:hidden`}
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          data-testid="filters-toggle"
        >
          {t("filters.more")} {activeCount > 0 ? `(${activeCount})` : ""}
        </button>
      </div>
      <div className={`${expanded ? "flex" : "hidden"} flex-col gap-3 sm:flex`}>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            role="checkbox"
            aria-checked={values.mine === "1"}
            className={values.mine === "1" ? ui.primary : ui.button}
            onClick={toggleMine}
            data-testid="filter-mine"
          >
            {t("filters.mine")}
          </button>
          <button
            type="button"
            role="checkbox"
            aria-checked={showClosed}
            className={showClosed ? ui.primary : ui.button}
            onClick={toggleClosed}
            data-testid="filter-closed"
          >
            {t("filters.showClosed")}
          </button>
          <select className={ui.input} value={values.assignee_user_id} onChange={(e) => set("assignee_user_id", e.target.value)} data-testid="filter-assignee">
            <option value="">{t("filters.assigneeAll")}</option>
            {members.map((m) => (
              <option key={m.user_id} value={m.user_id}>
                {m.display_name}
              </option>
            ))}
          </select>
          <select className={ui.input} value={values.property_id} onChange={(e) => apply({ ...values, property_id: e.target.value, unit_id: "" })} data-testid="filter-property">
            <option value="">{t("filters.propertyAll")}</option>
            {properties.map((p) => (
              <option key={p.id} value={p.id}>
                {p.number} {p.name}
              </option>
            ))}
          </select>
          <select className={ui.input} value={values.unit_id} onChange={(e) => set("unit_id", e.target.value)} disabled={!values.property_id} data-testid="filter-unit">
            <option value="">{t("filters.unitAll")}</option>
            {units.map((u) => (
              <option key={u.id} value={u.id}>
                {u.label ?? u.number}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-wrap gap-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("filters.contact")}</span>
            <input
              className={ui.input}
              placeholder={t("filters.contactPlaceholder")}
              value={contactLabel || contactQuery}
              onChange={(e) => {
                setContactQuery(e.target.value);
                setContactLabel("");
                if (!e.target.value) set("contact_id", "");
              }}
              data-testid="filter-contact"
            />
            {contactResults.length > 0 && !contactLabel ? (
              <ul className="max-h-48 overflow-auto rounded-md border border-border bg-bg text-sm shadow-card" role="listbox">
                {contactResults.map((c) => (
                  <li key={c.id}>
                    <button
                      type="button"
                      className="block w-full px-3 py-1.5 text-left hover:bg-surface"
                      onClick={() => {
                        setContactLabel(c.display_name);
                        setContactQuery("");
                        setContactResults([]);
                        set("contact_id", c.id);
                      }}
                    >
                      {c.display_name}
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </label>
          <select className={ui.input} value={values.contact_role} onChange={(e) => set("contact_role", e.target.value)} data-testid="filter-role">
            <option value="">{t("filters.roleAll")}</option>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {t(`filters.role.${r}`)}
              </option>
            ))}
          </select>
          <select className={ui.input} value={values.status} onChange={(e) => set("status", e.target.value)} data-testid="filter-status">
            <option value="">{t("filters.statusAll")}</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`statuses.${s}`)}
              </option>
            ))}
          </select>
          <select className={ui.input} value={values.priority} onChange={(e) => set("priority", e.target.value)} data-testid="filter-priority">
            <option value="">{t("filters.priorityAll")}</option>
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {t(`priorities.${p}`)}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("filters.category")}</span>
            <input className={ui.input} value={values.category} onChange={(e) => set("category", e.target.value)} data-testid="filter-category" />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("filters.createdFrom")}</span>
            <input type="date" className={ui.input} value={values.created_from.slice(0, 10)} onChange={(e) => set("created_from", e.target.value ? `${e.target.value}T00:00:00Z` : "")} data-testid="filter-created-from" />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("filters.createdTo")}</span>
            <input type="date" className={ui.input} value={values.created_to.slice(0, 10)} onChange={(e) => set("created_to", e.target.value ? `${e.target.value}T23:59:59Z` : "")} data-testid="filter-created-to" />
          </label>
          <button type="button" className={ui.button} onClick={reset} data-testid="filter-reset">
            {t("filters.reset")}
          </button>
        </div>
      </div>
    </div>
  );
}

"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type PickedProperty = { id: string; number: string; name: string };
type BuildingOption = { id: string; name: string };

/** Property search for the ticket form (M19-04): type at least two characters, pick one result.
 *  Nothing is loaded before the first search; the choice is reported to the parent. */
export function PropertyPicker({ onPick }: { onPick: (property: PickedProperty) => void }) {
  const t = useTranslations("TicketLocation");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PickedProperty[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function search() {
    const q = query.trim();
    if (q.length < 2) return;
    setBusy(true);
    setError(null);
    const res = await bff<{ items: PickedProperty[] }>(`/api/bff/properties?${new URLSearchParams({ q, page_size: "10" }).toString()}`);
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setResults((res.data?.items ?? []).map((p) => ({ id: p.id, number: p.number, name: p.name })));
  }

  return (
    <div className="flex flex-col gap-1">
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("propertySearch")}</span>
        <input
          className={ui.input}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void search();
            }
          }}
        />
      </label>
      <button type="button" className={`${ui.buttonSm} self-start`} disabled={busy || query.trim().length < 2} onClick={() => void search()}>
        {t("search")}
      </button>
      {error ? (
        <p role="alert" className={ui.error}>
          {error}
        </p>
      ) : null}
      {results.length > 0 ? (
        <ul className="flex flex-wrap gap-1">
          {results.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                className={ui.buttonSm}
                onClick={() => {
                  onPick(p);
                  setResults([]);
                  setQuery("");
                }}
              >
                {p.number} {p.name}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** Building select of a property (M19-04, ticket.building_id): loads the buildings of the
 *  property and offers "no building". The API refuses a building of another property. */
export function BuildingSelect({
  propertyId,
  value,
  onChange,
  disabled = false,
}: {
  propertyId: string;
  value: string;
  onChange: (buildingId: string) => void;
  disabled?: boolean;
}) {
  const t = useTranslations("TicketLocation");
  const [buildings, setBuildings] = useState<BuildingOption[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    void bff<BuildingOption[]>(`/api/bff/properties/${propertyId}/buildings`).then((res) => {
      if (!cancelled) setBuildings(res.ok && Array.isArray(res.data) ? res.data.map((b) => ({ id: b.id, name: b.name })) : []);
    });
    return () => {
      cancelled = true;
    };
  }, [propertyId]);

  return (
    <label className="flex flex-col gap-1">
      <span className={ui.label}>{t("building")}</span>
      <select className={ui.input} value={value} disabled={disabled || buildings === null} onChange={(e) => onChange(e.target.value)}>
        <option value="">{buildings === null ? t("loading") : t("noBuilding")}</option>
        {(buildings ?? []).map((b) => (
          <option key={b.id} value={b.id}>
            {b.name}
          </option>
        ))}
      </select>
    </label>
  );
}

"use client";
/** Kontaktsuche für die Stammdatenabschnitte der Objektseite (C2): Name tippen, Treffer
 *  wählen. Sucht ab zwei Zeichen über GET /contacts?q=. Wird von Ansprechpartnern und
 *  Eigentümerdetails gemeinsam genutzt. */
import { useTranslations } from "next-intl";
import { useId, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type ContactHit = { id: string; display_name: string };

export function ContactPicker({
  label,
  value,
  onChange,
  testId,
}: {
  label: string;
  value: ContactHit | null;
  onChange: (hit: ContactHit | null) => void;
  testId?: string;
}) {
  const t = useTranslations("Properties.contactPersons");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<ContactHit[]>([]);
  const listId = useId();

  const search = async (q: string) => {
    setQuery(q);
    onChange(null);
    if (q.trim().length < 2) {
      setHits([]);
      return;
    }
    const res = await bff<{ items: ContactHit[] }>(`/api/bff/contacts?q=${encodeURIComponent(q.trim())}&page_size=8`);
    setHits(res.ok ? res.data.items : []);
  };

  return (
    <div className="flex flex-col gap-1">
      <label className={ui.label}>
        {label}
        <input
          className={ui.input}
          value={value ? value.display_name : query}
          onChange={(e) => void search(e.target.value)}
          placeholder={t("searchPlaceholder")}
          aria-controls={listId}
          data-testid={testId}
        />
      </label>
      {value === null && hits.length > 0 ? (
        <ul id={listId} className="flex flex-col gap-1 text-sm" data-testid={testId ? `${testId}-hits` : undefined}>
          {hits.map((h) => (
            <li key={h.id}>
              <button
                type="button"
                className="hover:underline"
                onClick={() => {
                  onChange(h);
                  setHits([]);
                }}
              >
                {h.display_name}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/** Aktive Einträge eines Katalogs für Auswahlfelder; ein Fehler ergibt eine leere Liste. */
export async function loadCatalogOptions(catalog: string): Promise<{ code: string; label: string }[]> {
  const res = await bff<{ code: string; label: string; active: boolean }[]>(
    `/api/bff/catalogs/${encodeURIComponent(catalog)}?include_inactive=true`,
  );
  return res.ok ? res.data.filter((e) => e.active).map((e) => ({ code: e.code, label: e.label })) : [];
}

export function todayIso(): string {
  return new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Berlin" }).format(new Date());
}

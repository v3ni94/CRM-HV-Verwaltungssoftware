"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type PickedContact = { id: string; display_name: string };

/** Small contact search (name only, data minimisation) for the audit forms: type, search,
 *  pick. Selection is reported to the parent; nothing is written. */
export function ContactPicker({
  label,
  onPick,
  kind,
}: {
  label: string;
  onPick: (contact: PickedContact) => void;
  kind?: "person" | "company";
}) {
  const t = useTranslations("HoaWork");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<PickedContact[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function search() {
    const q = query.trim();
    if (q.length < 2) return;
    setBusy(true);
    setError(null);
    const params = new URLSearchParams({ q, page_size: "10" });
    if (kind) params.set("kind", kind);
    const res = await bff<{ items: PickedContact[] }>(`/api/bff/contacts?${params.toString()}`);
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setResults(res.data.items.map((c) => ({ id: c.id, display_name: c.display_name })));
  }

  return (
    <div className="flex flex-col gap-1">
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{label}</span>
        <span className="flex gap-2">
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
          <button type="button" className={ui.buttonSm} disabled={busy || query.trim().length < 2} onClick={() => void search()}>
            {t("audit.search")}
          </button>
        </span>
      </label>
      {error ? (
        <p role="alert" className={ui.error}>
          {error}
        </p>
      ) : null}
      {results.length > 0 ? (
        <ul className="flex flex-wrap gap-1">
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

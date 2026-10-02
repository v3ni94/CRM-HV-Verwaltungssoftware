"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { HANDBOOK, searchHandbook } from "@/lib/handbook";

/** Chapter list with full text search over the handbook (client side, no request). */
export function HelpSearch({ placeholder, empty }: { placeholder: string; empty: string }) {
  const [q, setQ] = useState("");
  const hits = useMemo(() => searchHandbook(q), [q]);
  return (
    <div className="space-y-4">
      <input
        type="search"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        className="w-full rounded border border-border-soft bg-surface px-3 py-2 text-sm"
      />
      {q.trim().length > 1 ? (
        hits.length === 0 ? (
          <p className="text-sm text-muted">{empty}</p>
        ) : (
          <ul className="space-y-3">
            {hits.map((h, i) => (
              <li key={i} className="text-sm">
                <Link href={`/hilfe/${h.slug}${h.anchor ? `#${h.anchor}` : ""}`} className="font-medium underline">
                  {h.title}
                  {h.heading && h.heading !== h.title ? ` · ${h.heading}` : ""}
                </Link>
                <p className="text-xs text-muted">{h.excerpt}</p>
              </li>
            ))}
          </ul>
        )
      ) : (
        <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {HANDBOOK.filter((c) => c.slug !== "README").map((c) => (
            <li key={c.slug}>
              <Link href={`/hilfe/${c.slug}`} className="block rounded border border-border-soft p-3 text-sm hover:bg-surface-muted">
                {c.title}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { searchSettingsIndex } from "@/lib/settings-index";
import { ui } from "@/lib/ui";

/**
 * Search box on top of the settings hub (operator request 27.09.2026: "Ergänze eine Suche bei
 * Einstellungen, um schneller ans Ziel zu kommen ... Die Suche geht bis in die nächste und
 * übernächste Ebene"). Matches instantly while typing against the static
 * `src/lib/settings-index.ts`, case and umlaut insensitive, and only ever shows entries the
 * signed in user could also reach as a card (same `permissions` the hub page itself uses).
 */
export function SettingsSearch({ permissions }: { permissions: readonly string[] }) {
  const t = useTranslations("SettingsSearch");
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);

  useEffect(() => {
    // Autofocus only on desktop (rule: a touch keyboard covering the hub on a phone is worse
    // than a search box the visitor has to tap first); `lg` matches the hub's own card grid
    // breakpoint.
    try {
      if (window.matchMedia("(min-width: 1024px)").matches) inputRef.current?.focus();
    } catch {
      /* matchMedia unavailable (e.g. some test environments): no autofocus, no crash */
    }
  }, []);

  const hits = useMemo(() => searchSettingsIndex(query, permissions), [query, permissions]);

  useEffect(() => setActive(0), [query]);

  function go(index: number) {
    const hit = hits[index];
    if (!hit) return;
    setQuery("");
    router.push(hit.entry.href);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      setQuery("");
    } else if (event.key === "ArrowDown") {
      if (hits.length === 0) return;
      event.preventDefault();
      setActive((i) => Math.min(i + 1, hits.length - 1));
    } else if (event.key === "ArrowUp") {
      if (hits.length === 0) return;
      event.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (event.key === "Enter") {
      if (hits.length === 0) return;
      event.preventDefault();
      go(active);
    }
  }

  const showResults = query.trim().length > 0;
  const activeId = showResults && hits[active] ? `settings-search-${hits[active]!.entry.id}` : undefined;

  return (
    <div className="relative">
      <input
        ref={inputRef}
        type="search"
        role="combobox"
        aria-expanded={showResults}
        aria-controls="settings-search-results"
        aria-activedescendant={activeId}
        aria-label={t("placeholder")}
        placeholder={t("placeholder")}
        className={ui.input}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={onKeyDown}
      />
      {showResults ? (
        <div
          id="settings-search-results"
          role="listbox"
          aria-label={t("resultsLabel")}
          className={`${ui.card} absolute z-10 mt-1 max-h-96 w-full overflow-auto p-1`}
        >
          {hits.length === 0 ? (
            <p className="px-3 py-2 text-sm text-muted">{t("noResults")}</p>
          ) : (
            hits.map(({ entry }, index) => (
              <div
                key={entry.id}
                id={`settings-search-${entry.id}`}
                data-testid={`settings-search-option-${entry.id}`}
                role="option"
                aria-selected={index === active}
                className={`cursor-pointer rounded-md px-3 py-2 ${index === active ? "bg-surface-2" : ""}`}
                onMouseEnter={() => setActive(index)}
                onClick={() => go(index)}
              >
                <p className="text-sm font-medium text-fg">{entry.title}</p>
                <p className="text-xs text-muted">{entry.breadcrumb.join(" › ")}</p>
              </div>
            ))
          )}
        </div>
      ) : null}
    </div>
  );
}

"use client";

import type { components } from "@mhvp/api-client";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Hit = components["schemas"]["Hit"];

function hrefOf(hit: Hit): string | null {
  return hit.entity_type === "contact" ? `/kontakte/${hit.id}` : null;
}

/** Global search over all areas (M9), opened with Strg+K (Cmd+K on macOS), via the BFF. */
export function SearchDialog() {
  const t = useTranslations("Shell");
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [active, setActive] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const opener = useRef<HTMLElement | null>(null);

  const close = useCallback(() => {
    setOpen(false);
    opener.current?.focus();
  }, []);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        opener.current = document.activeElement as HTMLElement | null;
        setOpen(true);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const q = query.trim();
    if (q.length < 2) {
      setHits([]);
      setError(null);
      return;
    }
    const handle = setTimeout(() => {
      void bff<Hit[]>(`/api/bff/workspace/search?q=${encodeURIComponent(q)}&limit=6`).then((result) => {
        if (result.ok) {
          setHits(result.data);
          setActive(0);
          setError(null);
        } else {
          setError(t("searchError"));
        }
      });
    }, 200);
    return () => clearTimeout(handle);
  }, [query, open, t]);

  function go(hit: Hit | undefined) {
    const href = hit && hrefOf(hit);
    if (!href) return;
    setOpen(false);
    setQuery("");
    router.push(href);
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((i) => Math.min(i + 1, Math.max(hits.length - 1, 0)));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      go(hits[active]);
    }
  }

  return (
    <>
      <button
        type="button"
        className={`${ui.button} min-w-48 justify-between text-muted`}
        onClick={(e) => {
          opener.current = e.currentTarget;
          setOpen(true);
        }}
        aria-keyshortcuts="Control+K Meta+K"
      >
        <span>{t("search")}</span>
        <kbd className="rounded border border-border px-1 text-xs">{t("searchShortcut")}</kbd>
      </button>
      {open ? (
        <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 pt-24" onMouseDown={close}>
          <div
            role="dialog"
            aria-modal="true"
            aria-label={t("searchTitle")}
            className="w-full max-w-xl rounded border border-border bg-bg shadow-lg"
            onMouseDown={(e) => e.stopPropagation()}
            onKeyDown={onKeyDown}
          >
            <input
              ref={inputRef}
              type="search"
              role="combobox"
              aria-expanded={hits.length > 0}
              aria-controls="search-results"
              aria-activedescendant={hits[active] ? `hit-${hits[active].id}` : undefined}
              aria-label={t("searchPlaceholder")}
              placeholder={t("searchPlaceholder")}
              className="w-full border-b border-border bg-transparent px-4 py-3 text-base focus:outline-none"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <ul id="search-results" role="listbox" className="max-h-80 overflow-auto py-1">
              {hits.map((hit, index) => (
                <li
                  key={`${hit.entity_type}-${hit.id}`}
                  id={`hit-${hit.id}`}
                  role="option"
                  aria-selected={index === active}
                  className={`cursor-pointer px-4 py-2 text-sm ${index === active ? "bg-surface" : ""}`}
                  onMouseEnter={() => setActive(index)}
                  onClick={() => go(hit)}
                >
                  <span className="mr-2 text-xs text-muted">{t(`entity.${hit.entity_type}`)}</span>
                  <span className="font-medium">{hit.title}</span>
                  {hit.subtitle ? <span className="ml-2 text-muted">{hit.subtitle}</span> : null}
                </li>
              ))}
            </ul>
            <p className="px-4 py-2 text-xs text-muted" role="status">
              {error ?? (query.trim().length < 2 ? t("searchMin") : hits.length === 0 ? t("searchEmpty") : "")}
            </p>
          </div>
        </div>
      ) : null}
    </>
  );
}

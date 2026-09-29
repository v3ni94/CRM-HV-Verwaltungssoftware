"use client";

import type { components } from "@mhvp/api-client";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { bff } from "@/lib/bff";
import { entityHref } from "@/lib/entity-links";
import { ui } from "@/lib/ui";

import { allowedActions } from "./palette-actions";

type Hit = components["schemas"]["Hit"];

export type PaletteNavItem = { href: string; label: string };
export type PaletteNavGroup = { label: string; items: PaletteNavItem[] };

type Item =
  | { kind: "action"; id: string; label: string; href: string; keywords: string[] }
  | { kind: "nav"; id: string; label: string; group: string; href: string }
  | { kind: "recent"; id: string; label: string; subtitle?: string | null; type: string; href: string }
  | { kind: "hit"; id: string; label: string; subtitle?: string | null; type: string; href: string };

type RecentEntry = { type: string; id: string; title: string; subtitle?: string | null; href: string };

const RECENT_MAX = 8;

function recentKey(userKey: string): string {
  return `mhvp.palette.recent.${userKey || "anon"}`;
}

function readRecent(userKey: string): RecentEntry[] {
  try {
    const raw = window.localStorage.getItem(recentKey(userKey));
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? (parsed as RecentEntry[]).filter((e) => e && typeof e.href === "string") : [];
  } catch {
    return [];
  }
}

function pushRecent(userKey: string, entry: RecentEntry) {
  try {
    const next = [entry, ...readRecent(userKey).filter((e) => e.href !== entry.href)].slice(0, RECENT_MAX);
    window.localStorage.setItem(recentKey(userKey), JSON.stringify(next));
  } catch {
    /* storage unavailable: recent items are a convenience only */
  }
}

function matches(query: string, ...texts: (string | undefined | null)[]): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return texts.some((t) => (t ?? "").toLowerCase().includes(q));
}

/**
 * Command palette (operator decision 27.09.2026, design proposal 1): one input, opened with
 * Strg+K or Cmd+K or the header button, that searches records via `GET /workspace/search`
 * and offers actions and every navigation entry filtered by permissions. Recent records are
 * kept per user in localStorage. Dialog role, focus trap, Escape closes.
 */
export function CommandPalette({
  nav,
  permissions,
  userKey,
}: {
  nav: PaletteNavGroup[];
  permissions: readonly string[];
  userKey: string;
}) {
  const t = useTranslations("Shell");
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [recent, setRecent] = useState<RecentEntry[]>([]);
  const [active, setActive] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const opener = useRef<HTMLElement | null>(null);

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    opener.current?.focus();
  }, []);

  const show = useCallback(
    (from: HTMLElement | null) => {
      opener.current = from;
      setRecent(readRecent(userKey));
      setOpen(true);
    },
    [userKey],
  );

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        show(document.activeElement as HTMLElement | null);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [show]);

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
      void bff<Hit[]>(`/api/bff/workspace/search?q=${encodeURIComponent(q)}&limit=8`).then((result) => {
        if (result.ok) {
          setHits(result.data);
          setError(null);
        } else {
          setError(t("searchError"));
        }
      });
    }, 200);
    return () => clearTimeout(handle);
  }, [query, open, t]);

  const items = useMemo<Item[]>(() => {
    const q = query.trim();
    const list: Item[] = [];
    if (!q) {
      for (const r of recent) list.push({ kind: "recent", id: `recent-${r.href}`, label: r.title, subtitle: r.subtitle, type: r.type, href: r.href });
    }
    for (const a of allowedActions(permissions)) {
      const label = t(`action.${a.labelKey}`);
      if (matches(q, label, ...(a.keywords ?? []))) list.push({ kind: "action", id: `action-${a.id}`, label, href: a.href, keywords: a.keywords ?? [] });
    }
    if (q) {
      for (const g of nav) {
        for (const n of g.items) {
          if (matches(q, n.label, g.label)) list.push({ kind: "nav", id: `nav-${n.href}`, label: n.label, group: g.label, href: n.href });
        }
      }
      for (const h of hits) {
        const href = entityHref(h.entity_type, h.id, h.parent_id);
        if (href) list.push({ kind: "hit", id: `hit-${h.entity_type}-${h.id}`, label: h.title, subtitle: h.subtitle, type: h.entity_type, href });
      }
    }
    return list;
  }, [query, recent, permissions, nav, hits, t]);

  useEffect(() => setActive(0), [query, hits]);

  function run(item: Item | undefined) {
    if (!item) return;
    if (item.kind === "hit") {
      pushRecent(userKey, { type: item.type, id: item.id, title: item.label, subtitle: item.subtitle, href: item.href });
    }
    setOpen(false);
    setQuery("");
    router.push(item.href);
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((i) => Math.min(i + 1, Math.max(items.length - 1, 0)));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      run(items[active]);
    } else if (event.key === "Tab") {
      const focusable = dialogRef.current?.querySelectorAll<HTMLElement>("input, button, [tabindex='0']");
      if (!focusable || focusable.length === 0) return;
      const first = focusable[0]!;
      const last = focusable[focusable.length - 1]!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  }

  const sections: { key: string; title: string; entries: { item: Item; index: number }[] }[] = [];
  items.forEach((item, index) => {
    const key = item.kind;
    let section = sections.find((s) => s.key === key);
    if (!section) {
      section = { key, title: t(`palette.${key}`), entries: [] };
      sections.push(section);
    }
    section.entries.push({ item, index });
  });
  const activeId = items[active]?.id;
  const q = query.trim();
  const status = error ?? (q.length === 0 && items.length === 0 ? t("palette.hint") : q.length > 0 && q.length < 2 ? t("searchMin") : items.length === 0 ? t("searchEmpty") : "");

  return (
    <>
      {/* Round 44 px icon below sm, the labelled pill from sm (44 px on touch, may shrink so
          the one row header never overflows a 768 px tablet), 14 rem wide from md, shortcut
          hint from lg (M31). */}
      <button
        type="button"
        className="inline-flex h-11 min-h-11 w-11 shrink-0 items-center justify-center gap-2 rounded-full border border-border bg-surface text-sm text-muted shadow-xs transition duration-150 hover:border-accent hover:text-fg focus:outline-none focus:ring-2 focus:ring-focus sm:h-auto sm:w-auto sm:min-w-0 sm:shrink sm:justify-between sm:px-3.5 sm:py-2 sm:pointer-fine:min-h-0 md:min-w-56"
        onClick={(e) => show(e.currentTarget)}
        aria-keyshortcuts="Control+K Meta+K"
        aria-label={t("palette.open")}
      >
        <span className="flex items-center gap-2">
          <svg aria-hidden="true" viewBox="0 0 20 20" className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="8.5" cy="8.5" r="5" />
            <path d="m16 16-3.2-3.2" strokeLinecap="round" />
          </svg>
          <span className="hidden whitespace-nowrap sm:flex" data-testid="palette-label">
            {t("search")}
          </span>
        </span>
        <kbd className="hidden rounded border border-border bg-surface-2 px-1.5 py-0.5 text-xs text-subtle lg:inline">{t("searchShortcut")}</kbd>
      </button>
      {open ? (
        <div className="fixed inset-0 z-50 flex items-start justify-center bg-scrim p-0 sm:p-4 sm:pt-24" onMouseDown={close}>
          {/* Full screen below sm: input pinned at the top, results fill the rest, a close
              button for touch; the centred card from sm as before. */}
          <div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-label={t("palette.title")}
            className="flex h-dvh w-full max-w-xl flex-col overflow-hidden bg-raised pt-[env(safe-area-inset-top)] sm:h-auto sm:max-h-[80dvh] sm:rounded-xl sm:border sm:border-border sm:pt-0 sm:shadow-lg"
            onMouseDown={(e) => e.stopPropagation()}
            onKeyDown={onKeyDown}
          >
            <div className="flex shrink-0 items-center border-b border-border">
              <input
                ref={inputRef}
                type="search"
                role="combobox"
                aria-expanded={items.length > 0}
                aria-controls="palette-results"
                aria-activedescendant={activeId}
                aria-label={t("searchPlaceholder")}
                placeholder={t("searchPlaceholder")}
                className="min-h-11 w-full min-w-0 flex-1 bg-transparent px-4 py-3 text-base focus:outline-none"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              <button type="button" className={`${ui.button} mr-2 min-h-11 sm:hidden`} onClick={close}>
                {t("close")}
              </button>
            </div>
            <div id="palette-results" role="listbox" aria-label={t("palette.title")} className="min-h-0 flex-1 overflow-auto py-1 sm:max-h-96 sm:flex-none">
              {sections.map((section) => (
                <div key={section.key} role="group" aria-label={section.title}>
                  <p className="px-4 pb-1 pt-2 text-xs font-medium uppercase tracking-wide text-subtle" aria-hidden="true">
                    {section.title}
                  </p>
                  {section.entries.map(({ item, index }) => (
                    <div
                      key={item.id}
                      id={item.id}
                      role="option"
                      aria-selected={index === active}
                      className={`flex min-h-11 cursor-pointer items-center gap-2 px-4 py-2 text-sm sm:pointer-fine:min-h-0 ${index === active ? "bg-surface-2" : ""}`}
                      onPointerMove={() => {
                        if (index !== active) setActive(index);
                      }}
                      onClick={() => run(item)}
                    >
                      {item.kind === "hit" || item.kind === "recent" ? (
                        <span className="text-xs text-muted">{t(`entity.${item.type}`)}</span>
                      ) : item.kind === "nav" ? (
                        <span className="text-xs text-muted">{item.group}</span>
                      ) : null}
                      <span className="font-medium">{item.label}</span>
                      {"subtitle" in item && item.subtitle ? <span className="text-muted">{item.subtitle}</span> : null}
                    </div>
                  ))}
                </div>
              ))}
            </div>
            <p className="flex items-center justify-between px-4 py-2 text-xs text-muted" role="status">
              <span>{status}</span>
              <span aria-hidden="true">{t("palette.keys")}</span>
            </p>
          </div>
        </div>
      ) : null}
    </>
  );
}

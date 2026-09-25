"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";
import { EmptyState } from "@/components/ui/EmptyState";

type Tab = "documents" | "contacts" | "events";

type ImmowareDocument = {
  id: string;
  href: string;
  display_name: string | null;
  content_type: string | null;
  size: number | null;
  last_modified: string | null;
  is_collection: boolean;
};

type ImmowareContact = {
  id: string;
  href: string;
  fn: string | null;
  org: string | null;
  emails: string[];
  phones: string[];
  matched_contact_id: string | null;
};

type ImmowareEvent = {
  id: string;
  href: string;
  summary: string | null;
  dtstart: string | null;
  dtend: string | null;
  location: string | null;
};

type Page<T> = { data: T[]; meta: { page: number; per_page: number; total: number } };

type ContactHit = { id: string; display_name: string };

const PAGE_SIZE = 25;

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function plusDaysIso(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function formatBytes(size: number | null): string {
  if (size === null) return "";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function breadcrumbFor(path: string): { label: string; path: string }[] {
  const parts = path.split("/").filter(Boolean);
  const crumbs: { label: string; path: string }[] = [{ label: "/", path: "" }];
  let acc = "";
  for (const part of parts) {
    acc = `${acc}${part}/`;
    crumbs.push({ label: part, path: acc });
  }
  return crumbs;
}

/** Immoware24-Browser (M32): Reiter fuer Dokumente, Kontakte und Termine, gespiegelt per DAV.
 *  Reine Leseansicht des Spiegels; Immoware24 selbst bleibt Master. */
export function ImmowareBrowser() {
  const t = useTranslations("Immoware");
  const [tab, setTab] = useState<Tab>("documents");
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2 border-b border-border-soft pb-2" role="tablist">
        {(["documents", "contacts", "events"] as const).map((value) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={tab === value}
            className={tab === value ? ui.badgeGold : ui.badge}
            onClick={() => setTab(value)}
          >
            {t(`tabs.${value}`)}
          </button>
        ))}
      </div>
      {tab === "documents" ? <DocumentsTab /> : null}
      {tab === "contacts" ? <ContactsTab /> : null}
      {tab === "events" ? <EventsTab /> : null}
    </div>
  );
}

function DocumentsTab() {
  const t = useTranslations("Immoware");
  const [path, setPath] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<Page<ImmowareDocument> | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoaded(false);
    setError(null);
    void (async () => {
      const params = new URLSearchParams({ path, page: String(page), page_size: String(PAGE_SIZE) });
      if (q.trim()) params.set("q", q.trim());
      const res = await bff<Page<ImmowareDocument>>(`/api/bff/immoware/documents?${params.toString()}`);
      if (!active) return;
      setLoaded(true);
      if (res.ok) setResult(res.data);
      else if (res.status === 502) setError(t("errors.notConfigured"));
      else if (res.status === 503) setError(t("errors.unreachable"));
      else setError(res.message);
    })();
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, q, page]);

  const rows = result?.data ?? [];
  const total = result?.meta.total ?? 0;
  const hasNext = page * PAGE_SIZE < total;
  const hasPrev = page > 1;

  return (
    <div className="flex flex-col gap-3">
      <nav aria-label={t("documents.breadcrumb")} className="mhvp-caption flex flex-wrap items-center gap-1 text-subtle">
        {breadcrumbFor(path).map((crumb, index) => (
          <span key={crumb.path || "root"} className="flex items-center gap-1">
            {index > 0 ? <span aria-hidden>/</span> : null}
            <button
              type="button"
              className="hover:text-fg hover:underline"
              onClick={() => {
                setPath(crumb.path);
                setPage(1);
              }}
            >
              {crumb.label}
            </button>
          </span>
        ))}
      </nav>
      <input
        type="search"
        className={ui.input}
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setPage(1);
        }}
        placeholder={t("documents.searchPlaceholder")}
        aria-label={t("documents.searchPlaceholder")}
      />
      {!loaded ? (
        <p className="text-sm text-muted">{t("loading")}</p>
      ) : error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : rows.length === 0 ? (
        <EmptyState title={t("documents.empty")} />
      ) : (
        <div className={`${ui.card} overflow-x-auto p-0`}>
          <div className="overflow-x-auto">
            <table className={ui.table} data-testid="immoware-documents">
              <thead>
                <tr>
                  <th>{t("documents.columns.name")}</th>
                  <th>{t("documents.columns.size")}</th>
                  <th>{t("documents.columns.modified")}</th>
                  <th>{t("documents.columns.actions")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((doc) => (
                  <tr key={doc.id}>
                    <td>
                      {doc.is_collection ? (
                        <button
                          type="button"
                          className="font-medium hover:underline"
                          onClick={() => {
                            setPath(doc.href.endsWith("/") ? doc.href : `${doc.href}/`);
                            setPage(1);
                          }}
                        >
                          {doc.display_name ?? doc.href}
                        </button>
                      ) : (
                        <span className="font-medium">{doc.display_name ?? doc.href}</span>
                      )}
                    </td>
                    <td className="tabular-nums text-muted">{formatBytes(doc.size)}</td>
                    <td className="tabular-nums text-muted">{formatDateTime(doc.last_modified)}</td>
                    <td>
                      {!doc.is_collection ? (
                        <a
                          href={`/api/bff/immoware/documents/${doc.id}/file`}
                          target="_blank"
                          rel="noreferrer"
                          className={ui.buttonSm}
                        >
                          {t("documents.download")}
                        </a>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {loaded && !error && total > PAGE_SIZE ? (
        <Pagination page={page} setPage={setPage} hasPrev={hasPrev} hasNext={hasNext} />
      ) : null}
    </div>
  );
}

function ContactsTab() {
  const t = useTranslations("Immoware");
  const [q, setQ] = useState("");
  const [unmatched, setUnmatched] = useState(false);
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<Page<ImmowareContact> | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [matchingId, setMatchingId] = useState<string | null>(null);
  const [matchQuery, setMatchQuery] = useState("");
  const [matchHits, setMatchHits] = useState<ContactHit[]>([]);
  const [rowError, setRowError] = useState<Record<string, string>>({});
  const [rowBusy, setRowBusy] = useState<string | null>(null);

  const load = async () => {
    setLoaded(false);
    setError(null);
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    if (q.trim()) params.set("q", q.trim());
    if (unmatched) params.set("unmatched", "true");
    const res = await bff<Page<ImmowareContact>>(`/api/bff/immoware/contacts?${params.toString()}`);
    setLoaded(true);
    if (res.ok) setResult(res.data);
    else if (res.status === 502) setError(t("errors.notConfigured"));
    else if (res.status === 503) setError(t("errors.unreachable"));
    else setError(res.message);
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, unmatched, page]);

  const searchContacts = async () => {
    const res = await bff<{ items: ContactHit[] }>(`/api/bff/contacts?q=${encodeURIComponent(matchQuery.trim())}`);
    if (res.ok) setMatchHits(res.data.items);
  };

  const match = async (davId: string, contactId: string) => {
    setRowBusy(davId);
    const res = await bff<ImmowareContact>(`/api/bff/immoware/contacts/${davId}/match`, {
      method: "POST",
      body: JSON.stringify({ contact_id: contactId }),
    });
    setRowBusy(null);
    if (res.ok) {
      setResult((prev) =>
        prev ? { ...prev, data: prev.data.map((c) => (c.id === davId ? res.data : c)) } : prev,
      );
      setMatchingId(null);
      setMatchQuery("");
      setMatchHits([]);
    } else {
      setRowError((prev) => ({ ...prev, [davId]: res.message }));
    }
  };

  const createContact = async (davId: string) => {
    setRowBusy(davId);
    const res = await bff<ImmowareContact>(`/api/bff/immoware/contacts/${davId}/create-contact`, { method: "POST" });
    setRowBusy(null);
    if (res.ok) {
      setResult((prev) =>
        prev ? { ...prev, data: prev.data.map((c) => (c.id === davId ? res.data : c)) } : prev,
      );
    } else {
      setRowError((prev) => ({ ...prev, [davId]: res.message }));
    }
  };

  const rows = result?.data ?? [];
  const total = result?.meta.total ?? 0;
  const hasNext = page * PAGE_SIZE < total;
  const hasPrev = page > 1;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="search"
          className={ui.input}
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
          placeholder={t("contacts.searchPlaceholder")}
          aria-label={t("contacts.searchPlaceholder")}
        />
        <label className="flex items-center gap-2 whitespace-nowrap text-sm">
          <input
            type="checkbox"
            checked={unmatched}
            onChange={(e) => {
              setUnmatched(e.target.checked);
              setPage(1);
            }}
          />
          {t("contacts.onlyUnmatched")}
        </label>
      </div>
      {!loaded ? (
        <p className="text-sm text-muted">{t("loading")}</p>
      ) : error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : rows.length === 0 ? (
        <EmptyState title={t("contacts.empty")} />
      ) : (
        <div className={`${ui.card} overflow-x-auto p-0`}>
          <div className="overflow-x-auto">
            <table className={ui.table} data-testid="immoware-contacts">
              <thead>
                <tr>
                  <th>{t("contacts.columns.name")}</th>
                  <th>{t("contacts.columns.org")}</th>
                  <th>{t("contacts.columns.email")}</th>
                  <th>{t("contacts.columns.phone")}</th>
                  <th>{t("contacts.columns.matched")}</th>
                  <th>{t("contacts.columns.actions")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={c.id}>
                    <td className="font-medium">{c.fn ?? ""}</td>
                    <td>{c.org ?? ""}</td>
                    <td className="text-xs">{c.emails.join(", ")}</td>
                    <td className="text-xs">{c.phones.join(", ")}</td>
                    <td>
                      {c.matched_contact_id ? (
                        <span className={ui.badgeSuccess}>{t("contacts.matched")}</span>
                      ) : (
                        <span className={ui.badge}>{t("contacts.unmatched")}</span>
                      )}
                    </td>
                    <td>
                      {!c.matched_contact_id ? (
                        <div className="flex flex-col gap-2">
                          {matchingId === c.id ? (
                            <div className="flex flex-col gap-1">
                              <div className="flex gap-2">
                                <input
                                  className={ui.input}
                                  value={matchQuery}
                                  onChange={(e) => setMatchQuery(e.target.value)}
                                  placeholder={t("contacts.matchPlaceholder")}
                                />
                                <button type="button" className={ui.buttonSm} onClick={searchContacts}>
                                  {t("contacts.search")}
                                </button>
                              </div>
                              {matchHits.length > 0 ? (
                                <ul className="flex flex-col gap-1">
                                  {matchHits.map((hit) => (
                                    <li key={hit.id}>
                                      <button
                                        type="button"
                                        className={ui.buttonSm}
                                        disabled={rowBusy === c.id}
                                        onClick={() => match(c.id, hit.id)}
                                      >
                                        {hit.display_name}
                                      </button>
                                    </li>
                                  ))}
                                </ul>
                              ) : null}
                            </div>
                          ) : (
                            <div className="flex flex-wrap gap-2">
                              <button type="button" className={ui.buttonSm} onClick={() => setMatchingId(c.id)}>
                                {t("contacts.match")}
                              </button>
                              <button
                                type="button"
                                className={ui.buttonSm}
                                disabled={rowBusy === c.id}
                                onClick={() => createContact(c.id)}
                              >
                                {t("contacts.createContact")}
                              </button>
                            </div>
                          )}
                          {rowError[c.id] ? <p className="text-xs text-danger-fg">{rowError[c.id]}</p> : null}
                        </div>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {loaded && !error && total > PAGE_SIZE ? (
        <Pagination page={page} setPage={setPage} hasPrev={hasPrev} hasNext={hasNext} />
      ) : null}
    </div>
  );
}

function EventsTab() {
  const t = useTranslations("Immoware");
  const [from, setFrom] = useState(todayIso());
  const [to, setTo] = useState(plusDaysIso(90));
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<Page<ImmowareEvent> | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoaded(false);
    setError(null);
    void (async () => {
      const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
      if (from) params.set("from", from);
      if (to) params.set("to", to);
      const res = await bff<Page<ImmowareEvent>>(`/api/bff/immoware/events?${params.toString()}`);
      if (!active) return;
      setLoaded(true);
      if (res.ok) setResult(res.data);
      else if (res.status === 502) setError(t("errors.notConfigured"));
      else if (res.status === 503) setError(t("errors.unreachable"));
      else setError(res.message);
    })();
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [from, to, page]);

  const rows = result?.data ?? [];
  const total = result?.meta.total ?? 0;
  const hasNext = page * PAGE_SIZE < total;
  const hasPrev = page > 1;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label htmlFor="imw-events-from" className={ui.label}>
            {t("events.from")}
          </label>
          <input
            id="imw-events-from"
            type="date"
            className={ui.input}
            value={from}
            onChange={(e) => {
              setFrom(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <div>
          <label htmlFor="imw-events-to" className={ui.label}>
            {t("events.to")}
          </label>
          <input
            id="imw-events-to"
            type="date"
            className={ui.input}
            value={to}
            onChange={(e) => {
              setTo(e.target.value);
              setPage(1);
            }}
          />
        </div>
      </div>
      {!loaded ? (
        <p className="text-sm text-muted">{t("loading")}</p>
      ) : error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : rows.length === 0 ? (
        <EmptyState title={t("events.empty")} />
      ) : (
        <ul className="flex flex-col gap-2">
          {rows.map((event) => (
            <li key={event.id} className={ui.card}>
              <p className="font-medium">{event.summary ?? ""}</p>
              <p className="text-sm text-muted">
                {formatDateTime(event.dtstart)}
                {event.dtend ? ` – ${formatDateTime(event.dtend)}` : ""}
              </p>
              {event.location ? <p className="text-xs text-subtle">{event.location}</p> : null}
            </li>
          ))}
        </ul>
      )}
      {loaded && !error && total > PAGE_SIZE ? (
        <Pagination page={page} setPage={setPage} hasPrev={hasPrev} hasNext={hasNext} />
      ) : null}
    </div>
  );
}

function Pagination({
  page,
  setPage,
  hasPrev,
  hasNext,
}: {
  page: number;
  setPage: (updater: (p: number) => number) => void;
  hasPrev: boolean;
  hasNext: boolean;
}) {
  const t = useTranslations("Immoware");
  return (
    <div className="flex items-center gap-2">
      <button type="button" className={ui.buttonSm} disabled={!hasPrev} onClick={() => setPage((p) => p - 1)}>
        {t("pagination.previous")}
      </button>
      <button type="button" className={ui.buttonSm} disabled={!hasNext} onClick={() => setPage((p) => p + 1)}>
        {t("pagination.next")}
      </button>
      <span className="text-xs text-muted">{t("pagination.page", { page })}</span>
    </div>
  );
}

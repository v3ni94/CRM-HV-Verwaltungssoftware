"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Katalogpflege (P1 AP4, 4.11 und Anhang B): Liste der Kataloge je Mandant, Einträge mit
 *  Anlegen, Umbenennen, Sortieren, Deaktivieren. Systemeinträge (Anhang B) lassen sich
 *  deaktivieren, aber nicht löschen; eigene Einträge lassen sich löschen. Schreibrecht
 *  `tenant_settings:update`. Endpunkte `GET /catalogs`, `GET|POST /catalogs/{catalog}`,
 *  `PATCH|DELETE /catalogs/{catalog}/{id}`. */
export type CatalogSummary = {
  catalog: string;
  entries: number;
  active: number;
  system: number;
};
export type CatalogEntry = {
  id: string;
  catalog: string;
  code: string;
  label: string;
  sort_order: number;
  active: boolean;
  is_system: boolean;
};

const CODE_PATTERN = /^[a-z0-9_]{1,63}$/;

export function CatalogAdmin({
  catalogs,
  canManage,
}: {
  catalogs: CatalogSummary[];
  canManage: boolean;
}) {
  const t = useTranslations("Settings.catalogs");
  const [summaries, setSummaries] = useState(catalogs);
  const [selected, setSelected] = useState<string>(catalogs[0]?.catalog ?? "");
  const [entries, setEntries] = useState<CatalogEntry[] | null>(null);
  const [code, setCode] = useState("");
  const [label, setLabel] = useState("");
  const [editing, setEditing] = useState<{
    id: string;
    label: string;
    sort_order: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const catalogLabel = (name: string) =>
    t.has(`names.${name}`) ? t(`names.${name}`) : name;

  async function load(name: string) {
    if (!name) return;
    const res = await bff<CatalogEntry[]>(
      `/api/bff/catalogs/${name}?include_inactive=true`,
    );
    if (res.ok) setEntries(res.data);
    else setError(res.message);
  }

  useEffect(() => {
    let cancelled = false;
    if (!selected) return;
    void bff<CatalogEntry[]>(
      `/api/bff/catalogs/${selected}?include_inactive=true`,
    ).then((res) => {
      if (cancelled) return;
      if (res.ok) setEntries(res.data);
      else setError(res.message);
    });
    return () => {
      cancelled = true;
    };
  }, [selected]);

  async function refreshSummaries() {
    const res = await bff<CatalogSummary[]>("/api/bff/catalogs");
    if (res.ok) setSummaries(res.data);
  }

  async function run(request: Promise<{ ok: boolean; message?: string }>) {
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await request;
    setBusy(false);
    if (res.ok) {
      setMessage(t("saved"));
      await Promise.all([load(selected), refreshSummaries()]);
      return true;
    }
    setError(res.message ?? t("failed"));
    return false;
  }

  async function add() {
    const nextCode = code.trim();
    if (!CODE_PATTERN.test(nextCode)) {
      setError(t("codeInvalid"));
      return;
    }
    if (!label.trim()) {
      setError(t("labelRequired"));
      return;
    }
    const sort = entries ? entries.length : 0;
    const ok = await run(
      bff(`/api/bff/catalogs/${selected}`, {
        method: "POST",
        body: JSON.stringify({
          code: nextCode,
          label: label.trim(),
          sort_order: sort,
        }),
      }),
    );
    if (ok) {
      setCode("");
      setLabel("");
    }
  }

  function toggle(entry: CatalogEntry) {
    void run(
      bff(`/api/bff/catalogs/${selected}/${entry.id}`, {
        method: "PATCH",
        body: JSON.stringify({ active: !entry.active }),
      }),
    );
  }

  async function saveEdit() {
    if (!editing) return;
    const sortOrder = Number.parseInt(editing.sort_order, 10);
    if (!editing.label.trim() || Number.isNaN(sortOrder)) {
      setError(t("labelRequired"));
      return;
    }
    const ok = await run(
      bff(`/api/bff/catalogs/${selected}/${editing.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          label: editing.label.trim(),
          sort_order: sortOrder,
        }),
      }),
    );
    if (ok) setEditing(null);
  }

  function remove(entry: CatalogEntry) {
    if (!window.confirm(t("confirmDelete", { label: entry.label }))) return;
    void run(
      bff(`/api/bff/catalogs/${selected}/${entry.id}`, { method: "DELETE" }),
    );
  }

  const readOnly = !canManage || busy;
  return (
    <div
      className="grid gap-4 lg:grid-cols-[18rem_1fr]"
      data-testid="catalog-admin"
    >
      <nav className={ui.card} aria-label={t("listTitle")}>
        <h2 className={ui.h2}>{t("listTitle")}</h2>
        <ul className="mt-2 flex max-h-[70vh] flex-col gap-0.5 overflow-y-auto">
          {summaries.map((c) => (
            <li key={c.catalog}>
              <button
                type="button"
                aria-current={c.catalog === selected ? "true" : undefined}
                className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm hover:bg-surface-2 ${c.catalog === selected ? "bg-surface-2 font-medium" : ""}`}
                onClick={() => {
                  setSelected(c.catalog);
                  setEditing(null);
                  setMessage(null);
                  setError(null);
                }}
              >
                <span>{catalogLabel(c.catalog)}</span>
                <span className={ui.badge}>{c.active}</span>
              </button>
            </li>
          ))}
        </ul>
      </nav>
      <section className={ui.card} aria-labelledby="catalog-entries-title">
        <div className="flex flex-col gap-3">
          <div>
            <h2 id="catalog-entries-title" className={ui.h2}>
              {catalogLabel(selected)}
            </h2>
            <p className={ui.help}>{t("entriesHelp", { code: selected })}</p>
          </div>
          {entries === null ? (
            <p className={ui.help}>{t("loading")}</p>
          ) : entries.length === 0 ? (
            <p className={ui.help}>{t("empty")}</p>
          ) : (
            <table className={ui.table} data-testid="catalog-entries">
              <thead>
                <tr>
                  <th>{t("colOrder")}</th>
                  <th>{t("colCode")}</th>
                  <th>{t("colLabel")}</th>
                  <th>{t("colKind")}</th>
                  <th>{t("colActive")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <tr key={e.id} className={e.active ? "" : "text-muted"}>
                    <td>
                      {editing?.id === e.id ? (
                        <input
                          className={ui.input}
                          type="number"
                          aria-label={t("colOrder")}
                          value={editing.sort_order}
                          onChange={(ev) =>
                            setEditing({
                              ...editing,
                              sort_order: ev.target.value,
                            })
                          }
                        />
                      ) : (
                        e.sort_order
                      )}
                    </td>
                    <td>
                      <code className="text-xs">{e.code}</code>
                    </td>
                    <td>
                      {editing?.id === e.id ? (
                        <input
                          className={ui.input}
                          aria-label={t("colLabel")}
                          value={editing.label}
                          maxLength={200}
                          onChange={(ev) =>
                            setEditing({ ...editing, label: ev.target.value })
                          }
                        />
                      ) : (
                        e.label
                      )}
                    </td>
                    <td>
                      {e.is_system ? (
                        <span className={ui.badgeGold}>{t("system")}</span>
                      ) : (
                        <span className={ui.badge}>{t("own")}</span>
                      )}
                    </td>
                    <td>
                      <input
                        type="checkbox"
                        checked={e.active}
                        disabled={readOnly}
                        aria-label={t("activeFor", { label: e.label })}
                        onChange={() => toggle(e)}
                      />
                    </td>
                    <td className="whitespace-nowrap">
                      {canManage ? (
                        editing?.id === e.id ? (
                          <span className="flex gap-1">
                            <button
                              type="button"
                              className={ui.buttonSm}
                              disabled={busy}
                              onClick={() => void saveEdit()}
                            >
                              {t("save")}
                            </button>
                            <button
                              type="button"
                              className={ui.buttonSm}
                              disabled={busy}
                              onClick={() => setEditing(null)}
                            >
                              {t("cancel")}
                            </button>
                          </span>
                        ) : (
                          <span className="flex gap-1">
                            <button
                              type="button"
                              className={ui.buttonSm}
                              disabled={busy}
                              onClick={() =>
                                setEditing({
                                  id: e.id,
                                  label: e.label,
                                  sort_order: String(e.sort_order),
                                })
                              }
                            >
                              {t("edit")}
                            </button>
                            {e.is_system ? null : (
                              <button
                                type="button"
                                className={ui.buttonSm}
                                disabled={busy}
                                onClick={() => remove(e)}
                              >
                                {t("delete")}
                              </button>
                            )}
                          </span>
                        )
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {canManage ? (
            <div className="flex flex-wrap items-end gap-2">
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("code")}</span>
                <input
                  className={ui.input}
                  value={code}
                  maxLength={63}
                  disabled={busy}
                  onChange={(e) => setCode(e.target.value)}
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className={ui.label}>{t("label")}</span>
                <input
                  className={ui.input}
                  value={label}
                  maxLength={200}
                  disabled={busy}
                  onChange={(e) => setLabel(e.target.value)}
                />
              </label>
              <button
                type="button"
                className={ui.primary}
                disabled={
                  busy || !selected || code.trim() === "" || label.trim() === ""
                }
                onClick={() => void add()}
              >
                {t("add")}
              </button>
            </div>
          ) : (
            <p className={ui.help}>{t("readOnly")}</p>
          )}
          <p className={ui.help}>{t("systemHint")}</p>
          {message ? (
            <span className="text-xs text-success-fg">{message}</span>
          ) : null}
          {error ? (
            <p role="alert" className={ui.alert}>
              {error}
            </p>
          ) : null}
        </div>
      </section>
    </div>
  );
}

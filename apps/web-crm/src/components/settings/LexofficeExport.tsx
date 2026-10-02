"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

type Kind = "contacts" | "invoices";
type Item = { id: string; label: string; date: string | null };
type ResultItem = { entity_id: string; ok: boolean; lexoffice_id?: string | null; error?: string | null; skipped_duplicate?: boolean };
type ExportResult = { run_id: string; items: ResultItem[] };

function listOf(data: unknown): Record<string, unknown>[] {
  if (Array.isArray(data)) return data as Record<string, unknown>[];
  const items = (data as { items?: unknown } | null)?.items;
  return Array.isArray(items) ? (items as Record<string, unknown>[]) : [];
}

/** Lexware Office Export (GAF-24): Auswahl der Datensätze (Kontakte oder Rechnungen, Rechnungen mit
 *  Zeitraum), Vorschau der Auswahl, Export und Download des Laufergebnisses. Der Export ist ein
 *  eigener bewusster Schritt, er läuft hinter dem Gate der Buchhaltung. */
export function LexofficeExport({ canExport }: { canExport: boolean }) {
  const t = useTranslations("Af20.lexExport");
  const [kind, setKind] = useState<Kind>("contacts");
  const [query, setQuery] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [items, setItems] = useState<Item[] | null>(null);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [template, setTemplate] = useState("{}");
  const [previewed, setPreviewed] = useState(false);
  const [result, setResult] = useState<ExportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setBusy(true);
    setError(null);
    setSelected({});
    setPreviewed(false);
    setResult(null);
    const url =
      kind === "contacts"
        ? `/api/bff/contacts?page_size=50${query.trim() ? `&q=${encodeURIComponent(query.trim())}` : ""}`
        : "/api/bff/accounting/invoices?page_size=200";
    const res = await bff<unknown>(url);
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    let rows: Item[] = listOf(res.data).map((r) =>
      kind === "contacts"
        ? { id: String(r.id), label: String(r.display_name ?? r.id), date: null }
        : { id: String(r.id), label: `${String(r.number ?? r.id)} (${String(r.gross ?? "")} EUR)`, date: (r.invoice_date as string | null) ?? null },
    );
    if (kind === "invoices") rows = rows.filter((r) => (!from || (r.date ?? "") >= from) && (!to || (r.date ?? "") <= to));
    setItems(rows);
  };

  const chosen = (items ?? []).filter((i) => selected[i.id]);
  let templateError: string | null = null;
  let payload: Record<string, unknown> = {};
  try {
    const parsed: unknown = JSON.parse(template);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) payload = parsed as Record<string, unknown>;
    else templateError = t("payloadInvalid");
  } catch {
    templateError = t("payloadInvalid");
  }

  const run = async () => {
    setBusy(true);
    setError(null);
    const idKey = kind === "contacts" ? "contact_id" : "invoice_id";
    const res = await bff<ExportResult>(`/api/bff/integrations/lexoffice/export/${kind}`, {
      method: "POST",
      body: JSON.stringify({ items: chosen.map((c) => ({ [idKey]: c.id, payload })) }),
    });
    setBusy(false);
    if (res.ok) setResult(res.data);
    else setError(res.message);
  };

  const download = () => {
    if (!result) return;
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `lexoffice-export-${result.run_id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className={ui.card} data-testid="lexoffice-export">
      <h2 className="text-sm font-semibold">{t("title")}</h2>
      <p className="text-xs text-muted">{t("intro")}</p>
      <div className="mt-2 flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("kind")}</span>
          <select className={ui.input} value={kind} onChange={(e) => { setKind(e.target.value as Kind); setItems(null); }}>
            <option value="contacts">{t("contacts")}</option>
            <option value="invoices">{t("invoices")}</option>
          </select>
        </label>
        {kind === "contacts" ? (
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("search")}</span>
            <input className={ui.input} value={query} onChange={(e) => setQuery(e.target.value)} />
          </label>
        ) : (
          <>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("from")}</span>
              <input type="date" className={ui.input} value={from} onChange={(e) => setFrom(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("to")}</span>
              <input type="date" className={ui.input} value={to} onChange={(e) => setTo(e.target.value)} />
            </label>
          </>
        )}
        <button type="button" className={ui.button} disabled={busy} onClick={() => void load()}>
          {t("load")}
        </button>
      </div>
      {items && items.length === 0 ? <p className="text-sm text-muted">{t("empty")}</p> : null}
      {items && items.length > 0 ? (
        <div className="mt-2 flex flex-col gap-2">
          <ul className="max-h-64 overflow-auto text-sm">
            {items.map((i) => (
              <li key={i.id}>
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={Boolean(selected[i.id])} onChange={(e) => { setSelected((p) => ({ ...p, [i.id]: e.target.checked })); setPreviewed(false); }} />
                  <span>{i.label}</span>
                  {i.date ? <span className="text-xs text-muted">{formatDate(i.date)}</span> : null}
                </label>
              </li>
            ))}
          </ul>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("payload")}</span>
            <textarea className={ui.input} rows={3} value={template} onChange={(e) => { setTemplate(e.target.value); setPreviewed(false); }} />
          </label>
          {templateError ? <p role="alert" className={ui.alert}>{templateError}</p> : null}
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className={ui.button} disabled={chosen.length === 0 || Boolean(templateError)} onClick={() => setPreviewed(true)}>
              {t("preview")}
            </button>
            {canExport ? (
              <button type="button" className={ui.primary} disabled={busy || !previewed || chosen.length === 0} onClick={() => void run()}>
                {t("export", { count: chosen.length })}
              </button>
            ) : null}
          </div>
          {previewed ? <p className="text-xs text-muted" data-testid="lexoffice-export-preview">{t("previewText", { count: chosen.length })}</p> : null}
        </div>
      ) : null}
      {result ? (
        <div className="mt-2 flex flex-col gap-1 text-sm" data-testid="lexoffice-export-result">
          <p>{t("resultText", { ok: result.items.filter((r) => r.ok).length, failed: result.items.filter((r) => !r.ok).length })}</p>
          <button type="button" className={ui.buttonSm} onClick={download}>
            {t("download")}
          </button>
        </div>
      ) : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </section>
  );
}

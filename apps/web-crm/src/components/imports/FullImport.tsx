"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatDateTime, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

const API = "/api/bff/imports/immoware24/vollimport";
export const KINDS = ["objektdaten", "eigentuemer", "mieter", "sonstige", "bank", "dienstleister", "adressen", "bankumsaetze", "salden", "eigentuemervertraege", "mietvertraege"] as const;
export type Kind = (typeof KINDS)[number];

export type Precheck = {
  datei: string;
  art: string;
  ok: boolean;
  sha256: string;
  bytes: number;
  zeichensatz: string;
  trennzeichen: string;
  kopfzeile: string[];
  pflichtspalten_fehlend: string[];
  optionale_spalten_fehlend: string[];
  unbekannte_spalten: string[];
  zeilen: number;
  dubletten: { schluessel: string; zeilen: number[] }[];
  pflichtfelder_fehlend: { zeile: number; feld: string }[];
  hinweise: string[];
};
export type Difference = { schluessel: string; grund?: string; anzahl?: number; felder?: { feld: string; soll: string | null; ist: string | null }[] };
/** Contract lists: count and target sum per object (file) against the platform (M8-02). */
export type PerObject = { objekt: string; soll_anzahl: number; ist_anzahl: number; soll_summe: string; ist_summe: string; abweichung: boolean };
export type Entity = {
  entitaet: string;
  soll: number;
  ist: number;
  uebereinstimmend: number;
  differenzen: number;
  fehlend: Difference[];
  doppelt: Difference[];
  abweichend: Difference[];
  zusaetzlich: Difference[];
  hinweise: string[];
  je_objekt?: PerObject[];
};
export type RunReport = {
  apply: boolean;
  id: string | null;
  import_run_id?: string | null;
  mode: string;
  stichtag: string;
  abgebrochen: boolean;
  dateien: { datei: string; art: string; sha256: string; bytes: number; zeilen: number }[];
  vorpruefung: Precheck[];
  counts: Record<string, Record<string, number>>;
  vorschau: Record<string, Record<string, number>>;
  abgleich: Entity[];
  differenzen: number;
  aktualisiert: { entitaet: string; schluessel: string; feld: string; alt: string | null; neu: string | null }[];
  eroeffnungssalden: { status?: string; hinweis?: string; summe?: string; anzahl?: Record<string, number>; eintraege?: unknown[] };
  dauer_ms: number;
};
export type RunSummary = {
  id: string;
  created_at: string;
  status: string;
  cutoff_date: string;
  files: { datei: string; art: string; zeilen: number }[];
  differences: number;
  duration_ms: number;
};

/** Guess of the export type from the file name (the operator can change it). */
export function kindFromFileName(name: string): Kind {
  const n = name.toLowerCase();
  if (n.includes("vertr") && n.includes("eigent")) return "eigentuemervertraege";
  if (n.includes("vertr") && n.includes("miet")) return "mietvertraege";
  if (n.includes("objekt")) return "objektdaten";
  if (n.includes("eigent")) return "eigentuemer";
  if (n.includes("miet")) return "mieter";
  if (n.includes("dienst")) return "dienstleister";
  if (n.includes("bankums") || n.includes("umsatz") || n.includes("umsaetze")) return "bankumsaetze";
  if (n.includes("bank")) return "bank";
  if (n.includes("adress")) return "adressen";
  if (n.includes("sald")) return "salden";
  if (n.includes("sonst")) return "sonstige";
  return "objektdaten";
}

type Picked = { file: File; kind: Kind };

function DifferenceList({ items, label }: { items: Difference[]; label: string }) {
  if (items.length === 0) return null;
  return (
    <details className="text-sm">
      <summary className="cursor-pointer font-medium">
        {label} ({items.length})
      </summary>
      <ul className="mt-1 list-disc pl-5">
        {items.slice(0, 200).map((d, i) => (
          <li key={`${d.schluessel}-${i}`}>
            <span className={ui.mono}>{d.schluessel}</span>
            {d.grund ? `: ${d.grund}` : ""}
            {d.anzahl ? `: ${d.anzahl}` : ""}
            {d.felder?.map((f) => ` ${f.feld}: Soll "${f.soll ?? ""}", Ist "${f.ist ?? ""}"`).join(";")}
          </li>
        ))}
      </ul>
    </details>
  );
}

export function PrecheckTable({ checks }: { checks: Precheck[] }) {
  const t = useTranslations("FullImport");
  return (
    <div className={ui.tableScroll}>
      <table className={ui.table} data-testid="fullimport-precheck">
        <thead>
          <tr>
            <th>{t("colFile")}</th>
            <th>{t("colKind")}</th>
            <th>{t("colRows")}</th>
            <th>{t("colEncoding")}</th>
            <th>{t("colResult")}</th>
          </tr>
        </thead>
        <tbody>
          {checks.map((c) => (
            <tr key={`${c.art}-${c.datei}`}>
              <td>
                {c.datei}
                <div className={`${ui.mono} text-xs text-muted`}>{c.sha256.slice(0, 16)}</div>
              </td>
              <td>{c.art}</td>
              <td className={ui.num}>{c.zeilen}</td>
              <td>
                {c.zeichensatz}, {c.trennzeichen}
              </td>
              <td>
                <span className={c.ok ? ui.badgeSuccess : ui.badgeDanger}>{c.ok ? t("checkOk") : t("checkFailed")}</span>
                <ul className="mt-1 text-xs">
                  {c.pflichtspalten_fehlend.length > 0 && (
                    <li>
                      {t("missingRequired")}: {c.pflichtspalten_fehlend.join(", ")}
                    </li>
                  )}
                  {c.optionale_spalten_fehlend.length > 0 && (
                    <li>
                      {t("missingOptional")}: {c.optionale_spalten_fehlend.join(", ")}
                    </li>
                  )}
                  {c.unbekannte_spalten.length > 0 && (
                    <li>
                      {t("unknownColumns")}: {c.unbekannte_spalten.join(", ")}
                    </li>
                  )}
                  {c.dubletten.length > 0 && (
                    <li>
                      {t("duplicates")}: {c.dubletten.map((d) => `${d.schluessel} (${d.zeilen.join(", ")})`).join("; ")}
                    </li>
                  )}
                  {c.pflichtfelder_fehlend.length > 0 && (
                    <li>
                      {t("missingFields")}: {c.pflichtfelder_fehlend.map((m) => `${t("row")} ${m.zeile} ${m.feld}`).join("; ")}
                    </li>
                  )}
                  {c.hinweise.map((h) => (
                    <li key={h}>{h}</li>
                  ))}
                </ul>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PerObjectTable({ entity }: { entity: Entity }) {
  const t = useTranslations("FullImport");
  const [onlyDeviations, setOnlyDeviations] = useState(false);
  const rows = entity.je_objekt ?? [];
  if (rows.length === 0) return null;
  const shown = onlyDeviations ? rows.filter((r) => r.abweichung) : rows;
  const deviations = rows.filter((r) => r.abweichung).length;
  return (
    <details className="text-sm" data-testid={`fullimport-per-object-${entity.entitaet}`}>
      <summary className="cursor-pointer font-medium">
        {entity.entitaet}: {t("contractsTitle")} ({deviations})
      </summary>
      <label className="mt-1 flex items-center gap-2 text-sm">
        <input type="checkbox" checked={onlyDeviations} onChange={(e) => setOnlyDeviations(e.target.checked)} />
        {t("onlyDeviations")}
      </label>
      <div className={ui.tableScroll}>
        <table className={ui.table}>
          <thead>
            <tr>
              <th>{t("colObject")}</th>
              <th>{t("colCountTarget")}</th>
              <th>{t("colCountActual")}</th>
              <th>{t("colSumTarget")}</th>
              <th>{t("colSumActual")}</th>
              <th>{t("colDeviation")}</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.objekt}>
                <td className={ui.mono}>{r.objekt}</td>
                <td className={ui.num}>{r.soll_anzahl}</td>
                <td className={ui.num}>{r.ist_anzahl}</td>
                <td className={ui.num}>{formatEur(r.soll_summe)}</td>
                <td className={ui.num}>{formatEur(r.ist_summe)}</td>
                <td>
                  <span className={r.abweichung ? ui.badgeWarning : ui.badgeSuccess}>{r.abweichung ? t("checkFailed") : t("checkOk")}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

export function ReconciliationTable({ entities }: { entities: Entity[] }) {
  const t = useTranslations("FullImport");
  return (
    <div className="flex flex-col gap-2">
      <div className={ui.tableScroll}>
        <table className={ui.table} data-testid="fullimport-reconciliation">
          <thead>
            <tr>
              <th>{t("colEntity")}</th>
              <th>{t("colTarget")}</th>
              <th>{t("colActual")}</th>
              <th>{t("colMatched")}</th>
              <th>{t("colMissing")}</th>
              <th>{t("colDuplicate")}</th>
              <th>{t("colDeviating")}</th>
            </tr>
          </thead>
          <tbody>
            {entities.map((e) => (
              <tr key={e.entitaet}>
                <td>{e.entitaet}</td>
                <td className={ui.num}>{e.soll}</td>
                <td className={ui.num}>{e.ist}</td>
                <td className={ui.num}>{e.uebereinstimmend}</td>
                <td className={ui.num}>{e.fehlend.length}</td>
                <td className={ui.num}>{e.doppelt.length}</td>
                <td className={ui.num}>{e.abweichend.length}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {entities.map((e) => (
        <div key={`d-${e.entitaet}`} className="flex flex-col gap-1">
          <DifferenceList items={e.fehlend} label={`${e.entitaet}: ${t("colMissing")}`} />
          <DifferenceList items={e.doppelt} label={`${e.entitaet}: ${t("colDuplicate")}`} />
          <DifferenceList items={e.abweichend} label={`${e.entitaet}: ${t("colDeviating")}`} />
          <PerObjectTable entity={e} />
          {e.hinweise.map((h) => (
            <p key={h} className={ui.help}>
              {h}
            </p>
          ))}
        </div>
      ))}
    </div>
  );
}

export function RunResult({ report }: { report: RunReport }) {
  const t = useTranslations("FullImport");
  const ob = report.eroeffnungssalden ?? {};
  return (
    <div className="flex flex-col gap-3" data-testid="fullimport-result">
      <p className={report.abgebrochen ? ui.alert : report.differenzen === 0 ? ui.success : ui.warning} role="status">
        {report.abgebrochen
          ? t("aborted")
          : t("summary", { mode: report.mode, cutoff: formatDate(report.stichtag), differences: report.differenzen, ms: report.dauer_ms })}
      </p>
      <PrecheckTable checks={report.vorpruefung} />
      {!report.abgebrochen && Object.keys(report.vorschau).length > 0 && (
        <div>
          <h3 className={ui.subtitle}>{report.apply ? t("appliedTitle") : t("previewTitle")}</h3>
          <ul className="text-sm" data-testid="fullimport-preview">
            {Object.entries(report.vorschau).map(([entity, counts]) => (
              <li key={entity}>
                <span className="font-medium">{entity}</span>:{" "}
                {Object.entries(counts)
                  .map(([k, v]) => `${k} ${v}`)
                  .join(", ")}
              </li>
            ))}
          </ul>
        </div>
      )}
      {!report.abgebrochen && report.abgleich.length > 0 && (
        <div>
          <h3 className={ui.subtitle}>{t("reconciliationTitle")}</h3>
          <ReconciliationTable entities={report.abgleich} />
        </div>
      )}
      {report.aktualisiert.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer font-medium">
            {t("updatedTitle")} ({report.aktualisiert.length})
          </summary>
          <ul className="mt-1 list-disc pl-5">
            {report.aktualisiert.map((u, i) => (
              <li key={`${u.schluessel}-${u.feld}-${i}`}>
                {u.entitaet} <span className={ui.mono}>{u.schluessel}</span> {u.feld}: &quot;{u.alt ?? ""}&quot; {"->"} &quot;{u.neu ?? ""}&quot;
              </li>
            ))}
          </ul>
        </details>
      )}
      {ob.status && (
        <div className={ui.notice} data-testid="fullimport-balances">
          <p className="font-medium">{t("balancesTitle")}</p>
          <p>{ob.hinweis}</p>
          <p>
            {t("balancesCounts", {
              proposals: ob.anzahl?.zugeordnet ?? 0,
              open: ob.anzahl?.offen ?? 0,
            })}
          </p>
        </div>
      )}
      {report.abgleich.some((e) => e.entitaet === "mietvertraege" || e.entitaet === "eigentuemervertraege") && <p className={ui.help}>{t("contractsHelp")}</p>}
      {report.id && (
        <p className="text-sm">
          <a className="font-medium hover:underline" href={`${API}/${report.id}/pdf`} target="_blank" rel="noreferrer">
            {t("pdfLink")}
          </a>
        </p>
      )}
    </div>
  );
}

/** Full import with cut-off date: pick the export files, pre-check, dry run, apply, reconcile. */
export function FullImport() {
  const t = useTranslations("FullImport");
  const [picked, setPicked] = useState<Picked[]>([]);
  const [cutoff, setCutoff] = useState("");
  const [numberMap, setNumberMap] = useState("");
  const [skipHandedOver, setSkipHandedOver] = useState(false);
  const [updateExisting, setUpdateExisting] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [prechecks, setPrechecks] = useState<Precheck[] | null>(null);
  const [report, setReport] = useState<RunReport | null>(null);
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [selected, setSelected] = useState<RunReport | null>(null);

  const loadRuns = useCallback(async () => {
    const res = await bff<RunSummary[]>(API);
    setRuns(res.ok ? res.data : []);
  }, []);
  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);

  const form = () => {
    const fd = new FormData();
    for (const p of picked) {
      fd.append("files", p.file);
      fd.append("kinds", p.kind);
    }
    return fd;
  };

  const precheck = async () => {
    setBusy("precheck");
    setError(null);
    setReport(null);
    const res = await bff<{ ok: boolean; vorpruefung: Precheck[] }>(`${API}/vorpruefung`, { method: "POST", body: form() });
    setBusy(null);
    if (res.ok) setPrechecks(res.data.vorpruefung);
    else setError(res.message);
  };

  const run = async (mode: "preview" | "apply" | "abgleich") => {
    if (mode === "apply" && !window.confirm(t("confirmApply"))) return;
    setBusy(mode);
    setError(null);
    const fd = form();
    fd.append("cutoff_date", cutoff);
    fd.append("number_map", numberMap);
    fd.append("skip_handed_over", skipHandedOver ? "true" : "false");
    fd.append("update_existing", updateExisting ? "true" : "false");
    const res = await bff<RunReport>(`${API}?mode=${mode}`, { method: "POST", body: fd });
    setBusy(null);
    if (res.ok) {
      setPrechecks(null);
      setReport(res.data);
      if (mode !== "preview") await loadRuns();
    } else setError(res.message);
  };

  const openRun = async (id: string) => {
    setError(null);
    const res = await bff<{ report: RunReport; opening_balances: RunReport["eroeffnungssalden"]; id: string; status: string }>(`${API}/${id}`);
    if (res.ok) setSelected({ ...res.data.report, id: res.data.id, apply: res.data.status === "applied", eroeffnungssalden: res.data.opening_balances });
    else setError(res.message);
  };

  const ready = picked.length > 0 && cutoff !== "" && busy === null;
  return (
    <div className={ui.sectionGap}>
      <p className={ui.notice}>{t("intro")}</p>
      <section className={ui.card}>
        <h2 className={ui.title}>{t("filesTitle")}</h2>
        <div className="mt-3 flex flex-col gap-3">
          <label className={ui.label}>
            {t("files")}
            <input
              type="file"
              multiple
              accept=".csv,text/csv"
              data-testid="fullimport-files"
              className="mt-1 block text-sm"
              onChange={(e) => {
                const files = Array.from(e.target.files ?? []);
                setPicked(files.map((file) => ({ file, kind: kindFromFileName(file.name) })));
                setPrechecks(null);
                setReport(null);
              }}
            />
          </label>
          {picked.length > 0 && (
            <ul className="flex flex-col gap-1 text-sm" data-testid="fullimport-picked">
              {picked.map((p, i) => (
                <li key={p.file.name} className="flex flex-wrap items-center gap-2">
                  <span>{p.file.name}</span>
                  <select
                    aria-label={t("kindFor", { file: p.file.name })}
                    className={ui.input}
                    value={p.kind}
                    onChange={(e) => setPicked((prev) => prev.map((x, j) => (j === i ? { ...x, kind: e.target.value as Kind } : x)))}
                  >
                    {KINDS.map((k) => (
                      <option key={k} value={k}>
                        {t(`kind.${k}`)}
                      </option>
                    ))}
                  </select>
                </li>
              ))}
            </ul>
          )}
          <label className={ui.label}>
            {t("cutoff")}
            <input type="date" className={ui.input} value={cutoff} onChange={(e) => setCutoff(e.target.value)} data-testid="fullimport-cutoff" />
            <span className={ui.help}>{t("cutoffHelp")}</span>
          </label>
          <label className={ui.label}>
            {t("numberMap")}
            <textarea className={ui.input} rows={2} value={numberMap} onChange={(e) => setNumberMap(e.target.value)} />
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={skipHandedOver} onChange={(e) => setSkipHandedOver(e.target.checked)} />
            {t("skipHandedOver")}
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={updateExisting} onChange={(e) => setUpdateExisting(e.target.checked)} data-testid="fullimport-update" />
            {t("updateExisting")}
          </label>
          <div className={ui.formActions}>
            <button type="button" className={ui.secondary} disabled={picked.length === 0 || busy !== null} onClick={precheck} data-testid="fullimport-precheck-button">
              {busy === "precheck" ? t("working") : t("precheck")}
            </button>
            <button type="button" className={ui.secondary} disabled={!ready} onClick={() => run("preview")} data-testid="fullimport-preview-button">
              {busy === "preview" ? t("working") : t("dryRun")}
            </button>
            <button type="button" className={ui.secondary} disabled={!ready} onClick={() => run("abgleich")} data-testid="fullimport-reconcile-button">
              {busy === "abgleich" ? t("working") : t("reconcileOnly")}
            </button>
            <button type="button" className={ui.primary} disabled={!ready || !report || report.apply || report.abgebrochen} onClick={() => run("apply")} data-testid="fullimport-apply-button">
              {busy === "apply" ? t("working") : t("apply")}
            </button>
          </div>
          <p className={ui.help}>{t("applyHelp")}</p>
        </div>
      </section>
      {error && (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      )}
      {prechecks && <PrecheckTable checks={prechecks} />}
      {report && <RunResult report={report} />}
      <section className={ui.card}>
        <h2 className={ui.title}>{t("runsTitle")}</h2>
        {runs === null ? (
          <p className={ui.help}>{t("loading")}</p>
        ) : runs.length === 0 ? (
          <p className={ui.help}>{t("noRuns")}</p>
        ) : (
          <div className={ui.tableScroll}>
            <table className={ui.table} data-testid="fullimport-runs">
              <thead>
                <tr>
                  <th>{t("colCreated")}</th>
                  <th>{t("colStatus")}</th>
                  <th>{t("cutoff")}</th>
                  <th>{t("colFiles")}</th>
                  <th>{t("colDifferences")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id}>
                    <td>{formatDateTime(r.created_at)}</td>
                    <td>{t(`status.${r.status}`)}</td>
                    <td>{formatDate(r.cutoff_date)}</td>
                    <td>{r.files.map((f) => `${f.art} (${f.zeilen})`).join(", ")}</td>
                    <td className={ui.num}>
                      <span className={r.differences === 0 ? ui.badgeSuccess : ui.badgeWarning}>{r.differences}</span>
                    </td>
                    <td className="flex gap-2">
                      <button type="button" className={ui.buttonSm} onClick={() => void openRun(r.id)}>
                        {t("open")}
                      </button>
                      <a className="text-sm font-medium hover:underline" href={`${API}/${r.id}/pdf`} target="_blank" rel="noreferrer">
                        {t("pdfLink")}
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {selected && (
          <div className="mt-4">
            <RunResult report={selected} />
          </div>
        )}
      </section>
    </div>
  );
}

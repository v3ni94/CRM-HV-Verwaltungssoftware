"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

const API = "/api/bff/imports/immoware24/lists";
const ROLES = ["eigentuemer", "mieter", "dienstleister", "bank", "sonstige"] as const;
type Role = (typeof ROLES)[number];

type PropertyEntry = {
  objekt: string;
  nummer: string | null;
  bezeichnung: string;
  status: string;
  hinweise: string[];
  probleme?: string[];
  einheiten: Record<string, number>;
  einheiten_probleme?: { ve: string; meldungen: string[] }[];
};
type ContactEntry = {
  datei: string;
  zeile: number;
  id: string;
  name: string;
  rolle: string;
  status: string;
  hinweise: string[];
  probleme?: string[];
};
type AssignmentEntry = { objekt: string; ve: string; zeile: number; rolle?: string; name?: string; grund?: string; hinweis?: string; kandidaten?: string[] };
type Report = {
  mode: "preview" | "apply";
  apply: boolean;
  import_run_id?: string;
  counts: Record<string, number>;
  objekte?: PropertyEntry[];
  kontakte?: ContactEntry[];
  start_date?: string;
  start_date_assumed?: boolean;
  einheiten_gesamt?: number;
  eigentuemer_zugeordnet?: number;
  mieter_zugeordnet?: number;
  leerstand?: number;
  nicht_gefunden?: AssignmentEntry[];
  mehrdeutig?: AssignmentEntry[];
  konflikte?: AssignmentEntry[];
  hinweise?: AssignmentEntry[];
};
type Prefix = "objektdaten" | "kontakte" | "zuordnung";

/** Collapsible list of the report (closed by default, count in the summary). */
function Collapsible({ title, count, testId, children }: { title: string; count: number; testId: string; children: ReactNode }) {
  const t = useTranslations("ImmowareLists");
  return (
    <details className="flex flex-col gap-1" data-testid={`${testId}-details`}>
      <summary className="cursor-pointer text-sm font-semibold">
        {title} ({count})
      </summary>
      {count === 0 ? <p className="text-sm text-muted">{t("noEntries")}</p> : children}
    </details>
  );
}

/** Result banner, counts and the link to the import run shared by both cards. */
function ReportHead({ report, prefix, testId, extra = [] }: { report: Report; prefix: Prefix; testId: string; extra?: [string, number][] }) {
  const t = useTranslations("ImmowareLists");
  return (
    <div className="flex flex-col gap-2" data-testid={testId}>
      <p className={report.apply ? ui.success : ui.notice} data-testid={`${testId}-mode`}>
        {report.apply ? t("resultApplied") : t("resultTest")}
      </p>
      <div className="overflow-x-auto">
        <table className={ui.table} data-testid={`${testId}-counts`}>
          <thead>
            <tr>
              <th>{t("colCount")}</th>
              <th>{t("colValue")}</th>
            </tr>
          </thead>
          <tbody>
            {[...extra, ...Object.entries(report.counts)].map(([key, value]) => (
              <tr key={key}>
                <td>{t.has(`${prefix}.count.${key}`) ? t(`${prefix}.count.${key}`) : key}</td>
                <td>{key.startsWith("zahlungen_cent_") ? formatCents(value) : value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {report.import_run_id ? (
        <Link href={`/importe/${report.import_run_id}`} className="text-sm font-medium hover:underline">
          {t("runLink")}
        </Link>
      ) : null}
    </div>
  );
}

function formatCents(cents: number) {
  return `${(cents / 100).toLocaleString("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} EUR`;
}

function status(t: ReturnType<typeof useTranslations<"ImmowareLists">>, value: string) {
  return t.has(`status.${value}`) ? t(`status.${value}`) : value;
}

function ObjektdatenReport({ report }: { report: Report }) {
  const t = useTranslations("ImmowareLists");
  const rows = report.objekte ?? [];
  const skipped = rows.filter((r) => r.status === "übersprungen");
  const conflicts = rows.filter((r) => r.status !== "übersprungen" && (r.probleme?.length || r.einheiten_probleme?.length || r.status === "conflict"));
  const notes = rows.filter((r) => r.hinweise.length > 0);
  const table = (title: string, items: PropertyEntry[], testId: string, messages: (r: PropertyEntry) => string[]) => (
    <Collapsible title={title} count={items.length} testId={testId}>
      {(
        <div className="overflow-x-auto">
          <table className={ui.table} data-testid={testId}>
            <thead>
              <tr>
                <th>{t("objektdaten.colObject")}</th>
                <th>{t("objektdaten.colNumber")}</th>
                <th>{t("objektdaten.colName")}</th>
                <th>{t("colStatus")}</th>
                <th>{t("objektdaten.colUnits")}</th>
                <th>{t("colMessages")}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.objekt}>
                  <td>{r.objekt}</td>
                  <td>{r.nummer ?? ""}</td>
                  <td>{r.bezeichnung}</td>
                  <td>{status(t, r.status)}</td>
                  <td>
                    {Object.entries(r.einheiten)
                      .map(([k, v]) => `${status(t, k)} ${v}`)
                      .join(", ")}
                  </td>
                  <td>
                    <ul className="list-disc pl-4">
                      {messages(r).map((m, i) => (
                        <li key={i}>{m}</li>
                      ))}
                    </ul>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Collapsible>
  );
  return (
    <div className="flex flex-col gap-4">
      <ReportHead report={report} prefix="objektdaten" testId="objektdaten-report" />
      {table(t("objektdaten.skippedTitle"), skipped, "objektdaten-skipped", (r) => r.probleme ?? [])}
      {table(t("objektdaten.notesTitle"), notes, "objektdaten-notes", (r) => r.hinweise)}
      {table(t("objektdaten.conflictsTitle"), conflicts, "objektdaten-conflicts", (r) => [
        ...(r.probleme ?? []),
        ...(r.einheiten_probleme ?? []).map((u) => `VE ${u.ve}: ${u.meldungen.join("; ")}`),
      ])}
    </div>
  );
}

function KontakteReport({ report }: { report: Report }) {
  const t = useTranslations("ImmowareLists");
  const rows = (report.kontakte ?? []).filter((r) => r.hinweise.length > 0 || (r.probleme?.length ?? 0) > 0);
  return (
    <div className="flex flex-col gap-4">
      <ReportHead report={report} prefix="kontakte" testId="kontakte-report" />
      <Collapsible title={t("kontakte.notesTitle")} count={rows.length} testId="kontakte-notes">
        {(
          <div className="overflow-x-auto">
            <table className={ui.table} data-testid="kontakte-notes">
              <thead>
                <tr>
                  <th>{t("kontakte.colFile")}</th>
                  <th>{t("kontakte.colLine")}</th>
                  <th>{t("kontakte.colId")}</th>
                  <th>{t("kontakte.colName")}</th>
                  <th>{t("kontakte.colRole")}</th>
                  <th>{t("colStatus")}</th>
                  <th>{t("colMessages")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={`${r.datei}:${r.zeile}`}>
                    <td>{r.datei}</td>
                    <td>{r.zeile}</td>
                    <td>{r.id}</td>
                    <td>{r.name}</td>
                    <td>{t.has(`kontakte.roleOption.${r.rolle}`) ? t(`kontakte.roleOption.${r.rolle}`) : r.rolle}</td>
                    <td>{status(t, r.status)}</td>
                    <td>
                      <ul className="list-disc pl-4">
                        {[...r.hinweise, ...(r.probleme ?? [])].map((m, i) => (
                          <li key={i}>{m}</li>
                        ))}
                      </ul>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Collapsible>
    </div>
  );
}

function AssignmentList({ title, items, testId }: { title: string; items: AssignmentEntry[]; testId: string }) {
  const t = useTranslations("ImmowareLists");
  return (
    <Collapsible title={title} count={items.length} testId={testId}>
      <div className="overflow-x-auto">
        <table className={ui.table} data-testid={testId}>
          <thead>
            <tr>
              <th>{t("objektdaten.colObject")}</th>
              <th>{t("zuordnung.colUnit")}</th>
              <th>{t("kontakte.colLine")}</th>
              <th>{t("kontakte.colRole")}</th>
              <th>{t("kontakte.colName")}</th>
              <th>{t("colMessages")}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((r, i) => (
              <tr key={`${r.zeile}:${r.rolle ?? ""}:${i}`}>
                <td>{r.objekt}</td>
                <td>{r.ve}</td>
                <td>{r.zeile}</td>
                <td>{r.rolle ?? ""}</td>
                <td>{r.name ?? ""}</td>
                <td>{r.grund ?? r.hinweis ?? (r.kandidaten ?? []).join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Collapsible>
  );
}

function ZuordnungReport({ report }: { report: Report }) {
  const t = useTranslations("ImmowareLists");
  const extra: [string, number][] = [
    ["einheiten_gesamt", report.einheiten_gesamt ?? 0],
    ["eigentuemer_zugeordnet", report.eigentuemer_zugeordnet ?? 0],
    ["mieter_zugeordnet", report.mieter_zugeordnet ?? 0],
    ["leerstand", report.leerstand ?? 0],
  ];
  return (
    <div className="flex flex-col gap-4">
      <ReportHead report={report} prefix="zuordnung" testId="zuordnung-report" extra={extra} />
      {report.start_date ? (
        <p className="text-sm" data-testid="zuordnung-start">
          {t("zuordnung.startUsed", { date: formatDate(report.start_date) })}
          {report.start_date_assumed ? ` ${t("zuordnung.startAssumed")}` : ""}
        </p>
      ) : null}
      <AssignmentList title={t("zuordnung.notFoundTitle")} items={report.nicht_gefunden ?? []} testId="zuordnung-not-found" />
      <AssignmentList title={t("zuordnung.ambiguousTitle")} items={report.mehrdeutig ?? []} testId="zuordnung-ambiguous" />
      <AssignmentList title={t("zuordnung.conflictsTitle")} items={report.konflikte ?? []} testId="zuordnung-conflicts" />
      <AssignmentList title={t("zuordnung.notesTitle")} items={report.hinweise ?? []} testId="zuordnung-notes" />
    </div>
  );
}

/** Test run and apply of one list import; apply is enabled only after a test run with the
 *  same input (a signature of files and options) and asks for confirmation. */
function useListRun(path: string) {
  const [report, setReport] = useState<Report | null>(null);
  const [testedFor, setTestedFor] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (mode: "preview" | "apply", form: FormData, signature: string) => {
    setError(null);
    setBusy(true);
    const res = await bff<Report>(`${API}/${path}?mode=${mode}`, { method: "POST", body: form });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setReport(res.data);
    setTestedFor(mode === "preview" ? signature : null);
  };
  return { report, testedFor, busy, error, run };
}

function ActionRow({
  t,
  busy,
  canApply,
  onTest,
  onApply,
  testId,
}: {
  t: ReturnType<typeof useTranslations<"ImmowareLists">>;
  busy: boolean;
  canApply: boolean;
  onTest: () => void;
  onApply: () => void;
  testId: string;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        <button type="button" className={ui.button} onClick={onTest} disabled={busy} data-testid={`${testId}-test`}>
          {t("testRun")}
        </button>
        <button type="button" className={ui.primary} onClick={onApply} disabled={busy || !canApply} data-testid={`${testId}-apply`}>
          {t("apply")}
        </button>
        {busy ? <span className="text-sm text-muted">{t("busy")}</span> : null}
      </div>
      {!canApply ? <p className={ui.help}>{t("applyHint")}</p> : null}
    </div>
  );
}

function fileKey(file: File | null) {
  return file ? `${file.name}:${file.size}:${file.lastModified}` : "";
}

export function ObjektdatenCard() {
  const t = useTranslations("ImmowareLists");
  const [file, setFile] = useState<File | null>(null);
  const [numberMap, setNumberMap] = useState("");
  const [skipHandedOver, setSkipHandedOver] = useState(false);
  const { report, testedFor, busy, error, run } = useListRun("objektdaten");
  const signature = `${fileKey(file)}|${numberMap.trim()}|${skipHandedOver}`;
  const canApply = testedFor !== null && testedFor === signature;

  const start = (mode: "preview" | "apply") => {
    if (!file) return;
    if (mode === "apply" && !window.confirm(t("applyConfirm"))) return;
    const form = new FormData();
    form.set("file", file);
    form.set("number_map", numberMap);
    form.set("skip_handed_over", skipHandedOver ? "true" : "false");
    void run(mode, form, signature);
  };

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="objektdaten-title" data-testid="objektdaten-card">
      <h3 id="objektdaten-title" className="text-base font-semibold">
        {t("objektdaten.title")}
      </h3>
      <p className={ui.help}>{t("objektdaten.help")}</p>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("objektdaten.file")}</span>
        <input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("objektdaten.numberMap")}</span>
        <textarea className={ui.input} rows={3} value={numberMap} onChange={(e) => setNumberMap(e.target.value)} />
        <span className={ui.help}>{t("objektdaten.numberMapHelp")}</span>
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={skipHandedOver} onChange={(e) => setSkipHandedOver(e.target.checked)} />
        {t("objektdaten.skipHandedOver")}
      </label>
      <ActionRow t={t} busy={busy} canApply={canApply && !!file} onTest={() => (file ? start("preview") : undefined)} onApply={() => start("apply")} testId="objektdaten" />
      {!file ? <p className={ui.help}>{t("fileRequired")}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {report ? <ObjektdatenReport report={report} /> : null}
    </section>
  );
}

/** Role from the file name (eigentuemer.csv, Mieter.csv, ...), otherwise "sonstige". */
export function roleFromFileName(name: string): Role {
  const lower = name.toLowerCase().replace("ü", "ue").replace("ä", "ae");
  if (lower.includes("eigentuemer") || lower.includes("eigentümer")) return "eigentuemer";
  if (lower.includes("mieter")) return "mieter";
  if (lower.includes("dienstleister")) return "dienstleister";
  if (lower.includes("bank")) return "bank";
  return "sonstige";
}

export function KontakteCard() {
  const t = useTranslations("ImmowareLists");
  const [chosen, setChosen] = useState<{ file: File; role: Role }[]>([]);
  const { report, testedFor, busy, error, run } = useListRun("kontakte");
  const signature = chosen.map((x) => `${fileKey(x.file)}=${x.role}`).join("|");
  const canApply = chosen.length > 0 && testedFor !== null && testedFor === signature;

  const start = (mode: "preview" | "apply") => {
    if (chosen.length === 0) return;
    if (mode === "apply" && !window.confirm(t("applyConfirm"))) return;
    const form = new FormData();
    for (const x of chosen) {
      form.append("files", x.file);
      form.append("roles", x.role);
    }
    void run(mode, form, signature);
  };

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="kontakte-title" data-testid="kontakte-card">
      <h3 id="kontakte-title" className="text-base font-semibold">
        {t("kontakte.title")}
      </h3>
      <p className={ui.help}>{t("kontakte.help")}</p>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("kontakte.files")}</span>
        <input
          type="file"
          multiple
          accept=".csv,text/csv"
          onChange={(e) => setChosen(Array.from(e.target.files ?? []).map((file) => ({ file, role: roleFromFileName(file.name) })))}
        />
      </label>
      {chosen.map((x, i) => (
        <label key={`${x.file.name}:${i}`} className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-3">
          <span className={ui.label}>{t("kontakte.role", { name: x.file.name })}</span>
          <select className={ui.input} value={x.role} onChange={(e) => setChosen((list) => list.map((c, j) => (j === i ? { ...c, role: e.target.value as Role } : c)))}>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {t(`kontakte.roleOption.${r}`)}
              </option>
            ))}
          </select>
        </label>
      ))}
      <ActionRow t={t} busy={busy} canApply={canApply} onTest={() => start("preview")} onApply={() => start("apply")} testId="kontakte" />
      {chosen.length === 0 ? <p className={ui.help}>{t("fileRequired")}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {report ? <KontakteReport report={report} /> : null}
    </section>
  );
}

function defaultStart(today = new Date()) {
  return `${today.getFullYear()}-01-01`;
}

export function ZuordnungCard() {
  const t = useTranslations("ImmowareLists");
  const [file, setFile] = useState<File | null>(null);
  const [startDate, setStartDate] = useState(defaultStart());
  const [skipHandedOver, setSkipHandedOver] = useState(false);
  const { report, testedFor, busy, error, run } = useListRun("zuordnung");
  const signature = `${fileKey(file)}|${startDate}|${skipHandedOver}`;
  const canApply = testedFor !== null && testedFor === signature;

  const start = (mode: "preview" | "apply") => {
    if (!file) return;
    if (mode === "apply" && !window.confirm(t("applyConfirm"))) return;
    const form = new FormData();
    form.set("file", file);
    if (startDate) form.set("start_date", startDate);
    form.set("skip_handed_over", skipHandedOver ? "true" : "false");
    void run(mode, form, signature);
  };

  return (
    <section className={`${ui.card} flex flex-col gap-3`} aria-labelledby="zuordnung-title" data-testid="zuordnung-card">
      <h3 id="zuordnung-title" className="text-base font-semibold">
        {t("zuordnung.title")}
      </h3>
      <p className={ui.help}>{t("zuordnung.help")}</p>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("zuordnung.file")}</span>
        <input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("zuordnung.startDate")}</span>
        <input type="date" className={ui.input} value={startDate} onChange={(e) => setStartDate(e.target.value)} />
        <span className={ui.help}>{t("zuordnung.startDateHelp")}</span>
      </label>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={skipHandedOver} onChange={(e) => setSkipHandedOver(e.target.checked)} />
        {t("objektdaten.skipHandedOver")}
      </label>
      <ActionRow t={t} busy={busy} canApply={canApply && !!file} onTest={() => start("preview")} onApply={() => start("apply")} testId="zuordnung" />
      {!file ? <p className={ui.help}>{t("fileRequired")}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {report ? <ZuordnungReport report={report} /> : null}
    </section>
  );
}

/** Page body "Immoware24 Listenimport": the three operator commands (objektdaten, kontakte,
 *  zuordnung) in their required order, without server access. */
export function ListImports() {
  const t = useTranslations("ImmowareLists");
  return (
    <div className="flex flex-col gap-4">
      <p className={ui.notice} data-testid="immoware-lists-order">
        {t("intro")}
      </p>
      <ObjektdatenCard />
      <KontakteCard />
      <ZuordnungCard />
    </div>
  );
}

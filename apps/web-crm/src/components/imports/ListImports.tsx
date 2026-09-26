"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

const API = "/api/bff/imports/immoware24/lists";
const ROLES = ["eigentuemer", "mieter", "bank", "sonstige"] as const;
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
type Report = {
  mode: "preview" | "apply";
  apply: boolean;
  import_run_id?: string;
  counts: Record<string, number>;
  /** What the reader tolerated: encoding, delimiter, skipped or repeated lines. */
  datei_hinweise?: string[];
  objekte?: PropertyEntry[];
  kontakte?: ContactEntry[];
};

/** Result banner, counts and the link to the import run shared by both cards. */
function ReportHead({ report, prefix, testId }: { report: Report; prefix: "objektdaten" | "kontakte"; testId: string }) {
  const t = useTranslations("ImmowareLists");
  return (
    <div className="flex flex-col gap-2" data-testid={testId}>
      <p className={report.apply ? ui.success : ui.notice} data-testid={`${testId}-mode`}>
        {report.apply ? t("resultApplied") : t("resultTest")}
      </p>
      {report.datei_hinweise && report.datei_hinweise.length > 0 ? (
        <ul className="list-disc pl-4 text-sm text-muted" data-testid={`${testId}-file-notes`} aria-label={t("fileNotes")}>
          {report.datei_hinweise.map((note, i) => (
            <li key={i}>{note}</li>
          ))}
        </ul>
      ) : null}
      <dl className="flex flex-wrap gap-4 text-sm">
        {Object.entries(report.counts).map(([key, value]) => (
          <div key={key} className="flex flex-col">
            <dt className="text-xs text-muted">{t.has(`${prefix}.count.${key}`) ? t(`${prefix}.count.${key}`) : key}</dt>
            <dd className="font-semibold">{value}</dd>
          </div>
        ))}
      </dl>
      {report.import_run_id ? (
        <Link href={`/importe/${report.import_run_id}`} className="text-sm font-medium hover:underline">
          {t("runLink")}
        </Link>
      ) : null}
    </div>
  );
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
    <section className="flex flex-col gap-1" aria-label={title}>
      <h4 className="text-sm font-semibold">{title}</h4>
      {items.length === 0 ? (
        <p className="text-sm text-muted">{t("noEntries")}</p>
      ) : (
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
    </section>
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
      <section className="flex flex-col gap-1" aria-label={t("kontakte.notesTitle")}>
        <h4 className="text-sm font-semibold">{t("kontakte.notesTitle")}</h4>
        {rows.length === 0 ? (
          <p className="text-sm text-muted">{t("noEntries")}</p>
        ) : (
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
      </section>
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

export function KontakteCard() {
  const t = useTranslations("ImmowareLists");
  const [files, setFiles] = useState<(File | null)[]>([null, null, null, null]);
  const [roles, setRoles] = useState<Role[]>(["eigentuemer", "mieter", "bank", "sonstige"]);
  const { report, testedFor, busy, error, run } = useListRun("kontakte");
  const chosen = files.map((f, i) => ({ file: f, role: roles[i]! })).filter((x): x is { file: File; role: Role } => x.file !== null);
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
      {files.map((_, i) => (
        <div key={i} className="grid gap-2 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("kontakte.file", { index: i + 1 })}</span>
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => setFiles((list) => list.map((f, j) => (j === i ? (e.target.files?.[0] ?? null) : f)))}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("kontakte.role", { index: i + 1 })}</span>
            <select className={ui.input} value={roles[i]} onChange={(e) => setRoles((list) => list.map((r, j) => (j === i ? (e.target.value as Role) : r)))}>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {t(`kontakte.roleOption.${r}`)}
                </option>
              ))}
            </select>
          </label>
        </div>
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

/** Section "Immoware24-Listen" of the import assistant: the two list imports of the operator
 *  commands (objektdaten, kontakte) without server access. */
export function ListImports() {
  const t = useTranslations("ImmowareLists");
  return (
    <section className="flex flex-col gap-4" aria-labelledby="immoware-lists-title">
      <h2 id="immoware-lists-title" className={ui.h2}>
        {t("title")}
      </h2>
      <p className="text-sm text-muted">{t("intro")}</p>
      <div className="grid gap-4 lg:grid-cols-2">
        <ObjektdatenCard />
        <KontakteCard />
      </div>
    </section>
  );
}

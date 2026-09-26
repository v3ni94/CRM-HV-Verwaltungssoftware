"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate, formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

export type InspectionEvent = {
  id: string;
  kind: string;
  from_status: string | null;
  to_status: string | null;
  note: string | null;
  occurred_at: string;
};

export type InspectionRequest = {
  id: string;
  status: string;
  delivery_kind: string | null;
  package_document_id: string | null;
  package_sha256: string | null;
  package_created_at: string | null;
  events: InspectionEvent[];
};

/** Documents of the community offered for the package; only owner released ones are selectable. */
export type CandidateDocument = { id: string; filename: string; title: string; released: boolean; created_at: string };

const NEXT: Record<string, string[]> = {
  requested: ["released", "rejected"],
  released: ["provided", "rejected"],
  provided: ["retrieved", "closed"],
  retrieved: ["closed"],
  closed: [],
  rejected: [],
};
const DELIVERY = ["portal", "data_medium", "on_site"] as const;

/** Status steps, notes, package build and download of one inspection request (A61). */
export function InspectionPanel({ request, documents }: { request: InspectionRequest; documents: CandidateDocument[] }) {
  const t = useTranslations("HoaInspection");
  const router = useRouter();
  const [note, setNote] = useState("");
  const [delivery, setDelivery] = useState<string>(request.delivery_kind ?? "data_medium");
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [packageResult, setPackageResult] = useState<{ sha256: string; entries: { file: string; sha256: string }[] } | null>(null);
  const base = `/api/bff/hoa/inspection-requests/${request.id}`;
  const canPackage = request.status === "released" || request.status === "provided";

  const run = async (path: string, body: unknown, after?: (data: never) => void) => {
    setBusy(true);
    setError(null);
    const res = await bff<never>(`${base}/${path}`, { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    after?.(res.data);
    router.refresh();
  };
  const transition = (status: string) =>
    run("transition", { status, note: note.trim() || null, delivery_kind: status === "provided" ? delivery : null }, () => setNote(""));
  const addNote = () => run("notes", { text: note.trim() }, () => setNote(""));
  const build = () => run("package", { document_ids: selected }, (data) => setPackageResult(data as { sha256: string; entries: { file: string; sha256: string }[] }));
  const toggle = (id: string) => setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  return (
    <div className="flex flex-col gap-4">
      <p className={ui.notice}>{t("notice")}</p>
      <section className={ui.card}>
        <h2 className={ui.h2}>{t("statusHeading")}</h2>
        <p className="text-sm">
          <span className={ui.badge} data-testid="inspection-status">
            {t(`status.${request.status}`)}
          </span>
          {request.delivery_kind ? <span className="ml-2 text-muted">{t(`delivery.${request.delivery_kind}`)}</span> : null}
        </p>
        <label className="mt-2 flex flex-col gap-1">
          <span className={ui.label}>{t("note")}</span>
          <textarea className={ui.input} rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        {NEXT[request.status]?.includes("provided") ? (
          <label className="mt-2 flex flex-col gap-1">
            <span className={ui.label}>{t("deliveryKind")}</span>
            <select className={ui.input} value={delivery} onChange={(e) => setDelivery(e.target.value)}>
              {DELIVERY.map((d) => (
                <option key={d} value={d}>
                  {t(`delivery.${d}`)}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <div className="mt-2 flex flex-wrap gap-2">
          <button type="button" className={ui.buttonSm} onClick={addNote} disabled={busy || note.trim().length === 0}>
            {t("addNote")}
          </button>
          {(NEXT[request.status] ?? []).map((next) => (
            <button
              key={next}
              type="button"
              className={next === "rejected" ? ui.danger : ui.button}
              onClick={() => transition(next)}
              disabled={busy || (next === "rejected" && note.trim().length === 0)}
            >
              {t(`action.${next}`)}
            </button>
          ))}
        </div>
      </section>
      <section className={ui.card}>
        <h2 className={ui.h2}>{t("packageHeading")}</h2>
        <p className={ui.help}>{t("packageHelp")}</p>
        <ul className="mt-2 flex flex-col gap-1 text-sm">
          {documents.map((d) => (
            <li key={d.id}>
              <label className="flex items-center gap-2">
                <input type="checkbox" disabled={!d.released || !canPackage} checked={selected.includes(d.id)} onChange={() => toggle(d.id)} />
                <span>{d.filename}</span>
                <span className="text-muted">{formatDate(d.created_at)}</span>
                {!d.released ? <span className={ui.badgeWarning}>{t("notReleased")}</span> : null}
              </label>
            </li>
          ))}
          {documents.length === 0 ? <li className="text-muted">{t("noDocuments")}</li> : null}
        </ul>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <button type="button" className={ui.button} onClick={build} disabled={busy || !canPackage || selected.length === 0}>
            {t("buildPackage")}
          </button>
          {request.package_document_id ? (
            <a className={ui.secondary} href={`${base}/package`} data-testid="package-download">
              {t("download")}
            </a>
          ) : null}
        </div>
        {request.package_sha256 ? (
          <p className="mt-2 break-all font-mono text-xs text-muted" data-testid="package-sha">
            {t("packageOf", { date: formatDateTime(request.package_created_at) })} SHA-256 {request.package_sha256}
          </p>
        ) : null}
        {packageResult ? (
          <ul className="mt-2 break-all font-mono text-xs" data-testid="package-entries">
            {packageResult.entries.map((e) => (
              <li key={e.file}>
                {e.file} {e.sha256}
              </li>
            ))}
          </ul>
        ) : null}
      </section>
      <section className={ui.card}>
        <h2 className={ui.h2}>{t("trail")}</h2>
        <ul className="flex flex-col gap-1 text-sm" data-testid="inspection-trail">
          {request.events.map((e) => (
            <li key={e.id}>
              <span className="text-muted">{formatDateTime(e.occurred_at)}</span> · {t(`kind.${e.kind}`)}
              {e.to_status ? ` · ${t(`status.${e.to_status}`)}` : ""}
              {e.note ? ` · ${e.note}` : ""}
            </li>
          ))}
        </ul>
      </section>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </div>
  );
}

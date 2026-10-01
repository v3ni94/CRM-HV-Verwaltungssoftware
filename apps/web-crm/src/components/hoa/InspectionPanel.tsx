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
  package_expires_at?: string | null;
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
  const [saved, setSaved] = useState(false);
  const [validDays, setValidDays] = useState("");
  const [revokeReason, setRevokeReason] = useState("");
  const [ownerCheck, setOwnerCheck] = useState<{ ownership_changed: boolean; package_active: boolean; recommendation: string } | null>(null);
  const [packageResult, setPackageResult] = useState<{ sha256: string; entries: { file: string; sha256: string }[] } | null>(null);
  const base = `/api/bff/hoa/inspection-requests/${request.id}`;
  const canPackage = request.status === "released" || request.status === "provided";

  const run = async (path: string, body: unknown, after?: (data: never) => void) => {
    setBusy(true);
    setError(null);
    setSaved(false);
    const res = await bff<never>(`${base}/${path}`, { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    after?.(res.data);
    setSaved(true);
    router.refresh();
  };
  const transition = (status: string) =>
    run("transition", { status, note: note.trim() || null, delivery_kind: status === "provided" ? delivery : null }, () => setNote(""));
  const addNote = () => run("notes", { text: note.trim() }, () => setNote(""));
  const days = Number(validDays);
  const expired = request.package_expires_at ? new Date(request.package_expires_at).getTime() <= Date.now() : false;
  const revoke = () => {
    if (!window.confirm(t("revokeConfirm"))) return;
    void run("revoke", { text: revokeReason.trim() }, () => setRevokeReason(""));
  };
  const checkOwner = () => run("owner-check", {}, (data) => setOwnerCheck(data as { ownership_changed: boolean; package_active: boolean; recommendation: string }));
  const build = () =>
    run("package", { document_ids: selected, ...(Number.isInteger(days) && days > 0 ? { valid_days: days } : {}) }, (data) => setPackageResult(data as { sha256: string; entries: { file: string; sha256: string }[] }));
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
        <label className="mt-2 flex max-w-xs flex-col gap-1">
          <span className={ui.label}>{t("validDays")}</span>
          <input className={ui.input} type="number" min={1} max={365} value={validDays} onChange={(e) => setValidDays(e.target.value)} data-testid="valid-days" />
          <span className={ui.help}>{t("validDaysHelp")}</span>
        </label>
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
        {request.package_document_id ? (
          <p className="mt-2 text-sm" data-testid="package-expiry">
            {request.package_expires_at
              ? expired
                ? t("expired", { date: formatDateTime(request.package_expires_at) })
                : t("expiresAt", { date: formatDateTime(request.package_expires_at) })
              : t("noExpiry")}
          </p>
        ) : null}
        {request.package_document_id && !expired ? (
          <div className="mt-2 flex flex-wrap items-end gap-2">
            <label className="flex flex-1 flex-col gap-1">
              <span className={ui.label}>{t("revokeReason")}</span>
              <input className={ui.input} value={revokeReason} onChange={(e) => setRevokeReason(e.target.value)} data-testid="revoke-reason" />
            </label>
            <button type="button" className={ui.danger} onClick={revoke} disabled={busy || revokeReason.trim().length === 0} data-testid="revoke-package">
              {t("revoke")}
            </button>
          </div>
        ) : null}
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
        <h2 className={ui.h2}>{t("ownerCheckHeading")}</h2>
        <p className={ui.help}>{t("ownerCheckHelp")}</p>
        <div className="mt-2">
          <button type="button" className={ui.buttonSm} onClick={checkOwner} disabled={busy} data-testid="owner-check">
            {t("ownerCheck")}
          </button>
        </div>
        {ownerCheck ? (
          <p className={ownerCheck.ownership_changed ? ui.notice : "mt-2 text-sm"} data-testid="owner-check-result">
            {ownerCheck.recommendation}
          </p>
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
      {saved ? (
        <p role="status" className={ui.success}>
          {t("saved")}
        </p>
      ) : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </div>
  );
}

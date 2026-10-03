"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

type ConsentItem = {
  kind: string;
  active: number;
  revoked: number;
  objections: number;
  without_proof: number;
  contacts_active: number;
};
type Deadlines = {
  access_days: number | null;
  erasure_days: number | null;
  warn_days: number | null;
  note: string | null;
  configured: boolean;
};
type DeadlineItem = {
  kind: "erasure" | "access";
  request_id: string;
  contact_id: string;
  status: string;
  received_on: string;
  warn_on: string | null;
  due_on: string | null;
  state: "unconfigured" | "ok" | "warn" | "overdue";
};
type Readiness = {
  complete: boolean;
  active_services: number;
  items: { key: string | null; name: string; entry_id: string | null; issues: string[] }[];
  note: string;
};

function num(v: string): number | null {
  const n = Number.parseInt(v, 10);
  return Number.isFinite(n) ? n : null;
}

/**
 * Datenschutzübersicht (Welle 21, AJ13): Einwilligungen je Zweck (GAI-508), Fristen für
 * Datenschutzanträge ohne Standardwert mit Überwachung (GAI-507) und die Vor-G1-Auswertung des
 * Verzeichnisses (GAI-510). Die Auswertung öffnet kein Gate; Fristen sind zu prüfen.
 */
export function PrivacyOversight({ canApprove }: { canApprove: boolean }) {
  const t = useTranslations("PrivacyOversight");
  const [consents, setConsents] = useState<ConsentItem[] | null>(null);
  const [deadlines, setDeadlines] = useState<Deadlines | null>(null);
  const [items, setItems] = useState<DeadlineItem[]>([]);
  const [ready, setReady] = useState<Readiness | null>(null);
  const [form, setForm] = useState({ access: "", erasure: "", warn: "" });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [c, m, r] = await Promise.all([
      bff<{ items: ConsentItem[] }>("/api/bff/privacy/consent-overview"),
      bff<{ settings: Deadlines; items: DeadlineItem[] }>("/api/bff/privacy/request-deadlines/monitor"),
      bff<Readiness>("/api/bff/privacy/register/readiness"),
    ]);
    if (c.ok) setConsents(c.data.items);
    if (m.ok) {
      setDeadlines(m.data.settings);
      setItems(m.data.items);
      setForm({
        access: m.data.settings.access_days?.toString() ?? "",
        erasure: m.data.settings.erasure_days?.toString() ?? "",
        warn: m.data.settings.warn_days?.toString() ?? "",
      });
    }
    if (r.ok) setReady(r.data);
    const failed = [c, m, r].find((x) => !x.ok);
    setError(failed && !failed.ok ? failed.message : null);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function save() {
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<Deadlines>("/api/bff/privacy/request-deadlines", {
      method: "PUT",
      body: JSON.stringify({ access_days: num(form.access), erasure_days: num(form.erasure), warn_days: num(form.warn) }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setMessage(t("deadlines.saved"));
    await load();
  }

  return (
    <section className={`${ui.card} flex flex-col gap-4`} aria-labelledby="privacy-oversight-title">
      <h2 id="privacy-oversight-title" className="text-base font-semibold">
        {t("title")}
      </h2>

      <div>
        <h3 className="mb-1 text-sm font-semibold">{t("consents.title")}</h3>
        <p className="mb-2 text-xs">{t("consents.hint")}</p>
        {consents ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left">
                  <th scope="col">{t("consents.kind")}</th>
                  <th scope="col">{t("consents.active")}</th>
                  <th scope="col">{t("consents.revoked")}</th>
                  <th scope="col">{t("consents.objections")}</th>
                  <th scope="col">{t("consents.withoutProof")}</th>
                  <th scope="col">{t("consents.contacts")}</th>
                </tr>
              </thead>
              <tbody>
                {consents.map((c) => (
                  <tr key={c.kind}>
                    <td>{t(`kinds.${c.kind}`)}</td>
                    <td>{c.active}</td>
                    <td>{c.revoked}</td>
                    <td>{c.objections}</td>
                    <td>{c.without_proof}</td>
                    <td>{c.contacts_active}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm">{t("loading")}</p>
        )}
      </div>

      <div>
        <h3 className="mb-1 text-sm font-semibold">{t("deadlines.title")}</h3>
        <p className="mb-2 text-xs">{t("deadlines.hint")}</p>
        <div className="flex flex-wrap gap-3">
          {(["access", "erasure", "warn"] as const).map((k) => (
            <div key={k} className="w-40">
              <label className={ui.label} htmlFor={`privacy-deadline-${k}`}>
                {t(`deadlines.${k}`)}
              </label>
              <input
                id={`privacy-deadline-${k}`}
                type="number"
                min={k === "warn" ? 0 : 1}
                className={ui.input}
                value={form[k]}
                disabled={!canApprove || busy}
                onChange={(e) => setForm((prev) => ({ ...prev, [k]: e.target.value }))}
              />
            </div>
          ))}
        </div>
        {canApprove ? (
          <button type="button" className={`${ui.primary} mt-2`} disabled={busy} onClick={() => void save()}>
            {t("deadlines.save")}
          </button>
        ) : null}
        {deadlines && !deadlines.configured ? <p className="mt-2 text-sm">{t("deadlines.unconfigured")}</p> : null}
        {items.length === 0 ? (
          <p className="mt-2 text-sm">{t("deadlines.empty")}</p>
        ) : (
          <ul className="mt-2 flex flex-col gap-1 text-sm">
            {items.map((i) => (
              <li key={i.request_id}>
                {t(i.kind === "access" ? "deadlines.itemAccess" : "deadlines.item", {
                  received: formatDate(i.received_on),
                  warn: formatDate(i.warn_on),
                  due: formatDate(i.due_on),
                })}{" "}
                <span className={i.state === "overdue" ? "font-semibold text-red-700" : ""}>{t(`states.${i.state}`)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <h3 className="mb-1 text-sm font-semibold">{t("readiness.title")}</h3>
        {ready ? (
          <>
            <p className="mb-2 text-xs">{ready.note}</p>
            <p className="text-sm">
              {ready.complete ? t("readiness.complete", { n: ready.active_services }) : t("readiness.open", { n: ready.items.length })}
            </p>
            <ul className="mt-1 flex flex-col gap-1 text-sm">
              {ready.items.map((i) => (
                <li key={`${i.key ?? ""}${i.entry_id ?? ""}${i.name}`}>
                  <span className="font-medium">{i.name}</span>: {i.issues.join(", ")}
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="text-sm">{t("loading")}</p>
        )}
      </div>
      {message ? <p role="status" className={ui.success}>{message}</p> : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </section>
  );
}

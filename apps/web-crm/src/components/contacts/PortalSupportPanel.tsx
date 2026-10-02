"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

type Account = { id: string; status: string };
type SupportView = {
  read_only: boolean;
  note: string;
  consent_expires_at: string | null;
  roles: string[];
  contracts: { id: string; kind: string; number: string | null }[];
  tickets: { id: string; number: number; title: string; status: string }[];
  documents: { id: string; title: string | null }[];
};
type LogRow = { id: string; staff_user_id: string | null; reason: string; areas: string; created_at: string };

/** Support view per portal access (GAF-22, section 14): read only extract of what the person
 *  sees in the portal. The API needs the tenant switch and a valid consent of the user and writes
 *  a log row per call, so a reason (5 to 500 characters) is mandatory. Nothing can be changed
 *  here. The protocol of earlier calls is loaded on demand. Needs tenant_settings:update. */
export function PortalSupportPanel({ contactId }: { contactId: string }) {
  const t = useTranslations("PortalSupport");
  const [account, setAccount] = useState<Account | null | undefined>(undefined);
  const [reason, setReason] = useState("");
  const [view, setView] = useState<SupportView | null>(null);
  const [log, setLog] = useState<LogRow[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    void bff<Account[]>(`/api/bff/portal-admin/accounts?contact_id=${encodeURIComponent(contactId)}`).then((res) => {
      if (alive) setAccount(res.ok ? (res.data?.[0] ?? null) : null);
    });
    return () => {
      alive = false;
    };
  }, [contactId]);

  const loadLog = useCallback(async (accountId: string) => {
    const res = await bff<LogRow[]>(`/api/bff/portal-admin/accounts/${accountId}/support-log`);
    if (res.ok) setLog(res.data ?? []);
    else setError(res.message);
  }, []);

  async function open() {
    if (!account) return;
    setError(null);
    if (reason.trim().length < 5) {
      setError(t("reasonRequired"));
      return;
    }
    setBusy(true);
    const res = await bff<SupportView>(
      `/api/bff/portal-admin/accounts/${account.id}/support-view?reason=${encodeURIComponent(reason.trim())}`,
    );
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setView(res.data);
    setReason("");
    if (log !== null) await loadLog(account.id);
  }

  if (!account) {
    return account === null ? (
      <p className="text-sm text-muted" data-testid="support-none">
        {t("noAccount")}
      </p>
    ) : null;
  }
  return (
    <section className={ui.card} data-testid="portal-support">
      <h2 className={ui.h2}>{t("title")}</h2>
      <p className="mt-1 text-xs text-subtle">{t("intro")}</p>
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <label className="flex min-w-60 flex-1 flex-col gap-1 text-sm">
          {t("reason")}
          <input className={ui.input} value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} />
        </label>
        <button type="button" className={ui.primary} disabled={busy} onClick={() => void open()}>
          {t("open")}
        </button>
        <button type="button" className={ui.secondary} onClick={() => void loadLog(account.id)}>
          {t("showLog")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={`${ui.alert} mt-2`}>
          {error}
        </p>
      ) : null}
      {view ? (
        <div className="mt-3 text-sm" data-testid="support-view">
          <p className={ui.notice}>{view.note}</p>
          <p className="mt-2">
            {t("roles")}: {view.roles.length ? view.roles.join(", ") : t("none")}
          </p>
          <h3 className="mt-2 font-medium">{t("contracts")}</h3>
          <ul className="list-disc pl-5">
            {view.contracts.map((c) => (
              <li key={c.id}>
                {c.kind} {c.number ?? ""}
              </li>
            ))}
          </ul>
          <h3 className="mt-2 font-medium">{t("tickets")}</h3>
          <ul className="list-disc pl-5">
            {view.tickets.map((x) => (
              <li key={x.id}>
                #{x.number} {x.title} ({x.status})
              </li>
            ))}
          </ul>
          <h3 className="mt-2 font-medium">{t("documents")}</h3>
          <ul className="list-disc pl-5">
            {view.documents.map((d) => (
              <li key={d.id}>{d.title}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {log ? (
        <div className="mt-3" data-testid="support-log">
          <h3 className="text-sm font-medium">{t("log")}</h3>
          {log.length === 0 ? (
            <p className="text-sm text-muted">{t("logEmpty")}</p>
          ) : (
            <ul className="text-sm">
              {log.map((r) => (
                <li key={r.id}>
                  {formatDateTime(r.created_at)}: {r.reason}
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </section>
  );
}

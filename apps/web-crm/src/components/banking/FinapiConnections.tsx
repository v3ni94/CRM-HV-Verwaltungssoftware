"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime, formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";

export type FinapiConnection = {
  id: string;
  bank_name: string;
  status: string;
  error_message: string | null;
};

/** Internes Konto (property_bank_account) als Zuordnungsziel. */
export type InternalAccountOption = { id: string; label: string };

export type AccountLink = {
  id: string;
  provider_account_id: string;
  property_bank_account_id: string | null;
  holder_name: string | null;
  iban_suffix: string | null;
  label: string | null;
  account_type: string | null;
  currency: string;
  usage: string;
  is_selected: boolean;
  last_attempt_at: string | null;
  last_bank_success_at: string | null;
  last_imported_at: string | null;
  last_error: string | null;
  balance: string | null;
  balance_bank_reference_at: string | null;
};

export type FetchRun = {
  id: string;
  connection_id: string | null;
  fetch_status: string | null;
  webform_url: string | null;
};

const USAGES = ["current", "reserve", "deposit", "other"] as const;

export function FinapiConnections({
  configured,
  connections,
  awaitingRuns,
  accountOptions,
}: {
  configured: boolean;
  connections: FinapiConnection[];
  awaitingRuns: FetchRun[];
  accountOptions: InternalAccountOption[];
}) {
  const t = useTranslations("BankFinapi");
  const router = useRouter();
  const [bankName, setBankName] = useState("");
  const [authContext, setAuthContext] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [accounts, setAccounts] = useState<Record<string, AccountLink[]>>({});

  const run = async (work: () => Promise<string | null>) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    const message = await work();
    setBusy(false);
    if (message) setNotice(message);
    router.refresh();
  };

  const connect = () =>
    run(async () => {
      const result = await bff<{ connection_id: string; webform_url: string | null }>(
        "/api/bff/banking/finapi/connections",
        {
          method: "POST",
          body: JSON.stringify({ bank_name: bankName, authorization_context: authContext }),
        },
      );
      if (!result.ok) {
        setError(result.message);
        return null;
      }
      setBankName("");
      setAuthContext("");
      if (result.data.webform_url) window.open(result.data.webform_url, "_blank", "noopener");
      return t("webformOpened");
    });

  const confirm = (id: string) =>
    run(async () => {
      const result = await bff<{ status: string; accounts: number }>(
        `/api/bff/banking/finapi/connections/${id}/confirm`,
        { method: "POST" },
      );
      if (!result.ok) {
        setError(result.message);
        return null;
      }
      if (result.data.status === "succeeded") {
        await loadAccounts(id);
        return t("confirmDone", { count: result.data.accounts });
      }
      return t(`confirmState.${result.data.status}` as Parameters<typeof t>[0]);
    });

  const loadAccounts = async (id: string) => {
    const result = await bff<AccountLink[]>(`/api/bff/banking/finapi/connections/${id}/accounts`);
    if (result.ok) setAccounts((prev) => ({ ...prev, [id]: result.data }));
    else setError(result.message);
  };

  const patchLink = (connectionId: string, linkId: string, patch: Partial<AccountLink>) =>
    setAccounts((prev) => ({
      ...prev,
      [connectionId]: (prev[connectionId] ?? []).map((link) =>
        link.id === linkId ? { ...link, ...patch } : link,
      ),
    }));

  const saveAccounts = (id: string) =>
    run(async () => {
      const rows = accounts[id] ?? [];
      const result = await bff<AccountLink[]>(`/api/bff/banking/finapi/connections/${id}/accounts`, {
        method: "PUT",
        body: JSON.stringify({
          accounts: rows.map((link) => ({
            link_id: link.id,
            selected: link.is_selected,
            property_bank_account_id: link.property_bank_account_id,
            usage: link.usage,
          })),
        }),
      });
      if (!result.ok) {
        setError(result.message);
        return null;
      }
      await loadAccounts(id);
      return t("assignmentSaved");
    });

  const fetchNow = (ids: string[]) =>
    run(async () => {
      const result = await bff<FetchRun[]>("/api/bff/banking/finapi/fetch", {
        method: "POST",
        body: JSON.stringify({ connection_ids: ids }),
      });
      if (!result.ok) {
        setError(result.message);
        return null;
      }
      const waiting = result.data.find((r) => r.fetch_status === "awaiting_authorization");
      if (waiting?.webform_url) {
        window.open(waiting.webform_url, "_blank", "noopener");
        return t("authorizationNeeded");
      }
      await Promise.all(ids.map((id) => loadAccounts(id)));
      return t("fetchDone");
    });

  const resume = (runId: string) =>
    run(async () => {
      const result = await bff<FetchRun>(`/api/bff/banking/finapi/runs/${runId}/resume`, {
        method: "POST",
      });
      if (!result.ok) {
        setError(result.message);
        return null;
      }
      if (result.data.fetch_status === "awaiting_authorization") return t("stillWaiting");
      return t("resumeDone");
    });

  const disconnect = (id: string) => {
    if (!window.confirm(t("disconnectConfirm"))) return;
    void run(async () => {
      const result = await bff<{ status: string; external_error: string | null }>(
        `/api/bff/banking/finapi/connections/${id}`,
        { method: "DELETE" },
      );
      if (!result.ok) {
        setError(result.message);
        return null;
      }
      return result.data.external_error
        ? t("disconnectedWithError", { error: result.data.external_error })
        : t("disconnected");
    });
  };

  if (!configured) return <p className={ui.notice}>{t("notConfigured")}</p>;

  return (
    <div className="flex flex-col gap-4">
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {notice ? <p className={ui.success}>{notice}</p> : null}

      {awaitingRuns.length > 0 ? (
        <div className={ui.notice}>
          <p className="font-medium text-fg">{t("awaitingTitle")}</p>
          <ul className="mt-1 flex flex-col gap-1">
            {awaitingRuns.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center gap-2">
                <span>{t("awaitingHint")}</span>
                {r.webform_url ? (
                  <a
                    href={r.webform_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-medium underline"
                  >
                    {t("openWebform")}
                  </a>
                ) : null}
                <button
                  type="button"
                  className={ui.buttonSm}
                  disabled={busy}
                  onClick={() => resume(r.id)}
                >
                  {t("resume")}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <section className={ui.card}>
        <h2 className={ui.h2}>{t("connectTitle")}</h2>
        <p className={`${ui.help} mt-1`}>{t("connectHint")}</p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("bankName")}</span>
            <input
              className={ui.input}
              value={bankName}
              onChange={(e) => setBankName(e.target.value)}
              maxLength={200}
            />
          </label>
          <label className="flex flex-col gap-1 sm:col-span-2">
            <span className={ui.label}>{t("authorizationContext")}</span>
            <textarea
              className={ui.input}
              value={authContext}
              onChange={(e) => setAuthContext(e.target.value)}
              rows={2}
              maxLength={2000}
              placeholder={t("authorizationPlaceholder")}
            />
            <span className={ui.help}>{t("authorizationHelp")}</span>
          </label>
        </div>
        <button
          type="button"
          className={`${ui.primary} mt-3`}
          disabled={busy || !bankName.trim() || authContext.trim().length < 5}
          onClick={connect}
        >
          {t("connect")}
        </button>
      </section>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className={ui.h2}>{t("connectionsTitle")}</h2>
        {connections.some((c) => c.status === "active") ? (
          <button
            type="button"
            className={ui.button}
            disabled={busy}
            onClick={() =>
              fetchNow(connections.filter((c) => c.status === "active").map((c) => c.id))
            }
          >
            {t("fetchAll")}
          </button>
        ) : null}
      </div>
      {connections.length === 0 ? (
        <p className="text-sm text-muted">{t("empty")}</p>
      ) : (
        connections.map((connection) => (
          <section key={connection.id} className={ui.card}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{connection.bank_name}</span>
              <span className={connection.status === "active" ? ui.badgeSuccess : ui.badge}>
                {t(`status.${connection.status}` as Parameters<typeof t>[0])}
              </span>
              <span className="ml-auto flex flex-wrap gap-2">
                {connection.status === "not_configured" ? (
                  <button
                    type="button"
                    className={ui.buttonSm}
                    disabled={busy}
                    onClick={() => confirm(connection.id)}
                  >
                    {t("confirm")}
                  </button>
                ) : null}
                {connection.status === "active" ? (
                  <button
                    type="button"
                    className={ui.buttonSm}
                    disabled={busy}
                    onClick={() => fetchNow([connection.id])}
                  >
                    {t("fetchOne")}
                  </button>
                ) : null}
                {accounts[connection.id] ? null : (
                  <button
                    type="button"
                    className={ui.buttonSm}
                    disabled={busy}
                    onClick={() => loadAccounts(connection.id)}
                  >
                    {t("showAccounts")}
                  </button>
                )}
                {connection.status !== "disabled" ? (
                  <button
                    type="button"
                    className={ui.buttonSm}
                    disabled={busy}
                    onClick={() => disconnect(connection.id)}
                  >
                    {t("disconnect")}
                  </button>
                ) : null}
              </span>
            </div>
            {connection.error_message ? (
              <p className={`${ui.alert} mt-2`}>{connection.error_message}</p>
            ) : null}
            {accounts[connection.id] ? (
              <AccountTable
                links={accounts[connection.id] ?? []}
                busy={busy}
                accountOptions={accountOptions}
                onPatch={(linkId, patch) => patchLink(connection.id, linkId, patch)}
                onSave={() => saveAccounts(connection.id)}
              />
            ) : null}
          </section>
        ))
      )}
    </div>
  );
}

function AccountTable({
  links,
  busy,
  accountOptions,
  onPatch,
  onSave,
}: {
  links: AccountLink[];
  busy: boolean;
  accountOptions: InternalAccountOption[];
  onPatch: (linkId: string, patch: Partial<AccountLink>) => void;
  onSave: () => void;
}) {
  const t = useTranslations("BankFinapi");
  return (
    <div className="mt-3 overflow-x-auto">
                <table className="w-full min-w-[900px] border-collapse text-sm">
                  <thead className="border-b border-border text-left text-xs text-muted">
                    <tr>
                      <th className="py-1.5 pr-3 font-medium">{t("colSelected")}</th>
                      <th className="py-1.5 pr-3 font-medium">{t("colAccount")}</th>
                      <th className="py-1.5 pr-3 font-medium">{t("colAssignment")}</th>
                      <th className="py-1.5 pr-3 font-medium">{t("colUsage")}</th>
                      <th className="py-1.5 pr-3 text-right font-medium">{t("colBalance")}</th>
                      <th className="py-1.5 font-medium">{t("colTimes")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {links.map((link) => (
                      <tr key={link.id} className="border-b border-border align-top">
                        <td className="py-1.5 pr-3">
                          <input
                            type="checkbox"
                            checked={link.is_selected}
                            aria-label={t("colSelected")}
                            onChange={(e) => onPatch(link.id, { is_selected: e.target.checked })}
                          />
                        </td>
                        <td className="py-1.5 pr-3">
                          <div className="font-medium">
                            {link.label ?? link.account_type ?? link.provider_account_id}
                          </div>
                          <div className="text-xs text-muted">
                            {link.holder_name}
                            {link.iban_suffix ? ` · IBAN …${link.iban_suffix}` : null}
                          </div>
                          {link.last_error ? (
                            <div className="text-xs text-danger-fg">{link.last_error}</div>
                          ) : null}
                        </td>
                        <td className="py-1.5 pr-3">
                          <select
                            className={ui.input}
                            value={link.property_bank_account_id ?? ""}
                            aria-label={t("colAssignment")}
                            onChange={(e) =>
                              onPatch(link.id, { property_bank_account_id: e.target.value || null })
                            }
                          >
                            <option value="">{t("unassigned")}</option>
                            {accountOptions.map((option) => (
                              <option key={option.id} value={option.id}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                          {!link.property_bank_account_id ? (
                            <p className={ui.help}>{t("unassignedHint")}</p>
                          ) : null}
                        </td>
                        <td className="py-1.5 pr-3">
                          <select
                            className={ui.input}
                            value={link.usage}
                            aria-label={t("colUsage")}
                            onChange={(e) => onPatch(link.id, { usage: e.target.value })}
                          >
                            {USAGES.map((usage) => (
                              <option key={usage} value={usage}>
                                {t(`usage.${usage}` as Parameters<typeof t>[0])}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td className="py-1.5 pr-3 text-right tabular-nums">
                          {link.balance != null ? formatEur(link.balance) : "–"}
                          <div className="text-xs text-muted">
                            {link.balance_bank_reference_at
                              ? formatDateTime(link.balance_bank_reference_at)
                              : t("noBankTime")}
                          </div>
                        </td>
                        <td className="py-1.5 text-xs text-muted">
                          <div>
                            {t("lastAttempt")}: {formatDateTime(link.last_attempt_at) || "–"}
                          </div>
                          <div>
                            {t("lastBankSuccess")}:{" "}
                            {formatDateTime(link.last_bank_success_at) || "–"}
                          </div>
                          <div>
                            {t("lastImported")}: {formatDateTime(link.last_imported_at) || "–"}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <button
                  type="button"
                  className={`${ui.primary} mt-3`}
                  disabled={busy}
                  onClick={onSave}
                >
                  {t("saveAssignment")}
                </button>
    </div>
  );
}

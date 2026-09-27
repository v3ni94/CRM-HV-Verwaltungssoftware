"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { StatusPill } from "@/components/ui/StatusPill";
import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { type ConnectionTest, type MeteringConnection, type MeteringProvider } from "@/lib/metering";
import { ui } from "@/lib/ui";

import { ConnectionWizard } from "./ConnectionWizard";

/** Central connection list (section 4): name, provider, environment, state, references,
 *  secret names (never values), last test with stale marker, capability summary; actions test,
 *  pause or activate, replace secrets. */
export function ConnectionsAdmin({
  initial,
  providers,
  canManage,
  loadFailed = false,
  onChange,
  onGoToAssignments,
}: {
  initial: MeteringConnection[];
  providers: MeteringProvider[];
  canManage: boolean;
  loadFailed?: boolean;
  onChange?: (connections: MeteringConnection[]) => void;
  onGoToAssignments?: (connection: MeteringConnection) => void;
}) {
  const t = useTranslations("Metering");
  const [connections, setConnections] = useState(initial);
  const [wizard, setWizard] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [secretsFor, setSecretsFor] = useState<string | null>(null);
  const [secretRows, setSecretRows] = useState<{ name: string; value: string }[]>([{ name: "", value: "" }]);
  const [testResult, setTestResult] = useState<Record<string, ConnectionTest>>({});

  function update(list: MeteringConnection[]) {
    setConnections(list);
    onChange?.(list);
  }
  function upsert(c: MeteringConnection) {
    update(connections.some((x) => x.id === c.id) ? connections.map((x) => (x.id === c.id ? c : x)) : [...connections, c]);
  }

  async function runTest(c: MeteringConnection) {
    setBusy(c.id);
    setError(null);
    const res = await bff<ConnectionTest>(`/api/bff/metering/connections/${c.id}/test`, { method: "POST" });
    setBusy(null);
    if (!res.ok) return setError(res.message);
    setTestResult((prev) => ({ ...prev, [c.id]: res.data }));
    upsert(res.data.connection);
  }

  async function toggleStatus(c: MeteringConnection) {
    setBusy(c.id);
    setError(null);
    const res = await bff<MeteringConnection>(`/api/bff/metering/connections/${c.id}`, {
      method: "PATCH",
      body: JSON.stringify({ version: c.version, status: c.status === "active" ? "paused" : "active" }),
    });
    setBusy(null);
    if (!res.ok) return setError(res.message);
    upsert(res.data);
  }

  async function toggleWrite(c: MeteringConnection) {
    setBusy(c.id);
    setError(null);
    const res = await bff<MeteringConnection>(`/api/bff/metering/connections/${c.id}`, {
      method: "PATCH",
      body: JSON.stringify({ version: c.version, write_sync_enabled: !c.write_sync_enabled }),
    });
    setBusy(null);
    if (!res.ok) return setError(res.message);
    upsert(res.data);
  }

  async function saveSecrets(c: MeteringConnection) {
    const secrets = Object.fromEntries(secretRows.filter((r) => r.name.trim()).map((r) => [r.name.trim(), r.value]));
    setBusy(c.id);
    setError(null);
    const res = await bff<MeteringConnection>(`/api/bff/metering/connections/${c.id}/secrets`, {
      method: "PUT",
      body: JSON.stringify({ secrets }),
    });
    setBusy(null);
    if (!res.ok) return setError(res.message);
    upsert(res.data);
    setSecretsFor(null);
    setSecretRows([{ name: "", value: "" }]);
  }

  const providerName = (code: string) => providers.find((p) => p.code === code)?.name ?? code;

  return (
    <div className="flex flex-col gap-4" data-testid="metering-connections">
      {loadFailed ? (
        <p role="alert" className={ui.alert}>
          {t("loadError")}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {!canManage ? <p className={ui.notice}>{t("readOnlyHint")}</p> : null}
      {canManage && !wizard ? (
        <div>
          <button type="button" className={ui.primary} onClick={() => setWizard(true)}>
            {t("connection.new")}
          </button>
        </div>
      ) : null}
      {wizard ? (
        <ConnectionWizard
          providers={providers}
          onDone={upsert}
          onCancel={() => setWizard(false)}
          onGoToAssignments={(c) => {
            setWizard(false);
            onGoToAssignments?.(c);
          }}
        />
      ) : null}

      {connections.length === 0 ? (
        <p className="text-sm text-muted">{t("connection.none")}</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {connections.map((c) => {
            const result = testResult[c.id];
            return (
              <li key={c.id} className={ui.card} data-testid={`metering-connection-${c.id}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{c.display_name}</span>
                  <span className={ui.badge}>{providerName(c.provider_code)}</span>
                  <span className={c.environment === "production" ? ui.badgeGold : ui.badge}>{t(`environment.${c.environment}`)}</span>
                  <StatusPill variant={c.status === "active" ? "success" : "neutral"} label={t(`connectionStatus.${c.status}`)} />
                </div>
                <dl className="mt-2 grid gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
                  <dt className="text-muted">{t("connection.references")}</dt>
                  <dd>{c.customer_references.length ? c.customer_references.join(", ") : t("none")}</dd>
                  <dt className="text-muted">{t("connection.secrets")}</dt>
                  <dd>{c.secret_names.length ? c.secret_names.join(", ") : t("none")}</dd>
                  <dt className="text-muted">{t("connection.lastTest")}</dt>
                  <dd>
                    {c.last_test_status ? (
                      <>
                        <StatusPill
                          variant={c.last_test_status === "success" ? "success" : c.last_test_status === "failed" ? "danger" : "warning"}
                          label={t(`testOutcome.${c.last_test_status}`)}
                        />{" "}
                        {formatDateTime(c.last_test_at)}
                        {c.test_stale ? <span className={`${ui.badgeWarning} ml-2`}>{t("connection.testStale")}</span> : null}
                      </>
                    ) : (
                      t("connection.notTested")
                    )}
                  </dd>
                  <dt className="text-muted">{t("connection.functions")}</dt>
                  <dd className="flex flex-wrap gap-1">
                    {c.capabilities.map((cap) => (
                      <span key={cap.function} className={cap.available ? ui.badgeSuccess : ui.badge} title={cap.reason ?? undefined}>
                        {t(`functions.${cap.function}`)}
                      </span>
                    ))}
                  </dd>
                </dl>
                {result ? (
                  <p className={`${ui.notice} mt-2 text-xs`}>
                    {t(`testOutcome.${result.outcome}`)}: {result.detail}
                  </p>
                ) : null}
                {canManage ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button type="button" className={ui.buttonSm} disabled={busy === c.id} onClick={() => runTest(c)}>
                      {t("connection.test")}
                    </button>
                    <button type="button" className={ui.buttonSm} disabled={busy === c.id} onClick={() => toggleStatus(c)}>
                      {c.status === "active" ? t("connection.pause") : t("connection.activate")}
                    </button>
                    <button type="button" className={ui.buttonSm} disabled={busy === c.id} onClick={() => toggleWrite(c)} title={t("connection.writeHint")}>
                      {c.write_sync_enabled ? t("connection.writeLock") : t("connection.writeRelease")}
                    </button>
                    <button type="button" className={ui.buttonSm} onClick={() => setSecretsFor(secretsFor === c.id ? null : c.id)}>
                      {t("connection.replaceSecrets")}
                    </button>
                    {onGoToAssignments ? (
                      <button type="button" className={ui.buttonSm} onClick={() => onGoToAssignments(c)}>
                        {t("wizard.toAssignments")}
                      </button>
                    ) : null}
                  </div>
                ) : null}
                {secretsFor === c.id ? (
                  <div className="mt-3 flex flex-col gap-2">
                    <p className={ui.help}>{t("connection.secretsHint")}</p>
                    {secretRows.map((row, i) => (
                      <div key={i} className="grid gap-2 sm:grid-cols-2">
                        <input
                          className={ui.input}
                          aria-label={t("connection.secretName")}
                          placeholder={t("connection.secretName")}
                          value={row.name}
                          onChange={(e) => setSecretRows((rows) => rows.map((r, j) => (j === i ? { ...r, name: e.target.value } : r)))}
                        />
                        <input
                          className={ui.input}
                          type="password"
                          autoComplete="off"
                          aria-label={t("connection.secretValue")}
                          placeholder={t("connection.secretValue")}
                          value={row.value}
                          onChange={(e) => setSecretRows((rows) => rows.map((r, j) => (j === i ? { ...r, value: e.target.value } : r)))}
                        />
                      </div>
                    ))}
                    <div className="flex flex-wrap gap-2">
                      <button type="button" className={ui.buttonSm} onClick={() => setSecretRows((rows) => [...rows, { name: "", value: "" }])}>
                        {t("connection.addSecret")}
                      </button>
                      <button type="button" className={ui.primary} disabled={busy === c.id} onClick={() => saveSecrets(c)}>
                        {t("save")}
                      </button>
                      <button type="button" className={ui.button} onClick={() => setSecretsFor(null)}>
                        {t("cancel")}
                      </button>
                    </div>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

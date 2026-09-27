"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { StatusPill } from "@/components/ui/StatusPill";
import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { type ConnectionTest, type MeteringConnection, type MeteringProvider } from "@/lib/metering";
import { ui } from "@/lib/ui";

/** Setup wizard (section 4): provider (with the honest documented state per function), name
 *  and environment, references, secrets (set only, never shown again), read only connection
 *  test with result and stale marker, released functions, jump to the assignment. */
type Step = "provider" | "details" | "secrets" | "test" | "done";

const STEPS: Step[] = ["provider", "details", "secrets", "test", "done"];

export function supportVariant(support: string): "success" | "warning" | "danger" | "neutral" {
  if (support === "yes") return "success";
  if (support === "documentation_required") return "warning";
  if (support === "no") return "danger";
  return "neutral";
}

export function ConnectionWizard({
  providers,
  onDone,
  onCancel,
  onGoToAssignments,
}: {
  providers: MeteringProvider[];
  onDone: (connection: MeteringConnection) => void;
  onCancel: () => void;
  onGoToAssignments?: (connection: MeteringConnection) => void;
}) {
  const t = useTranslations("Metering");
  const [step, setStep] = useState<Step>("provider");
  const [providerCode, setProviderCode] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [environment, setEnvironment] = useState<"test" | "production">("test");
  const [references, setReferences] = useState("");
  const [company, setCompany] = useState("");
  const [secretRows, setSecretRows] = useState<{ name: string; value: string }[]>([{ name: "", value: "" }]);
  const [connection, setConnection] = useState<MeteringConnection | null>(null);
  const [test, setTest] = useState<ConnectionTest | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const provider = providers.find((p) => p.code === providerCode);

  async function create() {
    setBusy(true);
    setError(null);
    const secrets = Object.fromEntries(secretRows.filter((r) => r.name.trim() && r.value).map((r) => [r.name.trim(), r.value]));
    const res = await bff<MeteringConnection>("/api/bff/metering/connections", {
      method: "POST",
      body: JSON.stringify({
        display_name: displayName.trim(),
        provider_code: providerCode,
        environment,
        customer_references: references
          .split(/[\n,;]/)
          .map((s) => s.trim())
          .filter(Boolean),
        contracting_company: company.trim() || null,
        secrets: Object.keys(secrets).length ? secrets : null,
      }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setConnection(res.data);
    onDone(res.data);
    setStep("test");
  }

  async function runTest() {
    if (!connection) return;
    setBusy(true);
    setError(null);
    const res = await bff<ConnectionTest>(`/api/bff/metering/connections/${connection.id}/test`, { method: "POST" });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setTest(res.data);
    setConnection(res.data.connection);
    onDone(res.data.connection);
  }

  const current = connection ?? test?.connection ?? null;

  return (
    <section className={ui.card} data-testid="metering-connection-wizard" aria-label={t("wizard.title")}>
      <ol className="mb-4 flex flex-wrap gap-2 text-xs">
        {STEPS.map((s, i) => (
          <li key={s} className={s === step ? ui.badgeGold : ui.badge} aria-current={s === step ? "step" : undefined}>
            {i + 1}. {t(`wizard.steps.${s}`)}
          </li>
        ))}
      </ol>
      {error ? (
        <p role="alert" className={`${ui.alert} mb-3`}>
          {error}
        </p>
      ) : null}

      {step === "provider" ? (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-muted">{t("wizard.providerIntro")}</p>
          <div className="grid gap-2 md:grid-cols-2">
            {providers.map((p) => (
              <label key={p.code} className={`${ui.card} cursor-pointer ${p.code === providerCode ? "border-gold" : ""}`}>
                <span className="flex items-center gap-2">
                  <input type="radio" name="provider" value={p.code} checked={p.code === providerCode} onChange={() => setProviderCode(p.code)} />
                  <span className="font-medium">{p.name}</span>
                  {p.manual_only ? <span className={ui.badgeWarning}>{t("wizard.manualOnly")}</span> : null}
                </span>
                <ul className="mt-2 flex flex-col gap-1 text-xs">
                  {p.functions.map((f) => (
                    <li key={f.function} className="flex flex-wrap items-center gap-2">
                      <span className="min-w-40">{t(`functions.${f.function}`)}</span>
                      <StatusPill variant={supportVariant(f.documented_support)} label={f.label} />
                      {f.adapter_implemented ? null : <span className="text-subtle">{t("wizard.noAdapter")}</span>}
                    </li>
                  ))}
                </ul>
              </label>
            ))}
          </div>
          {provider ? <p className={ui.help}>{provider.research_note}</p> : null}
          <div className={ui.formActions}>
            <button type="button" className={ui.primary} disabled={!providerCode} onClick={() => setStep("details")}>
              {t("wizard.next")}
            </button>
            <button type="button" className={ui.button} onClick={onCancel}>
              {t("cancel")}
            </button>
          </div>
        </div>
      ) : null}

      {step === "details" ? (
        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("connection.displayName")}</span>
            <input className={ui.input} value={displayName} onChange={(e) => setDisplayName(e.target.value)} maxLength={200} />
          </label>
          <fieldset className="flex flex-col gap-1">
            <legend className={ui.label}>{t("connection.environment")}</legend>
            <div className="flex gap-4 text-sm">
              {(["test", "production"] as const).map((env) => (
                <label key={env} className="flex items-center gap-1">
                  <input type="radio" name="environment" checked={environment === env} onChange={() => setEnvironment(env)} />
                  {t(`environment.${env}`)}
                </label>
              ))}
            </div>
            <p className={ui.help}>{t("wizard.environmentHint")}</p>
          </fieldset>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("connection.references")}</span>
            <textarea className={ui.input} rows={3} value={references} onChange={(e) => setReferences(e.target.value)} />
            <span className={ui.help}>{t("wizard.referencesHint")}</span>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("connection.contractingCompany")}</span>
            <input className={ui.input} value={company} onChange={(e) => setCompany(e.target.value)} maxLength={200} />
          </label>
          {provider ? <p className={ui.help}>{provider.auth_note}</p> : null}
          <div className={ui.formActions}>
            <button type="button" className={ui.button} onClick={() => setStep("provider")}>
              {t("wizard.back")}
            </button>
            <button type="button" className={ui.primary} disabled={!displayName.trim()} onClick={() => setStep("secrets")}>
              {t("wizard.next")}
            </button>
          </div>
        </div>
      ) : null}

      {step === "secrets" ? (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-muted">{t("wizard.secretsIntro")}</p>
          {secretRows.map((row, i) => (
            <div key={i} className="grid gap-2 sm:grid-cols-2">
              <input
                className={ui.input}
                placeholder={t("connection.secretName")}
                aria-label={t("connection.secretName")}
                value={row.name}
                onChange={(e) => setSecretRows((rows) => rows.map((r, j) => (j === i ? { ...r, name: e.target.value } : r)))}
              />
              <input
                className={ui.input}
                type="password"
                autoComplete="off"
                placeholder={t("connection.secretValue")}
                aria-label={t("connection.secretValue")}
                value={row.value}
                onChange={(e) => setSecretRows((rows) => rows.map((r, j) => (j === i ? { ...r, value: e.target.value } : r)))}
              />
            </div>
          ))}
          <button type="button" className={ui.buttonSm} onClick={() => setSecretRows((rows) => [...rows, { name: "", value: "" }])}>
            {t("connection.addSecret")}
          </button>
          <div className={ui.formActions}>
            <button type="button" className={ui.button} onClick={() => setStep("details")}>
              {t("wizard.back")}
            </button>
            <button type="button" className={ui.primary} disabled={busy} onClick={create}>
              {t("wizard.create")}
            </button>
          </div>
        </div>
      ) : null}

      {step === "test" && current ? (
        <div className="flex flex-col gap-3">
          <p className="text-sm">{t("wizard.created", { name: current.display_name })}</p>
          <p className="text-sm text-muted">{t("wizard.testIntro")}</p>
          <div className={ui.formActions}>
            <button type="button" className={ui.primary} disabled={busy} onClick={runTest} data-testid="metering-run-test">
              {t("connection.test")}
            </button>
            <button type="button" className={ui.button} onClick={() => setStep("done")}>
              {t("wizard.skipTest")}
            </button>
          </div>
          {test ? (
            <div className={ui.notice} data-testid="metering-test-result">
              <p>
                <StatusPill variant={test.outcome === "success" ? "success" : test.outcome === "failed" ? "danger" : "warning"} label={t(`testOutcome.${test.outcome}`)} />{" "}
                {test.detail}
              </p>
              <p className="mt-1 text-xs">
                {t("connection.lastTest")}: {formatDateTime(test.connection.last_test_at)}
                {test.connection.test_stale ? <span className={`${ui.badgeWarning} ml-2`}>{t("connection.testStale")}</span> : null}
              </p>
              <p className="mt-1 text-xs">
                {t("wizard.releasedFunctions")}:{" "}
                {test.functions_released.length ? test.functions_released.map((f) => t(`functions.${f}`)).join(", ") : t("none")}
              </p>
              <p className="mt-1 text-xs text-muted">{t("wizard.testNotAllObjects")}</p>
              <button type="button" className={`${ui.buttonSm} mt-2`} onClick={() => setStep("done")}>
                {t("wizard.next")}
              </button>
            </div>
          ) : null}
        </div>
      ) : null}

      {step === "done" && current ? (
        <div className="flex flex-col gap-3">
          <h3 className={ui.subtitle}>{t("wizard.releasedFunctions")}</h3>
          <ul className="flex flex-col gap-1 text-sm" data-testid="metering-capabilities">
            {current.capabilities.map((c) => (
              <li key={c.function} className="flex flex-wrap items-center gap-2">
                <span className="min-w-40">{t(`functions.${c.function}`)}</span>
                <StatusPill variant={c.available ? "success" : "neutral"} label={c.available ? t("capability.available") : t("capability.unavailable")} />
                {!c.available && c.reason ? <span className="text-xs text-muted">{c.reason}</span> : null}
              </li>
            ))}
          </ul>
          <div className={ui.formActions}>
            {onGoToAssignments ? (
              <button type="button" className={ui.primary} onClick={() => onGoToAssignments(current)}>
                {t("wizard.toAssignments")}
              </button>
            ) : null}
            <button type="button" className={ui.button} onClick={onCancel}>
              {t("close")}
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import type { DocumentOut, Provider, ProviderIn } from "@/lib/ai";
import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

const TIERS = ["small", "large", "embedding"] as const;
type Tier = (typeof TIERS)[number];
type TierForm = { model: string; input: string; output: string };

const DECIMAL = /^\d+([.,]\d{1,8})?$/;
const norm = (v: string) => v.trim().replace(",", ".");

function tierOf(models: Record<string, unknown>, tier: Tier): TierForm {
  const m = (models[tier] ?? {}) as Record<string, unknown>;
  const s = (v: unknown) => (v === undefined || v === null ? "" : String(v));
  return { model: s(m.model), input: s(m.input_eur_per_mtok), output: s(m.output_eur_per_mtok) };
}

/** Provider configuration (9.2): only the Anthropic adapter exists in the API so far. */
export function ProviderSettings({ provider: name, initial }: { provider: "anthropic" | "openai"; initial: Provider | null }) {
  const t = useTranslations("AiSettings");
  const [saved, setSaved] = useState<Provider | null>(initial);
  const [apiKey, setApiKey] = useState("");
  const [tiers, setTiers] = useState<Record<Tier, TierForm>>(() =>
    Object.fromEntries(TIERS.map((k) => [k, tierOf(initial?.models ?? {}, k)])) as Record<Tier, TierForm>,
  );
  const [budget, setBudget] = useState(initial?.monthly_budget_eur ?? "");
  const [dpa, setDpa] = useState(initial?.data_processing_agreement_signed ?? false);
  const [dpaDocument, setDpaDocument] = useState<string | null>(initial?.dpa_document_id ?? null);
  const [dpaName, setDpaName] = useState<string | null>(null);
  const [optOut, setOptOut] = useState(initial?.training_opt_out_confirmed ?? false);
  const [enabled, setEnabled] = useState(initial?.enabled ?? false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const setTier = (tier: Tier, key: keyof TierForm, value: string) =>
    setTiers((prev) => ({ ...prev, [tier]: { ...prev[tier], [key]: value } }));

  const validate = (): string | null => {
    if (!DECIMAL.test(norm(budget))) return t("budgetInvalid");
    for (const tier of TIERS) {
      const f = tiers[tier];
      const any = f.model || f.input || f.output;
      if (any && (!f.model.trim() || !DECIMAL.test(norm(f.input)) || !DECIMAL.test(norm(f.output)))) {
        return t("tierInvalid", { tier: t(`tier.${tier}`) });
      }
    }
    return null;
  };

  const uploadDpa = async (file: File) => {
    setError(null);
    const form = new FormData();
    form.set("file", file);
    form.set("title", t("dpaTitle"));
    const res = await bff<DocumentOut>("/api/bff/documents", { method: "POST", body: form });
    if (!res.ok) return setError(res.message);
    setDpaDocument(res.data.id);
    setDpaName(res.data.filename);
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage(null);
    const invalid = validate();
    if (invalid) return setError(invalid);
    setError(null);
    const models: ProviderIn["models"] = {};
    for (const tier of TIERS) {
      const f = tiers[tier];
      if (f.model.trim()) {
        models[tier] = { model: f.model.trim(), input_eur_per_mtok: norm(f.input), output_eur_per_mtok: norm(f.output) };
      }
    }
    const body: ProviderIn = {
      models,
      task_tiers: (saved?.task_tiers ?? {}) as ProviderIn["task_tiers"],
      monthly_budget_eur: norm(budget),
      data_processing_agreement_signed: dpa,
      dpa_document_id: dpaDocument,
      training_opt_out_confirmed: optOut,
      endpoint_region: saved?.endpoint_region ?? null,
      enabled,
      ...(apiKey ? { api_key: apiKey } : {}),
    };
    setBusy(true);
    const res = await bff<Provider>(`/api/bff/ai/providers/${name}`, { method: "PUT", body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setSaved(res.data);
    setApiKey("");
    setMessage(t("saved"));
  };

  const release = async () => {
    setError(null);
    setMessage(null);
    setBusy(true);
    const res = await bff<Provider>(`/api/bff/ai/providers/${name}/release`, { method: "POST" });
    setBusy(false);
    if (!res.ok) return setError(res.message);
    setSaved(res.data);
    setMessage(t("released"));
  };

  return (
    <form onSubmit={save} className={`${ui.card} flex flex-col gap-4`} aria-label={t("providerTitle", { provider: t(`provider.${name}`) })}>
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold">{t("providerTitle", { provider: t(`provider.${name}`) })}</h2>
        <span className="rounded border border-border px-1.5 py-0.5 text-xs" data-testid="release-state">
          {saved?.released_at ? t("releasedAt", { at: formatDateTime(saved.released_at) }) : t("notReleased")}
        </span>
      </div>

      <div>
        <label htmlFor="api-key" className={ui.label}>
          {t("apiKey")}
        </label>
        <input
          id="api-key"
          type="password"
          autoComplete="off"
          className={ui.input}
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder={saved?.has_api_key ? t("apiKeyStored") : t("apiKeyMissing")}
        />
        <p className="text-xs text-muted">{t("apiKeyHint")}</p>
      </div>

      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium">{t("models")}</legend>
        <p className="text-xs text-muted">{t("modelsHint")}</p>
        {TIERS.map((tier) => (
          <div key={tier} className="grid gap-2 sm:grid-cols-3">
            <div>
              <label htmlFor={`model-${tier}`} className={ui.label}>
                {t("modelFor", { tier: t(`tier.${tier}`) })}
              </label>
              <input id={`model-${tier}`} className={ui.input} value={tiers[tier].model} onChange={(e) => setTier(tier, "model", e.target.value)} />
            </div>
            <div>
              <label htmlFor={`in-${tier}`} className={ui.label}>
                {t("priceIn", { tier: t(`tier.${tier}`) })}
              </label>
              <input id={`in-${tier}`} inputMode="decimal" className={ui.input} value={tiers[tier].input} onChange={(e) => setTier(tier, "input", e.target.value)} />
            </div>
            <div>
              <label htmlFor={`out-${tier}`} className={ui.label}>
                {t("priceOut", { tier: t(`tier.${tier}`) })}
              </label>
              <input id={`out-${tier}`} inputMode="decimal" className={ui.input} value={tiers[tier].output} onChange={(e) => setTier(tier, "output", e.target.value)} />
            </div>
          </div>
        ))}
      </fieldset>

      <div className="max-w-xs">
        <label htmlFor="budget" className={ui.label}>
          {t("budget")}
        </label>
        <input id="budget" inputMode="decimal" className={ui.input} value={budget} onChange={(e) => setBudget(e.target.value)} />
      </div>

      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium">{t("dataProtection")}</legend>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={dpa} onChange={(e) => setDpa(e.target.checked)} />
          {t("dpaSigned")}
        </label>
        <div>
          <label htmlFor="dpa-file" className={ui.label}>
            {t("dpaDocument")}
          </label>
          <input
            id="dpa-file"
            type="file"
            accept="application/pdf"
            className="text-sm"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void uploadDpa(file);
            }}
          />
          <p className="text-xs text-muted">
            {dpaDocument ? t("dpaStored", { name: dpaName ?? dpaDocument.slice(0, 8) }) : t("dpaMissing")}
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={optOut} onChange={(e) => setOptOut(e.target.checked)} />
          {t("optOut")}
        </label>
        <p className="text-xs text-muted">{t("dataProtectionHint")}</p>
      </fieldset>

      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        {t("enabled")}
      </label>

      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {message ? (
        <p role="status" className={ui.notice}>
          {message}
        </p>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <button type="submit" className={ui.primary} disabled={busy}>
          {t("save")}
        </button>
        <button type="button" className={ui.button} onClick={release} disabled={busy || !saved || !!saved.released_at}>
          {t("release")}
        </button>
      </div>
      <p className="text-xs text-muted">{t("fourEyesHint")}</p>
    </form>
  );
}

"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Tenant = { id: string; name: string; slug: string };
type EntityKind = "manager" | "rental_owner" | "sev_owner";
type Entity = { kind: EntityKind; name: string };

type OnboardingResult = {
  tenant_id: string;
  name: string;
  legal_entities: { id: string; kind: string; name: string }[];
  admin: { email: string; existed: boolean; roles: string[] };
  feature_flags: Record<string, boolean>;
  gates: Record<string, boolean>;
  welcome_email: { to: string; subject: string; body: string; status: string };
};

type ExportRequest = {
  id: string;
  purpose: string;
  status: string;
  requested_by: string;
  decided_by: string | null;
  downloads: number;
  created_at: string;
  job_status?: "queued" | "running" | "ready" | "failed" | null;
  job_error?: string | null;
};

const SLUG = /^[a-z0-9][a-z0-9-]{1,62}$/;
const HEX = /^#[0-9a-fA-F]{6}$/;

/** M27-03: onboarding wizard for third party tenants (platform administrators). Feature flags
 *  stay off, no gate opens, the welcome mail is a draft that is never sent from here. */
export function OnboardingWizard() {
  const t = useTranslations("PlatformOnboarding");
  const [step, setStep] = useState(0);
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [city, setCity] = useState("");
  const [entities, setEntities] = useState<Entity[]>([{ kind: "manager", name: "" }]);
  const [adminEmail, setAdminEmail] = useState("");
  const [adminName, setAdminName] = useState("");
  const [adminPassword, setAdminPassword] = useState("");
  const [primary, setPrimary] = useState("");
  const [logoId, setLogoId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<OnboardingResult | null>(null);

  const steps = [t("stepTenant"), t("stepEntities"), t("stepAdmin"), t("stepCi"), t("stepSummary")];

  function validate(current: number): string | null {
    if (current === 0 && (!SLUG.test(slug) || name.trim().length < 2)) return t("slugInvalid");
    if (current === 1 && entities.some((e) => e.name.trim().length < 2)) return t("entityInvalid");
    if (current === 2 && (!adminEmail.includes("@") || adminName.trim().length < 2 || adminPassword.length < 12)) return t("adminInvalid");
    if (current === 3 && primary && !HEX.test(primary)) return t("colorInvalid");
    return null;
  }

  function next() {
    const problem = validate(step);
    if (problem) {
      setError(problem);
      return;
    }
    setError(null);
    setStep(Math.min(step + 1, steps.length - 1));
  }

  async function submit() {
    setBusy(true);
    setError(null);
    const branding: Record<string, string> = {};
    if (primary) branding.primary_color = primary;
    if (logoId) branding.logo_light_document_id = logoId;
    const res = await bff<OnboardingResult>("/api/bff/platform/onboarding", {
      method: "POST",
      body: JSON.stringify({
        slug,
        name,
        company: { name: companyName || name, city: city || null },
        branding,
        legal_entities: entities,
        admin: { email: adminEmail, display_name: adminName, password: adminPassword },
      }),
    });
    setBusy(false);
    if (res.ok) setResult(res.data);
    else setError(res.message);
  }

  if (result) {
    return (
      <section className={`${ui.card} flex flex-col gap-3`}>
        <h2 className={ui.h2}>{t("createdTitle", { name: result.name })}</h2>
        <p className={ui.success}>{t("createdHint")}</p>
        <ul className="text-sm">
          <li>{t("createdEntities", { count: result.legal_entities.length })}</li>
          <li>{t("createdAdmin", { email: result.admin.email })}</li>
          <li>
            {t("createdFlags")}: {Object.entries(result.feature_flags).map(([k, v]) => `${k} = ${v ? t("on") : t("off")}`).join(", ")}
          </li>
          <li>
            {t("createdGates")}: {Object.entries(result.gates).map(([g, open]) => `${g} ${open ? t("gateOpen") : t("gateClosed")}`).join(", ")}
          </li>
        </ul>
        <h3 className="text-sm font-semibold">{t("welcomeTitle")}</h3>
        <p className={ui.help}>{t("welcomeHint")}</p>
        <p className="text-sm">
          {t("welcomeTo")}: {result.welcome_email.to}
        </p>
        <p className="text-sm font-medium">{result.welcome_email.subject}</p>
        <pre className="whitespace-pre-wrap rounded-md border border-hairline bg-surface-2 p-3 text-sm">{result.welcome_email.body}</pre>
      </section>
    );
  }

  return (
    <section className={`${ui.card} flex flex-col gap-4`}>
      <ol className="flex flex-wrap gap-2 text-xs">
        {steps.map((label, index) => (
          <li key={label} className={index === step ? ui.badgeGold : ui.badge}>
            {index + 1}. {label}
          </li>
        ))}
      </ol>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      {step === 0 ? (
        <div className="flex flex-col gap-3 sm:max-w-md">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("slug")}</span>
            <input className={ui.input} value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="hausverwaltung-muster" />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("name")}</span>
            <input className={ui.input} value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("companyName")}</span>
            <input className={ui.input} value={companyName} onChange={(e) => setCompanyName(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("city")}</span>
            <input className={ui.input} value={city} onChange={(e) => setCity(e.target.value)} />
          </label>
        </div>
      ) : null}
      {step === 1 ? (
        <div className="flex flex-col gap-3">
          <p className={ui.help}>{t("entitiesHint")}</p>
          {entities.map((entity, index) => (
            <div key={index} className="flex flex-col gap-2 sm:flex-row">
              <select
                aria-label={t("entityKind")}
                className={ui.input}
                value={entity.kind}
                onChange={(e) => setEntities(entities.map((x, i) => (i === index ? { ...x, kind: e.target.value as EntityKind } : x)))}
              >
                <option value="manager">{t("kind_manager")}</option>
                <option value="rental_owner">{t("kind_rental_owner")}</option>
                <option value="sev_owner">{t("kind_sev_owner")}</option>
              </select>
              <input
                className={ui.input}
                aria-label={t("entityName")}
                value={entity.name}
                onChange={(e) => setEntities(entities.map((x, i) => (i === index ? { ...x, name: e.target.value } : x)))}
              />
              <button type="button" className={ui.buttonSm} onClick={() => setEntities(entities.filter((_, i) => i !== index))} disabled={entities.length === 1}>
                {t("remove")}
              </button>
            </div>
          ))}
          <button type="button" className={ui.secondary} onClick={() => setEntities([...entities, { kind: "rental_owner", name: "" }])}>
            {t("addEntity")}
          </button>
        </div>
      ) : null}
      {step === 2 ? (
        <div className="flex flex-col gap-3 sm:max-w-md">
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("adminEmail")}</span>
            <input className={ui.input} type="email" value={adminEmail} onChange={(e) => setAdminEmail(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("adminName")}</span>
            <input className={ui.input} value={adminName} onChange={(e) => setAdminName(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("adminPassword")}</span>
            <input className={ui.input} type="password" value={adminPassword} onChange={(e) => setAdminPassword(e.target.value)} />
            <span className={ui.help}>{t("adminPasswordHint")}</span>
          </label>
        </div>
      ) : null}
      {step === 3 ? (
        <div className="flex flex-col gap-3 sm:max-w-md">
          <p className={ui.help}>{t("ciHint")}</p>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("primaryColor")}</span>
            <input className={ui.input} value={primary} onChange={(e) => setPrimary(e.target.value)} placeholder="#1A2B3C" />
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("logoDocumentId")}</span>
            <input className={ui.input} value={logoId} onChange={(e) => setLogoId(e.target.value)} />
          </label>
        </div>
      ) : null}
      {step === 4 ? (
        <ul className="text-sm">
          <li>
            {t("name")}: {name} ({slug})
          </li>
          <li>{t("createdEntities", { count: entities.length })}</li>
          <li>
            {t("adminEmail")}: {adminEmail}
          </li>
          <li>{t("summaryFlags")}</li>
        </ul>
      ) : null}
      <div className={ui.formActions}>
        <button type="button" className={ui.secondary} onClick={() => setStep(Math.max(step - 1, 0))} disabled={step === 0 || busy}>
          {t("back")}
        </button>
        {step < steps.length - 1 ? (
          <button type="button" className={ui.primary} onClick={next}>
            {t("next")}
          </button>
        ) : (
          <button type="button" className={ui.primary} onClick={() => void submit()} disabled={busy}>
            {t("submit")}
          </button>
        )}
      </div>
    </section>
  );
}

/** Tenant export (GDPR access and portability): request, second person approves, download. */
export function TenantExport({ tenants }: { tenants: Tenant[] }) {
  const t = useTranslations("PlatformOnboarding");
  const tj = useTranslations("PlatformLicensing");
  const [tenantId, setTenantId] = useState(tenants[0]?.id ?? "");
  const [purpose, setPurpose] = useState<"access" | "portability">("access");
  const [requests, setRequests] = useState<ExportRequest[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function load(id: string) {
    setTenantId(id);
    const res = await bff<ExportRequest[]>(`/api/bff/platform/tenants/${id}/export-requests`);
    if (res.ok) setRequests(res.data);
    else setError(res.message);
  }

  async function request() {
    setError(null);
    const res = await bff<ExportRequest>(`/api/bff/platform/tenants/${tenantId}/export-requests`, {
      method: "POST",
      body: JSON.stringify({ purpose }),
    });
    if (!res.ok) setError(res.message);
    await load(tenantId);
  }

  async function decide(id: string, action: "approve" | "reject") {
    setError(null);
    const res = await bff<ExportRequest>(`/api/bff/platform/tenants/${tenantId}/export-requests/${id}/${action}`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    if (!res.ok) setError(res.message);
    await load(tenantId);
  }

  async function startJob(id: string) {
    setError(null);
    const res = await bff<ExportRequest>(`/api/bff/platform/tenants/${tenantId}/export-requests/${id}/run`, { method: "POST" });
    if (!res.ok) setError(res.message);
    await load(tenantId);
  }

  return (
    <section className={`${ui.card} flex flex-col gap-3`}>
      <h2 className={ui.h2}>{t("exportTitle")}</h2>
      <p className={ui.help}>{t("exportHint")}</p>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("tenant")}</span>
          <select className={ui.input} value={tenantId} onChange={(e) => void load(e.target.value)}>
            {tenants.map((tn) => (
              <option key={tn.id} value={tn.id}>
                {tn.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("purpose")}</span>
          <select className={ui.input} value={purpose} onChange={(e) => setPurpose(e.target.value as "access" | "portability")}>
            <option value="access">{t("purpose_access")}</option>
            <option value="portability">{t("purpose_portability")}</option>
          </select>
        </label>
        <button type="button" className={ui.primary} onClick={() => void request()} disabled={!tenantId}>
          {t("exportRequest")}
        </button>
        <button type="button" className={ui.secondary} onClick={() => void load(tenantId)} disabled={!tenantId}>
          {t("exportRefresh")}
        </button>
      </div>
      {requests.length ? (
        <div className={ui.tableScroll}>
          <table className={`${ui.table} w-full text-sm`}>
            <thead>
              <tr>
                <th className="text-left">{t("purpose")}</th>
                <th className="text-left">{t("status")}</th>
                <th className="text-left">{t("downloads")}</th>
                <th className="text-left">{t("actions")}</th>
              </tr>
            </thead>
            <tbody>
              {requests.map((r) => (
                <tr key={r.id}>
                  <td>{t(`purpose_${r.purpose}`)}</td>
                  <td>{t(`status_${r.status}`)}</td>
                  <td>{r.downloads}</td>
                  <td className="flex gap-2">
                    {r.status === "requested" ? (
                      <>
                        <button type="button" className={ui.buttonSm} onClick={() => void decide(r.id, "approve")}>
                          {t("approve")}
                        </button>
                        <button type="button" className={ui.buttonSm} onClick={() => void decide(r.id, "reject")}>
                          {t("reject")}
                        </button>
                      </>
                    ) : null}
                    {r.status === "approved" && (!r.job_status || r.job_status === "failed") ? (
                      <button type="button" className={ui.buttonSm} title={tj("exportJobHint")} onClick={() => void startJob(r.id)}>
                        {tj("exportJobStart")}
                      </button>
                    ) : null}
                    {r.status === "approved" && r.job_status && r.job_status !== "ready" ? (
                      <span className="text-xs">{tj(`job_${r.job_status}`)}</span>
                    ) : null}
                    {r.status === "approved" && (!r.job_status || r.job_status === "ready") ? (
                      <a className={ui.buttonSm} href={`/api/bff/platform/tenants/${tenantId}/export-requests/${r.id}/download`} download>
                        {t("download")}
                      </a>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className={ui.help}>{t("noRequests")}</p>
      )}
    </section>
  );
}

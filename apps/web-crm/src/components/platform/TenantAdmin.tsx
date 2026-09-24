"use client";

import type { components } from "@mhvp/api-client";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Tenant = components["schemas"]["mhvp__platform__schemas__TenantOut"];

const SLUG_PATTERN = /^[a-z0-9][a-z0-9-]{1,62}$/;

function CreateTenantForm({ onCreated }: { onCreated: (tenant: Tenant) => void }) {
  const t = useTranslations("TenantAdmin");
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!SLUG_PATTERN.test(slug)) {
      setError(t("slugInvalid"));
      return;
    }
    setBusy(true);
    setError(null);
    const res = await bff<Tenant>("/api/bff/platform/tenants", { method: "POST", body: JSON.stringify({ slug, name }) });
    setBusy(false);
    if (res.ok) {
      onCreated(res.data);
      setSlug("");
      setName("");
    } else {
      setError(res.message);
    }
  }

  return (
    <form onSubmit={(e) => void submit(e)} className={`${ui.card} flex flex-col gap-3 sm:max-w-md`}>
      <h2 className="text-sm font-semibold">{t("createTenantTitle")}</h2>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("slug")}</span>
        <input required className={ui.input} value={slug} onChange={(e) => setSlug(e.target.value)} placeholder="hausverwaltung-muster" />
        <span className="text-xs text-muted">{t("slugHint")}</span>
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("name")}</span>
        <input required className={ui.input} value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      <button type="submit" className={ui.primary} disabled={busy}>
        {t("createTenantSubmit")}
      </button>
    </form>
  );
}

function AssignAdminForm({ tenants }: { tenants: Tenant[] }) {
  const t = useTranslations("TenantAdmin");
  const [tenantId, setTenantId] = useState(tenants[0]?.id ?? "");
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    setError(null);
    const created = await bff<{ id: string }>("/api/bff/platform/users", {
      method: "POST",
      body: JSON.stringify({ email, display_name: displayName, password, is_platform_admin: false }),
    });
    if (!created.ok) {
      setBusy(false);
      if (created.status === 409) setError(t("emailExists"));
      else setError(created.message);
      return;
    }
    const added = await bff<unknown>(`/api/bff/platform/tenants/${tenantId}/members`, {
      method: "POST",
      body: JSON.stringify({ user_id: created.data.id, role_codes: ["tenant_admin"] }),
    });
    setBusy(false);
    if (added.ok) {
      setMessage(t("assignDone"));
      setEmail("");
      setDisplayName("");
      setPassword("");
    } else {
      setError(added.message);
    }
  }

  return (
    <form onSubmit={(e) => void submit(e)} className={`${ui.card} flex flex-col gap-3 sm:max-w-md`}>
      <h2 className="text-sm font-semibold">{t("assignAdminTitle")}</h2>
      <p className="text-xs text-muted">{t("assignAdminHint")}</p>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("tenant")}</span>
        <select required className={ui.input} value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
          {tenants.map((tn) => (
            <option key={tn.id} value={tn.id}>
              {tn.name}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("email")}</span>
        <input type="email" required className={ui.input} value={email} onChange={(e) => setEmail(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("displayName")}</span>
        <input required className={ui.input} value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("startPassword")}</span>
        <input type="password" required minLength={12} className={ui.input} value={password} onChange={(e) => setPassword(e.target.value)} />
      </label>
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      {message ? <p className="text-xs text-success-fg">{message}</p> : null}
      <button type="submit" className={ui.primary} disabled={busy || tenants.length === 0}>
        {t("assignAdminSubmit")}
      </button>
    </form>
  );
}

export function TenantAdmin({ initialTenants }: { initialTenants: Tenant[] }) {
  const [tenants, setTenants] = useState(initialTenants);
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <CreateTenantForm onCreated={(tenant) => setTenants((prev) => [...prev, tenant])} />
      <AssignAdminForm tenants={tenants} />
    </div>
  );
}

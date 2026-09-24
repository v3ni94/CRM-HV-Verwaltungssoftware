"use client";

import type { components } from "@mhvp/api-client";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Role = components["schemas"]["RoleOut"];

function groupByResource(permissions: string[]): Record<string, string[]> {
  const groups: Record<string, string[]> = {};
  for (const p of permissions) {
    const resource = p.split(":")[0] ?? p;
    (groups[resource] ??= []).push(p);
  }
  return groups;
}

function PermissionEditor({
  allPermissions,
  selected,
  onChange,
}: {
  allPermissions: string[];
  selected: string[];
  onChange: (next: string[]) => void;
}) {
  const groups = useMemo(() => groupByResource(allPermissions), [allPermissions]);
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {Object.entries(groups).map(([resource, perms]) => (
        <fieldset key={resource} className="rounded-md border border-border p-2">
          <legend className="px-1 text-xs font-medium text-muted">{resource}</legend>
          <div className="flex flex-col gap-1">
            {perms.map((p) => (
              <label key={p} className="flex items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={selected.includes(p)}
                  onChange={(e) => onChange(e.target.checked ? [...selected, p] : selected.filter((s) => s !== p))}
                />
                {p}
              </label>
            ))}
          </div>
        </fieldset>
      ))}
    </div>
  );
}

function RoleCard({ role, allPermissions, canUpdate, onSaved }: { role: Role; allPermissions: string[]; canUpdate: boolean; onSaved: (permissions: string[]) => void }) {
  const t = useTranslations("Roles");
  const [selected, setSelected] = useState<string[]>(role.permissions);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const editable = canUpdate && !role.is_system;

  async function save() {
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<Role>(`/api/bff/tenant/roles/${role.id}/permissions`, {
      method: "PUT",
      body: JSON.stringify({ permissions: selected }),
    });
    setBusy(false);
    if (res.ok) {
      onSaved(selected);
      setMessage(t("saved"));
    } else {
      setError(res.message);
    }
  }

  return (
    <section className={ui.card}>
      <div className="flex items-center justify-between">
        <h2 className="font-medium">
          {role.name} <span className="text-xs text-muted">({role.code})</span>
        </h2>
        {role.is_system ? <span className={ui.badge}>{t("system")}</span> : null}
      </div>
      <div className="mt-3">
        {editable ? (
          <PermissionEditor allPermissions={allPermissions} selected={selected} onChange={setSelected} />
        ) : (
          <p className="text-sm text-muted">{role.permissions.join(", ") || t("noPermissions")}</p>
        )}
      </div>
      {editable ? (
        <div className="mt-3 flex items-center gap-2">
          <button type="button" className={ui.primary} disabled={busy} onClick={() => void save()}>
            {t("save")}
          </button>
          {message ? <span className="text-xs text-success-fg">{message}</span> : null}
          {error ? <span className={ui.error}>{error}</span> : null}
        </div>
      ) : null}
    </section>
  );
}

function CreateRoleForm({ allPermissions, onCreated }: { allPermissions: string[]; onCreated: (role: Role) => void }) {
  const t = useTranslations("Roles");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [permissions, setPermissions] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const res = await bff<Role>("/api/bff/tenant/roles", {
      method: "POST",
      body: JSON.stringify({ code, name, permissions }),
    });
    setBusy(false);
    if (res.ok) {
      onCreated(res.data);
      setCode("");
      setName("");
      setPermissions([]);
    } else {
      setError(res.message);
    }
  }

  return (
    <form onSubmit={(e) => void submit(e)} className={`${ui.card} flex flex-col gap-3`}>
      <h2 className="text-sm font-semibold">{t("createTitle")}</h2>
      <label className="flex flex-col gap-1 sm:max-w-xs">
        <span className={ui.label}>{t("code")}</span>
        <input required className={ui.input} value={code} onChange={(e) => setCode(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 sm:max-w-xs">
        <span className={ui.label}>{t("name")}</span>
        <input required className={ui.input} value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <PermissionEditor allPermissions={allPermissions} selected={permissions} onChange={setPermissions} />
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
      <button type="submit" className={ui.primary} disabled={busy}>
        {t("createSubmit")}
      </button>
    </form>
  );
}

export function RolesAdmin({ initialRoles, canUpdate }: { initialRoles: Role[]; canUpdate: boolean }) {
  const t = useTranslations("Roles");
  const [roles, setRoles] = useState(initialRoles);
  const allPermissions = useMemo(
    () => Array.from(new Set(roles.flatMap((r) => r.permissions))).sort(),
    [roles],
  );

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted">{t("intro")}</p>
      {roles.map((r) => (
        <RoleCard
          key={r.id}
          role={r}
          allPermissions={allPermissions}
          canUpdate={canUpdate}
          onSaved={(permissions) => setRoles((prev) => prev.map((role) => (role.id === r.id ? { ...role, permissions } : role)))}
        />
      ))}
      {canUpdate ? (
        <CreateRoleForm allPermissions={allPermissions} onCreated={(role) => setRoles((prev) => [...prev, role])} />
      ) : null}
    </div>
  );
}

"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

const ROLES = ["eigentuemer", "mieter", "verwalter", "dienstleister", "bank", "sonstiges"] as const;

type ApplyRoleResult = { import_run_id: string; role: string; contacts_changed: number };

/** Adds a role to every contact an import run created; existing roles are kept. */
export function ImportRoleForm({ id }: { id: string }) {
  const t = useTranslations("Imports");
  const [role, setRole] = useState<(typeof ROLES)[number]>("bank");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const apply = async () => {
    setBusy(true);
    setError(null);
    setDone(null);
    const res = await bff<ApplyRoleResult>(`/api/bff/ai/import-runs/${id}/apply-role`, {
      method: "POST",
      body: JSON.stringify({ role }),
    });
    setBusy(false);
    if (res.ok) setDone(t("roleDone", { role: t(`role.${role}`), count: res.data.contacts_changed }));
    else setError(res.message);
  };

  return (
    <div className="flex flex-wrap items-end gap-2" aria-label={t("roleTitle")}>
      <label className="flex flex-col gap-1 text-sm">
        {t("roleLabel")}
        <select
          className={ui.input}
          value={role}
          onChange={(e) => setRole(e.target.value as (typeof ROLES)[number])}
          disabled={busy}
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {t(`role.${r}`)}
            </option>
          ))}
        </select>
      </label>
      <button type="button" className={ui.button} onClick={apply} disabled={busy}>
        {t("roleApply")}
      </button>
      {done ? <span className="text-sm">{done}</span> : null}
      {error ? (
        <span role="alert" className={ui.error}>
          {error}
        </span>
      ) : null}
    </div>
  );
}

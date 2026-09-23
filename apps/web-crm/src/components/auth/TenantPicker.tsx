"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export async function switchTenant(tenantId: string) {
  return bff<{ tenant_id: string | null }>("/api/session/tenant", {
    method: "POST",
    body: JSON.stringify({ tenant_id: tenantId }),
  });
}

export function TenantPicker({ tenants, next }: { tenants: { id: string; name: string }[]; next: string }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function choose(id: string) {
    setError(null);
    setBusy(id);
    const result = await switchTenant(id);
    setBusy(null);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    router.push(next);
    router.refresh();
  }

  return (
    <div className="flex flex-col gap-2">
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <ul className="flex flex-col gap-2">
        {tenants.map((tenant) => (
          <li key={tenant.id}>
            <button
              type="button"
              className={`${ui.button} w-full justify-start`}
              disabled={busy !== null}
              onClick={() => void choose(tenant.id)}
            >
              {tenant.name}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

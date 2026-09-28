"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { switchTenant } from "@/components/auth/TenantPicker";

export function TenantSwitcher({
  tenants,
  current,
}: {
  tenants: { id: string; name: string }[];
  current: string | null;
}) {
  const t = useTranslations("Shell");
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const active = tenants.find((tenant) => tenant.id === current);

  if (tenants.length < 2) {
    return (
      <span className="inline-flex items-center rounded-full border border-border bg-surface px-3 py-1.5 text-sm font-medium text-fg shadow-xs">
        {active?.name ?? ""}
      </span>
    );
  }

  async function onChange(event: React.ChangeEvent<HTMLSelectElement>) {
    setError(null);
    setBusy(true);
    const result = await switchTenant(event.target.value);
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    router.push("/kontakte");
    router.refresh();
  }

  return (
    <div className="flex items-center gap-2">
      <label htmlFor="tenant-switcher" className="sr-only">
        {t("switchTenant")}
      </label>
      <select
        id="tenant-switcher"
        className="mhvp-select w-auto rounded-full border border-border bg-surface py-1.5 pl-3.5 pr-7 text-sm font-medium text-fg shadow-xs transition hover:border-accent focus:border-accent-strong focus:outline-none focus:ring-2 focus:ring-focus"
        value={current ?? ""}
        disabled={busy}
        onChange={(e) => void onChange(e)}
      >
        {tenants.map((tenant) => (
          <option key={tenant.id} value={tenant.id}>
            {tenant.name}
          </option>
        ))}
      </select>
      {error ? (
        <span role="alert" className="text-xs text-danger-fg">
          {error}
        </span>
      ) : null}
    </div>
  );
}

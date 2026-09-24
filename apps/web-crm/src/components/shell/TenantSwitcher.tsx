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
      <span className="inline-flex items-center rounded-full border border-border bg-surface px-3 py-1.5 text-sm font-medium text-fg">
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
        className="w-auto appearance-none rounded-full border border-border bg-surface bg-[length:14px] bg-[right_0.6rem_center] bg-no-repeat py-1.5 pl-3.5 pr-7 text-sm font-medium text-fg transition hover:border-gold focus:border-gold focus:outline-none focus:ring-2 focus:ring-gold/40"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 20 20' fill='none' stroke='%23808080' stroke-width='1.5'%3E%3Cpath d='M5.5 7.5 10 12l4.5-4.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E\")",
        }}
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

"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { switchTenant } from "@/components/auth/TenantPicker";
import { ui } from "@/lib/ui";

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
    return <span className="text-sm font-medium">{active?.name ?? ""}</span>;
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
        className={`${ui.input} w-auto`}
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
        <span role="alert" className={ui.error}>
          {error}
        </span>
      ) : null}
    </div>
  );
}

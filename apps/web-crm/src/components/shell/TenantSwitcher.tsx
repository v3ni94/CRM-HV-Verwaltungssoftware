"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { switchTenant } from "@/components/auth/TenantPicker";

const SELECT: Record<"header" | "drawer", string> = {
  /** Header pill: 44 px and 16 px text on phones, the compact pill from `sm` with a mouse,
   *  44 px again on tablets with touch (M31). */
  header: "w-auto min-h-11 rounded-full py-1.5 pl-3.5 pr-7 text-base sm:text-sm sm:pointer-fine:min-h-0",
  /** Inside the navigation drawer: full width, 44 px, 16 px text. */
  drawer: "w-full min-h-11 rounded-md py-2 pl-3 pr-8 text-base",
};

export function TenantSwitcher({
  tenants,
  current,
  variant = "header",
}: {
  tenants: { id: string; name: string }[];
  current: string | null;
  variant?: "header" | "drawer";
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
    <div className={variant === "drawer" ? "flex flex-col gap-1" : "flex items-center gap-2"}>
      <label htmlFor={variant === "drawer" ? "tenant-switcher-drawer" : "tenant-switcher"} className="sr-only">
        {t("switchTenant")}
      </label>
      <select
        id={variant === "drawer" ? "tenant-switcher-drawer" : "tenant-switcher"}
        className={`mhvp-select border border-border bg-surface font-medium text-fg shadow-xs transition hover:border-accent focus:border-accent-strong focus:outline-none focus:ring-2 focus:ring-focus ${SELECT[variant]}`}
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

"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** AE36 (AA15-01): sets or removes the demo flag of a tenant (platform administrators). A tenant
 *  with an open release gate is refused by the API. The flag excludes the tenant from billing,
 *  exports, DATEV and statistics. */
export function DemoFlagToggle({ tenantId, isDemo }: { tenantId: string; isDemo: boolean }) {
  const t = useTranslations("AE36");
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    if (!window.confirm(isDemo ? t("demoConfirmUnmark") : t("demoConfirmMark"))) return;
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/platform/tenants/${tenantId}/demo`, {
      method: "PUT",
      body: JSON.stringify({ is_demo: !isDemo }),
    });
    setBusy(false);
    if (res.ok) router.refresh();
    else setError(res.message);
  }

  return (
    <div className="flex flex-col gap-1">
      <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void toggle()}>
        {isDemo ? t("demoUnmark") : t("demoMark")}
      </button>
      {error ? (
        <p role="alert" className={ui.error}>
          {error}
        </p>
      ) : null}
    </div>
  );
}

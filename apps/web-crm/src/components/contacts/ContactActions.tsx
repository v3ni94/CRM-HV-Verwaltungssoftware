"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export function ContactActions({
  id,
  name,
  canDelete = true,
}: {
  id: string;
  name: string;
  canDelete?: boolean;
}) {
  const t = useTranslations("Contacts");
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hint, setHint] = useState(false);
  const [busy, setBusy] = useState(false);

  async function remove() {
    setBusy(true);
    setError(null);
    const result = await bff<null>(`/api/bff/contacts/${id}`, { method: "DELETE" });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    router.push("/kontakte");
    router.refresh();
  }

  async function exportData() {
    setError(null);
    const result = await bff<unknown>(`/api/bff/contacts/${id}/export`);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    const blob = new Blob([JSON.stringify(result.data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `dsgvo-auskunft-${id}.json`;
    document.body.append(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    setHint(true);
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <div className="flex gap-2">
        <Link href={`/kontakte/${id}/bearbeiten`} className={ui.button}>
          {t("edit")}
        </Link>
        <button type="button" className={ui.button} onClick={() => void exportData()}>
          {t("export")}
        </button>
        {canDelete ? (
          <button type="button" className={ui.danger} onClick={() => setConfirming(true)}>
            {t("delete")}
          </button>
        ) : null}
      </div>
      {confirming ? (
        <div role="alertdialog" aria-labelledby="del-q" className={`${ui.card} max-w-md`}>
          <p id="del-q" className="mb-2 text-sm">
            {t("deleteConfirm", { name })}
          </p>
          <div className="flex gap-2">
            <button type="button" className={ui.danger} disabled={busy} onClick={() => void remove()} autoFocus>
              {t("deleteYes")}
            </button>
            <button type="button" className={ui.button} onClick={() => setConfirming(false)}>
              {t("cancel")}
            </button>
          </div>
        </div>
      ) : null}
      {hint ? (
        <p role="status" className={`${ui.notice} max-w-md`}>
          {t("exportHint")}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className={`${ui.alert} max-w-md`}>
          {error}
        </p>
      ) : null}
    </div>
  );
}

"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Bulk tag action on the checked rows (inputs named "bulk-id" inside the given form). */
export function BulkTagBar({ formId }: { formId: string }) {
  const t = useTranslations("Workspace");
  const router = useRouter();
  const [tag, setTag] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  async function run(action: "contacts.add_tag" | "contacts.remove_tag") {
    const form = document.getElementById(formId);
    const ids = Array.from(form?.querySelectorAll<HTMLInputElement>('input[name="bulk-id"]:checked') ?? []).map((i) => i.value);
    if (ids.length === 0) {
      setMessage(t("bulkNone"));
      return;
    }
    const result = await bff<{ changed: number }>("/api/bff/workspace/bulk", {
      method: "POST",
      body: JSON.stringify({ action, ids, tag: tag.trim() }),
    });
    setMessage(result.ok ? t("bulkDone", { changed: result.data.changed }) : result.message);
    if (result.ok) router.refresh();
  }

  return (
    <div className="flex flex-wrap items-center gap-2 text-sm" role="group" aria-label={t("bulk")}>
      <label htmlFor="bulk-tag" className="text-muted">
        {t("bulkTag")}
      </label>
      <input id="bulk-tag" value={tag} onChange={(e) => setTag(e.target.value)} maxLength={63} className={`${ui.input} w-40`} />
      <button type="button" className={ui.button} disabled={!tag.trim()} onClick={() => void run("contacts.add_tag")}>
        {t("bulkAdd")}
      </button>
      <button type="button" className={ui.button} disabled={!tag.trim()} onClick={() => void run("contacts.remove_tag")}>
        {t("bulkRemove")}
      </button>
      {message ? (
        <span role="status" className="text-muted">
          {message}
        </span>
      ) : null}
    </div>
  );
}

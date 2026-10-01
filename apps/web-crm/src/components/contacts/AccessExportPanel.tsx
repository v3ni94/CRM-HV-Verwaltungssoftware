"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDateTime } from "@/lib/format";
import { ui } from "@/lib/ui";

type AccessExport = {
  id: string;
  status: "prepared" | "reviewed" | "released" | "rejected";
  prepared_at: string;
  prepared_by: string | null;
  reviewed_by: string | null;
  released_by: string | null;
  downloads: number;
  rejected_reason: string | null;
};

/** DSGVO-Auskunft mit Prüfschritt (AC07, GA08-06): vorbereiten, prüfen und freigeben durch
 * eine zweite Person, erst danach Download; jeder Schritt wird protokolliert. */
export function AccessExportPanel({ contactId }: { contactId: string }) {
  const t = useTranslations("Contacts.accessExport");
  const base = `/api/bff/contacts/${contactId}/access-exports`;
  const [items, setItems] = useState<AccessExport[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const result = await bff<AccessExport[]>(base);
    if (result.ok) setItems(result.data);
    else setError(result.message);
  }, [base]);

  useEffect(() => {
    void load();
  }, [load]);

  async function act(path: string, init: RequestInit = { method: "POST" }) {
    setBusy(true);
    setError(null);
    const result = await bff<unknown>(path, init);
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return null;
    }
    await load();
    return result.data;
  }

  async function download(id: string) {
    const data = await act(`${base}/${id}/download`, { method: "GET" });
    if (data === null) return;
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `dsgvo-auskunft-${contactId}.json`;
    document.body.append(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <section aria-labelledby="access-export-title" className={`${ui.card} max-w-xl`}>
      <h3 id="access-export-title" className="mb-1 font-semibold">
        {t("title")}
      </h3>
      <p className="mb-2 text-sm">{t("hint")}</p>
      <button type="button" className={ui.button} disabled={busy} onClick={() => void act(base)}>
        {t("prepare")}
      </button>
      {items.length === 0 ? (
        <p className="mt-2 text-sm">{t("empty")}</p>
      ) : (
        <ul className="mt-2 flex flex-col gap-2">
          {items.map((item) => (
            <li key={item.id} className="text-sm">
              <span>
                {formatDateTime(item.prepared_at)}: {t(`status.${item.status}`)}
                {item.downloads > 0 ? ` (${t("downloads", { count: item.downloads })})` : ""}
              </span>
              <div className="mt-1 flex gap-2">
                {item.status === "prepared" ? (
                  <button
                    type="button"
                    className={ui.button}
                    disabled={busy}
                    onClick={() => void act(`${base}/${item.id}/review`)}
                  >
                    {t("review")}
                  </button>
                ) : null}
                {item.status === "reviewed" ? (
                  <button
                    type="button"
                    className={ui.button}
                    disabled={busy}
                    onClick={() => void act(`${base}/${item.id}/approve`)}
                  >
                    {t("release")}
                  </button>
                ) : null}
                {item.status === "prepared" || item.status === "reviewed" ? (
                  <button
                    type="button"
                    className={ui.button}
                    disabled={busy}
                    onClick={() =>
                      void act(`${base}/${item.id}/reject`, {
                        method: "POST",
                        body: JSON.stringify({ reason: t("rejectReason") }),
                      })
                    }
                  >
                    {t("reject")}
                  </button>
                ) : null}
                {item.status === "released" ? (
                  <button
                    type="button"
                    className={ui.button}
                    disabled={busy}
                    onClick={() => void download(item.id)}
                  >
                    {t("download")}
                  </button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
      {error ? (
        <p role="alert" className={`${ui.alert} mt-2`}>
          {error}
        </p>
      ) : null}
    </section>
  );
}

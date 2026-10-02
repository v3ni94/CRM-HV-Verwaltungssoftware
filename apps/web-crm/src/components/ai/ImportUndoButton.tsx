"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import { ImportUndoDialog } from "./ImportUndoDialog";

export function ImportUndoButton({ id }: { id: string }) {
  const t = useTranslations("Imports");
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const undo = async () => {
    setBusy(true);
    const res = await bff(`/api/bff/imports/${id}/undo`, { method: "POST" });
    setBusy(false);
    setOpen(false);
    if (res.ok) router.refresh();
    else setError(res.message);
  };
  return (
    <span className="inline-flex flex-col gap-1">
      <button type="button" className={ui.button} onClick={() => setOpen(true)} disabled={busy}>
        {t("undo")}
      </button>
      {open ? <ImportUndoDialog importId={id} open busy={busy} onConfirm={undo} onCancel={() => setOpen(false)} /> : null}
      {error ? (
        <span role="alert" className={ui.error}>
          {error}
        </span>
      ) : null}
    </span>
  );
}

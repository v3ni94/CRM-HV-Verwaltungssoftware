"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { ui } from "@/lib/ui";

/** Shows a secret exactly once (AF19). The value lives only in the state of the parent and is
 *  never written to a log, storage or URL; dismissing removes it from the page. */
export function SecretOnceNotice({ title, secret, onDismiss }: { title: string; secret: string; onDismiss: () => void }) {
  const t = useTranslations("AF19");
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(secret);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }
  return (
    <div className={`${ui.card} flex flex-col gap-2`} data-testid="secret-once" role="status">
      <h2 className={ui.h2}>{title}</h2>
      <p className={ui.help}>{t("secret.hint")}</p>
      <code className="break-all rounded bg-surface-2 px-2 py-1 text-xs">{secret}</code>
      <div className={ui.formActions}>
        <button type="button" className={ui.secondary} onClick={() => void copy()}>
          {t("secret.copy")}
        </button>
        <button type="button" className={ui.button} onClick={onDismiss}>
          {t("secret.dismiss")}
        </button>
      </div>
      {copied ? <p className={ui.success}>{t("secret.copied")}</p> : null}
    </div>
  );
}

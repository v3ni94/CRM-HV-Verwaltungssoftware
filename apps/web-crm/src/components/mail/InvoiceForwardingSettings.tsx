"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type InvoiceForwarding = {
  enabled: boolean;
  forward_address: string | null;
  sender_allowlist: string[];
  learning_list: string[];
};

/** Rechnungs-Weiterleitung (M20, operator 25.09.2026): Zieladresse und Absender-Positivliste
 * für Rechnungen der Gesellschaft selbst (nicht objektbezogen). Die Lernliste füllt sich, wenn
 * ein Vorschlag ("Weiterleiten?") in der Mailansicht zweimal bestätigt wird. */
export function InvoiceForwardingSettings({ initial }: { initial: InvoiceForwarding }) {
  const t = useTranslations("MailSettings");
  const [enabled, setEnabled] = useState(initial.enabled);
  const [address, setAddress] = useState(initial.forward_address ?? "");
  const [allowlist, setAllowlist] = useState(initial.sender_allowlist.join(", "));
  const [learningList, setLearningList] = useState(initial.learning_list);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function save() {
    setBusy(true);
    setError(null);
    setSaved(false);
    const sender_allowlist = allowlist
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const res = await bff<InvoiceForwarding>("/api/bff/mail/invoice-forwarding", {
      method: "PUT",
      body: JSON.stringify({ enabled, forward_address: address.trim() || null, sender_allowlist }),
    });
    setBusy(false);
    if (res.ok) {
      setLearningList(res.data.learning_list);
      setSaved(true);
    } else {
      setError(res.message);
    }
  }

  return (
    <section className={`${ui.card} flex flex-col gap-3`}>
      <h2 className="text-sm font-semibold">{t("invoiceForwardingTitle")}</h2>
      <p className="text-xs text-muted">{t("invoiceForwardingHint")}</p>
      <label className="flex items-center gap-1.5 text-sm">
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        {t("invoiceForwardingEnabled")}
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("invoiceForwardingAddress")}</span>
        <input
          type="email"
          className={ui.input}
          value={address}
          placeholder="muellerhv@inbox.lexware.email"
          onChange={(e) => setAddress(e.target.value)}
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("invoiceForwardingAllowlist")}</span>
        <textarea
          className={ui.input}
          rows={3}
          value={allowlist}
          placeholder="rechnung@telekom.de, buchhaltung@poetter.de"
          onChange={(e) => setAllowlist(e.target.value)}
        />
        <span className="text-xs text-muted">{t("invoiceForwardingAllowlistHint")}</span>
      </label>
      {learningList.length > 0 ? (
        <p className="text-xs text-muted">
          {t("invoiceForwardingLearningList")}: {learningList.join(", ")}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div className="flex items-center gap-3">
        <button type="button" className={ui.primary} disabled={busy} onClick={() => void save()}>
          {t("save")}
        </button>
        {saved ? <span className="text-xs text-success-fg">{t("saved")}</span> : null}
      </div>
    </section>
  );
}

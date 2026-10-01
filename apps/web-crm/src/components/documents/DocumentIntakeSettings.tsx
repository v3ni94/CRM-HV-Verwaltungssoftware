"use client";

import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type IntakeAddress = {
  configured: boolean;
  enabled: boolean;
  address: string | null;
  mailbox_address: string | null;
  allowed_senders: string[];
  distribute: boolean;
};

/** Eingangsadresse je Mandant (11.4, M6-04) und Schalter für den direkten Browser-Upload
 *  (S12-06, Standard aus). Die Adresse entsteht aus dem Sammelpostfach und einem Token
 *  (Plus-Adressierung). Mit der Verteilung nimmt ein Mandant (Hub) Nachrichten mit dem Token
 *  eines anderen Mandanten desselben Postfachs an und reicht sie weiter. */
export function DocumentIntakeSettings({ initial, directUpload }: { initial: IntakeAddress; directUpload: boolean }) {
  const t = useTranslations("DocumentIntakeSettings");
  const [config, setConfig] = useState(initial);
  const [mailbox, setMailbox] = useState(initial.mailbox_address ?? "");
  const [senders, setSenders] = useState(initial.allowed_senders.join("\n"));
  const [enabled, setEnabled] = useState(initial.configured ? initial.enabled : true);
  const [distribute, setDistribute] = useState(initial.distribute);
  const [direct, setDirect] = useState(directUpload);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const save = async (rotate: boolean) => {
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<IntakeAddress>(`/api/bff/document-intake-address${rotate ? "?rotate=true" : ""}`, {
      method: "PUT",
      body: JSON.stringify({
        mailbox_address: mailbox.trim(),
        allowed_senders: senders
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean),
        enabled,
        distribute,
      }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setConfig(res.data);
    setMessage(rotate ? t("rotated") : t("saved"));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void save(false);
  };

  const changeDirect = async (next: boolean) => {
    setBusy(true);
    setMessage(null);
    setError(null);
    const res = await bff<{ enabled: boolean }>("/api/bff/document-direct-upload", {
      method: "PUT",
      body: JSON.stringify({ enabled: next }),
    });
    setBusy(false);
    if (res.ok) {
      setDirect(res.data.enabled);
      setMessage(t("saved"));
    } else setError(res.message);
  };

  return (
    <div className="flex flex-col gap-4">
      <section className={`${ui.card} flex flex-col gap-3`} aria-label={t("title")} data-testid="intake-address">
        <h2 className="text-sm font-semibold">{t("title")}</h2>
        <p className="text-xs text-muted">{t("intro")}</p>
        {config.configured && config.address ? (
          <p className="text-sm">
            {t("address")}: <code data-testid="intake-address-value">{config.address}</code>
          </p>
        ) : (
          <p className="text-sm text-muted">{t("notConfigured")}</p>
        )}
        <form className="flex flex-col gap-2" onSubmit={submit}>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted">{t("mailbox")}</span>
            <input className={ui.input} type="email" value={mailbox} onChange={(e) => setMailbox(e.target.value)} aria-label={t("mailbox")} />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted">{t("senders")}</span>
            <textarea className={ui.input} rows={3} value={senders} onChange={(e) => setSenders(e.target.value)} aria-label={t("senders")} />
            <span className="text-xs text-muted">{t("sendersHint")}</span>
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
            {t("enabled")}
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={distribute} onChange={(e) => setDistribute(e.target.checked)} />
            {t("distribute")}
          </label>
          <p className="text-xs text-muted">{t("distributeHint")}</p>
          <div className="flex flex-wrap gap-2">
            <button type="submit" className={ui.primary} disabled={busy || !mailbox.trim()}>
              {t("save")}
            </button>
            {config.configured ? (
              <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void save(true)}>
                {t("rotate")}
              </button>
            ) : null}
          </div>
        </form>
      </section>
      <section className={`${ui.card} flex flex-col gap-2`} aria-label={t("direct.title")} data-testid="direct-upload">
        <h2 className="text-sm font-semibold">{t("direct.title")}</h2>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={direct} disabled={busy} onChange={(e) => void changeDirect(e.target.checked)} />
          {t("direct.label")}
        </label>
        <p className="text-xs text-muted">{t("direct.hint")}</p>
      </section>
      {message ? <p className={ui.success}>{message}</p> : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </div>
  );
}

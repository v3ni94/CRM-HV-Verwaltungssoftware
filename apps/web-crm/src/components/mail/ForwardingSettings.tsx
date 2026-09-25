"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type ForwardingConfig = {
  enabled: boolean;
  address: string;
  mode: "suggest" | "auto";
  senders: string[];
};

export function ForwardingSettings({ config }: { config: ForwardingConfig }) {
  const t = useTranslations("MailForwarding");
  const router = useRouter();
  const [enabled, setEnabled] = useState(config.enabled);
  const [address, setAddress] = useState(config.address);
  const [mode, setMode] = useState<"suggest" | "auto">(config.mode);
  const [senders, setSenders] = useState(config.senders.join("\n"));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const save = async () => {
    setBusy(true);
    setError(null);
    setSaved(false);
    const res = await bff("/api/bff/mail/forwarding", {
      method: "PUT",
      body: JSON.stringify({
        enabled,
        address: address.trim(),
        mode,
        senders: senders
          .split("\n")
          .map((line) => line.trim().toLowerCase())
          .filter(Boolean),
      }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setSaved(true);
    router.refresh();
  };

  return (
    <div className="flex max-w-2xl flex-col gap-4">
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {saved ? <p className={ui.success}>{t("saved")}</p> : null}
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        {t("enable")}
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("address")}</span>
        <input
          className={ui.input}
          type="email"
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          placeholder="muellerhv@inbox.lexware.email"
          maxLength={320}
        />
        <span className={ui.help}>{t("addressHelp")}</span>
      </label>
      <fieldset className="flex flex-col gap-1">
        <legend className={ui.label}>{t("mode")}</legend>
        <label className="flex items-start gap-2 text-sm">
          <input
            type="radio"
            name="mode"
            checked={mode === "suggest"}
            onChange={() => setMode("suggest")}
            className="mt-1"
          />
          <span>
            <span className="font-medium">{t("modeSuggest")}</span>
            <span className="block text-xs text-muted">{t("modeSuggestHelp")}</span>
          </span>
        </label>
        <label className="flex items-start gap-2 text-sm">
          <input
            type="radio"
            name="mode"
            checked={mode === "auto"}
            onChange={() => setMode("auto")}
            className="mt-1"
          />
          <span>
            <span className="font-medium">{t("modeAuto")}</span>
            <span className="block text-xs text-muted">{t("modeAutoHelp")}</span>
          </span>
        </label>
      </fieldset>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("senders")}</span>
        <textarea
          className={ui.input}
          rows={6}
          value={senders}
          onChange={(e) => setSenders(e.target.value)}
          placeholder={"rechnung@telekom.de\naok.de"}
        />
        <span className={ui.help}>{t("sendersHelp")}</span>
      </label>
      <button type="button" className={`${ui.primary} self-start`} disabled={busy} onClick={save}>
        {t("save")}
      </button>
    </div>
  );
}

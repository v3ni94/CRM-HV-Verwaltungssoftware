"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Channel = "post" | "email" | "hand_delivery";
const CHANNELS: Channel[] = ["post", "email", "hand_delivery"];

/** GAJ-103 (H03, D26): records the delivery of a consumption information in the substitute
 *  process without portal (channel, date, evidence). Only a record; nothing is sent. */
export function ConsumptionInfoDeliveryForm({ propertyId, infoId, canUpdate, onSaved }: { propertyId: string; infoId: string; canUpdate: boolean; onSaved?: () => void }) {
  const t = useTranslations("OperationsMasks.delivery");
  const [open, setOpen] = useState(false);
  const [channel, setChannel] = useState<Channel>("post");
  const [deliveredOn, setDeliveredOn] = useState("");
  const [evidence, setEvidence] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  if (!canUpdate) return null;
  if (done) return <span className={ui.success}>{t("saved")}</span>;
  if (!open) {
    return (
      <button type="button" className={ui.buttonSm} onClick={() => setOpen(true)}>
        {t("open")}
      </button>
    );
  }
  const valid = deliveredOn !== "" && evidence.trim().length >= 3;
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/properties/${propertyId}/consumption-info/${infoId}/delivery`, {
      method: "PUT",
      body: JSON.stringify({ channel, delivered_on: deliveredOn, evidence: evidence.trim() }),
    });
    setBusy(false);
    if (res.ok) {
      setDone(true);
      onSaved?.();
    } else setError(res.message);
  }
  return (
    <form onSubmit={save} className="flex flex-col gap-2" aria-label={t("title")} data-testid="consumption-delivery-form">
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("channel")}</span>
        <select className={ui.input} value={channel} onChange={(e) => setChannel(e.target.value as Channel)}>
          {CHANNELS.map((c) => (
            <option key={c} value={c}>
              {t(`channels.${c}`)}
            </option>
          ))}
        </select>
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("deliveredOn")}</span>
        <input type="date" className={ui.input} value={deliveredOn} onChange={(e) => setDeliveredOn(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className={ui.label}>{t("evidence")}</span>
        <textarea className={ui.input} maxLength={2000} value={evidence} onChange={(e) => setEvidence(e.target.value)} />
      </label>
      <p className={ui.help}>{t("evidenceHint")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div className="flex gap-2">
        <button type="submit" className={ui.primary} disabled={busy || !valid}>
          {t("save")}
        </button>
        <button type="button" className={ui.button} onClick={() => setOpen(false)} disabled={busy}>
          {t("cancel")}
        </button>
      </div>
    </form>
  );
}

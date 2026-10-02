"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState, type FormEvent } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type WorkOrderRatingState = {
  mode: "off" | "staff" | "all";
  can_rate: boolean;
  staff_rated: boolean;
  ratings: { id: string; party: "staff" | "resident"; stars: number; comment: string | null }[];
};

/** GAF-35: Bewertung des Auftrags durch die Verwaltung (einmalig, nach Abschluss). Die
 *  Bewertungen selbst erscheinen nur bei Schalter staff oder all; nie für Dienstleister. */
export function WorkOrderRatingPanel({ orderId, canEdit }: { orderId: string; canEdit: boolean }) {
  const t = useTranslations("WorkOrders");
  const [state, setState] = useState<WorkOrderRatingState | null>(null);
  const [stars, setStars] = useState(5);
  const [comment, setComment] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  async function load() {
    const res = await bff<WorkOrderRatingState>(`/api/bff/work-orders/${orderId}/rating`);
    if (res.ok) setState(res.data);
  }
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orderId]);

  async function save(e: FormEvent) {
    e.preventDefault();
    const res = await bff(`/api/bff/work-orders/${orderId}/rating`, {
      method: "POST",
      body: JSON.stringify({ stars, comment: comment.trim() || null }),
    });
    if (!res.ok) {
      setMessage({ ok: false, text: res.message });
      return;
    }
    setMessage({ ok: true, text: t("ratingSaved") });
    await load();
  }

  if (!state) return null;
  const visible = state.mode !== "off";
  return (
    <section className={`${ui.card} flex flex-col gap-2`} aria-label={t("ratingTitle")}>
      <h2 className="text-base font-semibold">{t("ratingTitle")}</h2>
      {!visible ? <p className={ui.help}>{t("ratingOff")}</p> : null}
      {visible && state.ratings.length === 0 ? <p className={ui.help}>{t("ratingNone")}</p> : null}
      {visible ? (
        <ul className="flex flex-col gap-1 text-sm">
          {state.ratings.map((r) => (
            <li key={r.id}>
              <span className="font-medium">{t(`ratingParty_${r.party}`)}:</span> {t("ratingStarsValue", { stars: r.stars })}
              {r.comment ? <span className="text-muted"> ({r.comment})</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
      {message ? (
        <p role="status" className={message.ok ? ui.success : ui.alert}>
          {message.text}
        </p>
      ) : null}
      {!state.can_rate ? <p className={ui.help}>{t("ratingNotYet")}</p> : null}
      {state.can_rate && state.staff_rated ? <p className={ui.help}>{t("ratingDone")}</p> : null}
      {state.can_rate && !state.staff_rated && canEdit ? (
        <form onSubmit={save} className="flex flex-col gap-2">
          <label className={ui.label}>
            {t("ratingStars")}
            <select className={ui.input} value={stars} onChange={(e) => setStars(Number(e.target.value))}>
              {[5, 4, 3, 2, 1].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <label className={ui.label}>
            {t("ratingComment")}
            <textarea className={ui.input} rows={3} maxLength={2000} value={comment} onChange={(e) => setComment(e.target.value)} />
          </label>
          <div>
            <button type="submit" className={ui.primary}>
              {t("ratingSubmit")}
            </button>
          </div>
        </form>
      ) : null}
    </section>
  );
}

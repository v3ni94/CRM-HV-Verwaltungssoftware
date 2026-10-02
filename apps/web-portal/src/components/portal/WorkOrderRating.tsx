"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type RatingState = {
  mode: string;
  can_rate: boolean;
  own: { stars: number } | null;
  provider_summary: { rated_count: number; average: string | null } | null;
};

/** GAF-35: Bewertung eines abgeschlossenen Auftrags durch den betroffenen Bewohner, einmalig.
 *  Die Durchschnittsanzeige des Dienstleisters erscheint nur bei Schalter "all". */
export function WorkOrderRating({ orderId }: { orderId: string }) {
  const t = useTranslations("Tickets");
  const [state, setState] = useState<RatingState | null>(null);
  const [stars, setStars] = useState(5);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function load() {
    const result = await bff<RatingState>(`/api/bff/portal/work-orders/${orderId}/rating`);
    if (result.ok) setState(result.data);
  }
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orderId]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    const result = await bff(`/api/bff/portal/work-orders/${orderId}/rating`, {
      method: "POST",
      body: JSON.stringify({ stars, comment: comment.trim() || null }),
    });
    setBusy(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    await load();
  }

  if (!state || (!state.can_rate && !state.own)) return null;
  const summary = state.provider_summary;
  return (
    <div className={`${ui.card} flex flex-col gap-3`}>
      <h2 className={ui.h2}>{t("rating")}</h2>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {state.own ? (
        <p role="status" className="text-sm">
          {t("ratingDone")} {t("ratingOwn", { stars: state.own.stars })}
        </p>
      ) : (
        <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
          <p className={ui.help}>{t("ratingHint")}</p>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("ratingStars")}</span>
            <select className={ui.input} value={stars} onChange={(e) => setStars(Number(e.target.value))}>
              {[5, 4, 3, 2, 1].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("ratingComment")}</span>
            <textarea
              className={ui.input}
              rows={3}
              maxLength={2000}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
            />
          </label>
          <button type="submit" className={ui.button} disabled={busy}>
            {t("ratingSubmit")}
          </button>
        </form>
      )}
      {summary && summary.average ? (
        <p className="text-sm text-muted">
          {t("ratingSummary", { average: summary.average, count: summary.rated_count })}
        </p>
      ) : null}
    </div>
  );
}

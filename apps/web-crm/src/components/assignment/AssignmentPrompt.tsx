"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

/** Rückfrage zur Zuordnung (Betreiber 27.09.2026): "Handelt es sich um den Kontakt Max
 *  Mustermann (Mieter, Objekt 012)?" mit Ja und Nein je Dimension (Kontakt, Objekt, Einheit)
 *  für eine Mail (`/mail/messages/{id}/assignment-review`) oder ein Ticket
 *  (`/tickets/{id}/assignment-review`). Ja übernimmt den Vorschlag, Nein verwirft ihn und
 *  öffnet eine Suche; bei mehreren Kandidaten wird die Liste angeboten. Sichere Treffer
 *  wurden serverseitig bereits übernommen und erscheinen hier nicht; die Karte bleibt leer,
 *  wenn keine Rückfrage offen ist. */

export type Dimension = "contact" | "property" | "unit";

export type AssignmentCandidate = {
  id: string;
  label: string;
  detail: string | null;
  confidence: number;
  reasons: string[];
};

export type AssignmentReview = {
  id: string;
  entity_type: "message" | "ticket";
  entity_id: string;
  dimension: Dimension;
  status: "auto" | "open" | "accepted" | "rejected" | "none" | "preset" | "superseded";
  candidates: AssignmentCandidate[];
  chosen_id: string | null;
  reason: string | null;
  decision: string | null;
};

type SearchHit = { id: string; label: string };

function basePath(entityType: "message" | "ticket", entityId: string): string {
  return entityType === "message" ? `/api/bff/mail/messages/${entityId}/assignment-review` : `/api/bff/tickets/${entityId}/assignment-review`;
}

type AssignmentPromptProps = {
  entityType: "message" | "ticket";
  entityId: string;
  canDecide: boolean;
  /** Vorab geladene Prüfzeilen (z. B. aus dem Detailabruf); ohne Angabe lädt die Karte selbst. */
  initialReviews?: AssignmentReview[];
  onDecided?: (reviews: AssignmentReview[]) => void;
};

/** Review 1.36.0: keyed by the entity, so switching to another mail or ticket starts with empty
 *  reviews, search and hits, and a late answer for the previous entity only reaches the
 *  unmounted instance. Ja and Übernehmen therefore always act on the entity shown. */
export function AssignmentPrompt(props: AssignmentPromptProps) {
  return <EntityAssignmentPrompt key={`${props.entityType}:${props.entityId}`} {...props} />;
}

function EntityAssignmentPrompt({ entityType, entityId, canDecide, initialReviews, onDecided }: AssignmentPromptProps) {
  const t = useTranslations("AssignmentPrompt");
  const [reviews, setReviews] = useState<AssignmentReview[]>(initialReviews ?? []);
  const [busy, setBusy] = useState<Dimension | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [searching, setSearching] = useState<Dimension | null>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);

  useEffect(() => {
    if (initialReviews) return;
    // Only the answer of the latest request is applied (no stale overwrite).
    let active = true;
    void bff<AssignmentReview[]>(basePath(entityType, entityId)).then((res) => {
      if (active && res.ok) setReviews(res.data ?? []);
    });
    return () => {
      active = false;
    };
  }, [initialReviews, entityType, entityId]);

  /** Review 1.36.0: every decision names what the member saw, the field value shown with the
   *  question (`seen_value`, null for an empty field) and for Ja the confirmed candidate
   *  (`candidate_id`, also for a single proposal). A 409 means the assignment changed meanwhile:
   *  the review is reloaded and the German detail is shown. */
  async function decide(review: AssignmentReview, decision: "accept" | "reject", candidateId?: string) {
    const dimension = review.dimension;
    setBusy(dimension);
    setError(null);
    const res = await bff<AssignmentReview[]>(`${basePath(entityType, entityId)}/decide`, {
      method: "POST",
      body: JSON.stringify({ dimension, decision, candidate_id: candidateId ?? null, seen_value: review.chosen_id ?? null }),
    });
    if (!res.ok) {
      if (res.status === 409) {
        const reload = await bff<AssignmentReview[]>(basePath(entityType, entityId));
        if (reload.ok) setReviews(reload.data ?? []);
        setSearching(null);
      }
      setBusy(null);
      setError(res.message || t("error"));
      return;
    }
    setBusy(null);
    setReviews(res.data ?? []);
    onDecided?.(res.data ?? []);
    if (decision === "reject") {
      setSearching(dimension);
      setQuery("");
      setHits([]);
    } else {
      setSearching(null);
    }
  }

  async function search(dimension: Dimension) {
    const q = query.trim();
    if (q.length < 2 && dimension !== "unit") return;
    setError(null);
    if (dimension === "contact") {
      const res = await bff<{ items: { id: string; display_name: string }[] }>(`/api/bff/contacts?q=${encodeURIComponent(q)}&page_size=10`);
      if (res.ok) setHits((res.data?.items ?? []).map((c) => ({ id: c.id, label: c.display_name })));
      else setError(res.message);
      return;
    }
    if (dimension === "property") {
      const res = await bff<{ items: { id: string; number: string; name: string }[] }>(`/api/bff/properties?q=${encodeURIComponent(q)}&page_size=10`);
      if (res.ok) setHits((res.data?.items ?? []).map((p) => ({ id: p.id, label: `${p.number} ${p.name}` })));
      else setError(res.message);
      return;
    }
    const propertyId = reviews.find((r) => r.dimension === "property")?.chosen_id;
    if (!propertyId) {
      setError(t("unitNeedsProperty"));
      return;
    }
    const res = await bff<{ id: string; number: string; label?: string | null; location?: string | null }[]>(`/api/bff/properties/${propertyId}/units`);
    if (res.ok) {
      const filter = q.toLowerCase();
      setHits(
        (res.data ?? [])
          .filter((u) => !filter || u.number.toLowerCase().includes(filter) || (u.location ?? "").toLowerCase().includes(filter))
          .map((u) => ({ id: u.id, label: [t("unitPrefix", { number: u.number }), u.label, u.location].filter(Boolean).join(", ") })),
      );
    } else setError(res.message);
  }

  const open = reviews.filter((r) => r.status === "open");
  const rejected = reviews.filter((r) => r.status === "rejected" && r.dimension === searching);
  if (open.length === 0 && rejected.length === 0 && !error) return null;

  return (
    <div className={`${ui.card} flex flex-col gap-3`} data-testid="assignment-prompt" role="region" aria-label={t("title")}>
      <div className="text-xs font-medium uppercase tracking-wide text-muted">{t("title")}</div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {open.map((review) => {
        const first = review.candidates[0];
        const many = review.candidates.length > 1;
        return (
          <div key={review.id} className="flex flex-col gap-2" data-testid={`assignment-prompt-${review.dimension}`}>
            <p className="text-sm">
              {many
                ? t(`questionMany.${review.dimension}`)
                : t(`question.${review.dimension}`, { label: first?.label ?? "", detail: first?.detail ? ` (${first.detail})` : "" })}
            </p>
            {first ? (
              <p className="text-xs text-muted">
                {t("confidence", { percent: Math.round(first.confidence * 100) })}
                {first.reasons.length ? `, ${first.reasons.join("; ")}` : ""}
              </p>
            ) : null}
            {many ? (
              <ul className="flex flex-col gap-1">
                {review.candidates.map((c) => (
                  <li key={c.id} className="flex items-center justify-between gap-2 text-sm">
                    <span>
                      {c.label}
                      {c.detail ? <span className="text-muted"> ({c.detail})</span> : null}
                      <span className="text-muted"> {t("confidence", { percent: Math.round(c.confidence * 100) })}</span>
                    </span>
                    {canDecide ? (
                      <button type="button" className={ui.buttonSm} disabled={busy === review.dimension} onClick={() => decide(review, "accept", c.id)}>
                        {t("choose")}
                      </button>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : null}
            {canDecide ? (
              <div className="flex gap-2">
                {!many ? (
                  <button type="button" className={ui.primary} disabled={busy === review.dimension || !first} onClick={() => first && decide(review, "accept", first.id)}>
                    {t("yes")}
                  </button>
                ) : null}
                <button type="button" className={ui.buttonSm} disabled={busy === review.dimension} onClick={() => decide(review, "reject")}>
                  {t("no")}
                </button>
              </div>
            ) : (
              <p className="text-xs text-muted">{t("readOnly")}</p>
            )}
          </div>
        );
      })}
      {rejected.map((review) => (
        <div key={review.id} className="flex flex-col gap-2" data-testid={`assignment-search-${review.dimension}`}>
          <p className="text-sm">{t(`search.${review.dimension}`)}</p>
          <div className="flex gap-2">
            <input
              className={ui.input}
              aria-label={t("searchLabel")}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void search(review.dimension);
                }
              }}
            />
            <button type="button" className={ui.buttonSm} onClick={() => search(review.dimension)}>
              {t("searchButton")}
            </button>
            <button type="button" className={ui.buttonSm} onClick={() => setSearching(null)}>
              {t("close")}
            </button>
          </div>
          {hits.length ? (
            <ul className="flex flex-col gap-1">
              {hits.map((hit) => (
                <li key={hit.id} className="flex items-center justify-between gap-2 text-sm">
                  <span>{hit.label}</span>
                  <button type="button" className={ui.buttonSm} disabled={busy === review.dimension} onClick={() => decide(review, "accept", hit.id)}>
                    {t("choose")}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ))}
    </div>
  );
}

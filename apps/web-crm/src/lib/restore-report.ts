/** GAM-209: Auswertung des Berichts des Wiederanwendungslaufs der Löschungen
 *  (`python -m mhvp.documents.replay_deletions --report`, Format ReplayReport.as_dict). */

export type RestoreResult = { document_id: string | null; outcome: string; reason: string | null };
export type RestoreReport = { apply: boolean; counts: Record<string, number>; results: RestoreResult[] };
export type RestoreGroup = "replayed" | "kept" | "review" | "skipped";

export const MAX_REPORT_BYTES = 5 * 1024 * 1024;

const GROUPS: Record<string, RestoreGroup> = {
  deleted: "replayed",
  would_delete: "replayed",
  trashed: "replayed",
  would_trash: "replayed",
  restored: "replayed",
  would_restore: "replayed",
  kept_hold: "kept",
  kept_blocked: "kept",
  kept_hash_mismatch: "kept",
  absent: "review",
  invalid: "review",
  skipped: "skipped",
};

/** Unknown outcome types land in the review group, never silently in a clean one. */
export const groupOf = (outcome: string): RestoreGroup => GROUPS[outcome] ?? "review";
export const isKnownOutcome = (outcome: string): boolean => outcome in GROUPS;

/** Parses the report text; null when it is not a report of the replay run. */
export function parseRestoreReport(text: string): RestoreReport | null {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    return null;
  }
  if (typeof raw !== "object" || raw === null) return null;
  const r = raw as Record<string, unknown>;
  if (typeof r.apply !== "boolean" || !Array.isArray(r.results)) return null;
  const results: RestoreResult[] = [];
  for (const item of r.results) {
    if (typeof item !== "object" || item === null) return null;
    const i = item as Record<string, unknown>;
    if (typeof i.outcome !== "string") return null;
    results.push({
      document_id: typeof i.document_id === "string" ? i.document_id : null,
      outcome: i.outcome,
      reason: typeof i.reason === "string" ? i.reason : null,
    });
  }
  const counts: Record<string, number> = {};
  for (const x of results) counts[x.outcome] = (counts[x.outcome] ?? 0) + 1;
  return { apply: r.apply, counts, results };
}

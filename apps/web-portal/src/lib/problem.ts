/** Problem details (RFC 9457, ADR 0004) as returned by the API, and German UI messages. */

export type FieldError = {
  location: (string | number)[];
  field: string;
  code: string;
  message: string;
};

export type Problem = {
  type?: string;
  title?: string;
  status?: number;
  detail?: string | null;
  code?: string;
  errors?: FieldError[] | null;
};

export const VERSION_CONFLICT_MESSAGE =
  "Der Datensatz wurde zwischenzeitlich geändert. Bitte die Seite neu laden und die Änderung erneut vornehmen.";

const FALLBACK: Record<number, string> = {
  400: "Die Anfrage konnte nicht verarbeitet werden.",
  401: "Die Sitzung ist abgelaufen. Bitte erneut anmelden.",
  403: "Für diese Aktion fehlt die Berechtigung.",
  404: "Der Datensatz wurde nicht gefunden.",
  409: "Die Aktion steht im Konflikt mit dem aktuellen Stand.",
  412: VERSION_CONFLICT_MESSAGE,
  422: "Bitte die markierten Angaben prüfen.",
  429: "Zu viele Anfragen. Bitte kurz warten und erneut versuchen.",
};

export function isProblem(value: unknown): value is Problem {
  return typeof value === "object" && value !== null && ("title" in value || "detail" in value);
}

/** German message for the user. The API already answers in German; 412 gets a fixed text. */
export function problemMessage(problem: Problem | null | undefined, status?: number): string {
  const code = status ?? problem?.status ?? 0;
  if (code === 412) return VERSION_CONFLICT_MESSAGE;
  const text = problem?.detail || problem?.title;
  if (text) return text;
  return FALLBACK[code] ?? "Die Schnittstelle ist derzeit nicht erreichbar. Bitte später erneut versuchen.";
}

/** Maps an API error location (e.g. ["body", "emails", 0, "email"]) to a form path. */
export function fieldPath(location: (string | number)[]): string | null {
  const parts = location[0] === "body" ? location.slice(1) : location;
  return parts.length ? parts.join(".") : null;
}

export async function readProblem(response: Response): Promise<Problem | null> {
  try {
    const body: unknown = await response.json();
    return isProblem(body) ? body : null;
  } catch {
    return null;
  }
}

export function problemJson(status: number, title: string, detail?: string): Response {
  return new Response(JSON.stringify({ title, status, detail: detail ?? null }), {
    status,
    headers: { "content-type": "application/problem+json" },
  });
}

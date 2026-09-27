/** Browser-side calls to the same-origin BFF (cookies are sent automatically). */
import { problemMessage, readProblem, type Problem } from "./problem";

export type BffResult<T> =
  | {
      ok: true;
      data: T;
      status: number;
      etag: string | null;
      // Paginierung (Betreibermeldung 27.09.2026, echte Seiten in /mail): gesetzt, wenn die
      // Antwort X-Total-Count/-Page/-Page-Size trägt (z. B. GET /mail/messages, GET /tickets).
      totalCount: number | null;
      page: number | null;
      pageSize: number | null;
    }
  | { ok: false; status: number; problem: Problem | null; message: string };

export async function bff<T>(path: string, init: RequestInit = {}): Promise<BffResult<T>> {
  const headers = new Headers(init.headers);
  // FormData sets its own multipart content type including the boundary.
  if (init.body && !(init.body instanceof FormData) && !headers.has("content-type")) headers.set("content-type", "application/json");
  let response: Response;
  try {
    response = await fetch(path, { ...init, headers, credentials: "same-origin", cache: "no-store" });
  } catch {
    return { ok: false, status: 0, problem: null, message: problemMessage(null, 0) };
  }
  if (!response.ok) {
    const problem = await readProblem(response);
    return { ok: false, status: response.status, problem, message: problemMessage(problem, response.status) };
  }
  // 204 and other empty bodies (e.g. 202 Accepted) yield null instead of a JSON parse error.
  const text = response.status === 204 ? "" : await response.text();
  const data = text ? (JSON.parse(text) as T) : (null as T);
  const numHeader = (name: string): number | null => {
    const value = response.headers.get(name);
    const parsed = value ? Number.parseInt(value, 10) : NaN;
    return Number.isFinite(parsed) ? parsed : null;
  };
  return {
    ok: true,
    data,
    status: response.status,
    etag: response.headers.get("etag"),
    totalCount: numHeader("x-total-count"),
    page: numHeader("x-page"),
    pageSize: numHeader("x-page-size"),
  };
}

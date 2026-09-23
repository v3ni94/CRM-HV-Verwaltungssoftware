/** Browser-side calls to the same-origin BFF (cookies are sent automatically). */
import { problemMessage, readProblem, type Problem } from "./problem";

export type BffResult<T> =
  | { ok: true; data: T; status: number; etag: string | null }
  | { ok: false; status: number; problem: Problem | null; message: string };

export async function bff<T>(path: string, init: RequestInit = {}): Promise<BffResult<T>> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("content-type")) headers.set("content-type", "application/json");
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
  const data = response.status === 204 ? (null as T) : ((await response.json()) as T);
  return { ok: true, data, status: response.status, etag: response.headers.get("etag") };
}

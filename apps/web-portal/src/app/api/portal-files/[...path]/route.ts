/**
 * Binary files of the portal handover protocols (M30 Stufe 3): photos, signatures and the PDF.
 * Served through the session with a narrow allowlist; read only, inline, no caching.
 */
import { serverFetch } from "@/lib/api-server";
import { problemJson } from "@/lib/problem";

const ID = "[0-9a-fA-F-]{36}";
const ALLOWED: RegExp[] = [
  new RegExp(`^portal/handover/${ID}/documents/${ID}/content$`),
  new RegExp(`^portal/handover/${ID}/pdf$`),
  new RegExp(`^portal/documents/${ID}/download$`),
  // Anlage eines Aushangs (Schwarzes Brett, A54); visibility follows the notice.
  new RegExp(`^portal/notices/${ID}/document$`),
  // Beleg eines Prüfauftrags (A52): nur freigegebene Belege, Abruf als Indiz vermerkt.
  new RegExp(`^portal/board/engagements/${ID}/documents/${ID}$`),
];
const MAX_BYTES = 60 * 1024 * 1024;

type Context = { params: Promise<{ path: string[] }> };

export async function GET(request: Request, context: Context): Promise<Response> {
  const path = (await context.params).path.join("/");
  if (!ALLOWED.some((rule) => rule.test(path))) return problemJson(404, "Nicht gefunden");
  const search = new URL(request.url).search;
  let upstream: Response;
  try {
    upstream = await serverFetch(`/api/v1/${path}${search}`, { method: "GET" });
  } catch {
    return problemJson(
      502,
      "Schnittstelle nicht erreichbar",
      "Die Schnittstelle ist derzeit nicht erreichbar. Bitte später erneut versuchen.",
    );
  }
  if (!upstream.ok) return problemJson(upstream.status === 401 ? 401 : 404, "Nicht gefunden");
  const payload = await upstream.arrayBuffer();
  if (payload.byteLength > MAX_BYTES) return problemJson(413, "Datei zu groß");
  const headers = new Headers({
    "cache-control": "private, no-store",
    "x-content-type-options": "nosniff",
  });
  headers.set("content-type", upstream.headers.get("content-type") ?? "application/octet-stream");
  headers.set("content-disposition", upstream.headers.get("content-disposition") ?? "inline");
  return new Response(payload, { status: 200, headers });
}

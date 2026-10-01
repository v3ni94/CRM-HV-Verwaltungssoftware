import { LOCALE_COOKIE, isLocale } from "@/lib/locale";

export const dynamic = "force-dynamic";

/** Stores the chosen portal language in a cookie (no personal data, one year). */
export async function POST(request: Request): Promise<Response> {
  const body = (await request.json().catch(() => null)) as { locale?: unknown } | null;
  if (!body || !isLocale(body.locale)) {
    return Response.json({ title: "Sprache nicht verfügbar", status: 422 }, { status: 422 });
  }
  const secure = request.url.startsWith("https:") ? "; Secure" : "";
  return new Response(null, {
    status: 204,
    headers: {
      "Set-Cookie": `${LOCALE_COOKIE}=${body.locale}; Path=/; Max-Age=31536000; SameSite=Lax${secure}`,
      "Cache-Control": "no-store",
    },
  });
}

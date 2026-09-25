/** Same-site landing for external redirects (Google OAuth, bank WebForm).
 *
 *  Session cookies are SameSite=Strict, so a redirect chain that starts at Google or a bank
 *  reaches the CRM without cookies and the middleware would show the login page although the
 *  session is still valid. This public route renders a tiny page whose JavaScript navigates to
 *  the internal target; that navigation is same-site and carries the cookies. Only relative
 *  paths are accepted so the route cannot be used as an open redirect. */
export const dynamic = "force-dynamic";

function safeNext(raw: string | null): string {
  if (
    !raw ||
    !raw.startsWith("/") ||
    raw.startsWith("//") ||
    raw.includes("\\")
  )
    return "/start";
  return raw;
}

export async function GET(request: Request): Promise<Response> {
  const next = safeNext(new URL(request.url).searchParams.get("next"));
  const json = JSON.stringify(next);
  const html = `<!doctype html><html lang="de"><head><meta charset="utf-8"><title>Weiterleitung</title>
<meta http-equiv="refresh" content="1;url=${next.replace(/"/g, "&quot;")}"></head>
<body style="font-family:system-ui;padding:2rem">Einen Moment, Sie werden weitergeleitet.
<script>location.replace(${json});</script></body></html>`;
  return new Response(html, {
    status: 200,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

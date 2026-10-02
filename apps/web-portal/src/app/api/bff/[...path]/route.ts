/**
 * Backend-for-frontend proxy of the portal. Only the listed portal operations are reachable;
 * the bearer token is added server side from the httpOnly cookie. Mutating methods require a
 * same-origin Origin header (CSRF, together with SameSite=Strict cookies). Binary content
 * (photos, PDF) is served by /api/portal-files, never through this JSON proxy.
 */
import { serverFetch } from "@/lib/api-server";
import { rejectForeignOrigin } from "@/lib/csrf";
import { problemJson } from "@/lib/problem";

const ID = "[0-9a-fA-F-]{36}";
const SECTION = "(participants|meters|rooms|defects|keys|items|notes)";
const ALLOWED: { method: string; pattern: RegExp }[] = [
  { method: "GET", pattern: /^portal\/me$/ },
  // AC06 (GA02-06): Annahme der Nutzungsbedingungen des Portals.
  { method: "GET", pattern: /^portal\/terms$/ },
  { method: "POST", pattern: /^portal\/terms\/accept$/ },
  // GA11-01: language choice stored at the portal account.
  { method: "PATCH", pattern: /^portal\/me\/locale$/ },
  // Sicherheit (operator 26.09.2026, M2-01): optional second factor and remembered devices of
  // the own account; the TOTP setup with its QR code runs through /api/session/totp/setup.
  { method: "POST", pattern: /^auth\/totp\/(confirm|disable)$/ },
  { method: "GET", pattern: /^auth\/trusted-devices$/ },
  { method: "DELETE", pattern: new RegExp(`^auth/trusted-devices/${ID}$`) },
  // S16-01: Passkeys nur als zweiter Faktor; die Optionen laufen über
  // /api/session/webauthn/register-options (erzwingt passwordless false).
  { method: "GET", pattern: /^auth\/webauthn\/(status|credentials)$/ },
  { method: "POST", pattern: /^auth\/webauthn\/register\/verify$/ },
  { method: "DELETE", pattern: new RegExp(`^auth/webauthn/credentials/${ID}$`) },
  // GAH-305: Passwort ändern und aktive Sitzungen des eigenen Kontos.
  { method: "POST", pattern: /^auth\/password$/ },
  { method: "GET", pattern: /^auth\/sessions$/ },
  { method: "DELETE", pattern: new RegExp(`^auth/sessions/${ID}$`) },
  // Benachrichtigungen mit Sprung zum Betreff (operator 26.09.2026).
  { method: "GET", pattern: /^portal\/notifications$/ },
  { method: "POST", pattern: /^portal\/notifications\/read$/ },
  // M21/M22 Portal Mieter, Eigentümer und Dienstleister.
  { method: "GET", pattern: /^portal\/documents$/ },
  // M25-06: Sammel-Download der Belege als ZIP mit Index.
  { method: "POST", pattern: /^portal\/documents\/bundle$/ },
  { method: "POST", pattern: /^portal\/uploads$/ },
  { method: "GET", pattern: /^portal\/tickets$/ },
  { method: "POST", pattern: /^portal\/tickets$/ },
  { method: "POST", pattern: new RegExp(`^portal/tickets/${ID}/comments$`) },
  // Formulare der Verwaltung (A56): Liste der eigenen Zielgruppe und Einreichung als Vorgang.
  { method: "GET", pattern: /^portal\/forms$/ },
  { method: "POST", pattern: new RegExp(`^portal/forms/${ID}/submissions$`) },
  { method: "POST", pattern: /^portal\/change-requests$/ },
  // M3-02 Portalstufe: digitales SEPA-Lastschriftmandat als Vorschlag (Freigabe im CRM, G2).
  { method: "GET", pattern: /^portal\/sepa-mandates\/preview$/ },
  { method: "GET", pattern: /^portal\/sepa-mandates$/ },
  { method: "POST", pattern: /^portal\/sepa-mandates$/ },
  { method: "POST", pattern: /^portal\/meter-readings$/ },
  { method: "GET", pattern: /^portal\/account$/ },
  // A51 Portal Eigentümer, lesend: Beschlüsse, Ansprechpartner, Hausgeldkonto.
  { method: "GET", pattern: /^portal\/resolutions$/ },
  // AD06 / GA11-03: Online-Versammlung (Zusage, Wortmeldung, Vollmacht, Stimmabgabe).
  { method: "GET", pattern: new RegExp(`^portal/meetings/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^portal/meetings/${ID}/(participation|speaker-requests)$`) },
  { method: "POST", pattern: new RegExp(`^portal/meetings/${ID}/agenda/${ID}/votes$`) },
  // AG07 (GAF-32): circular resolution votes of owners (switch and G4 checked by the API).
  { method: "GET", pattern: /^portal\/circular-resolutions$/ },
  { method: "POST", pattern: new RegExp(`^portal/circular-resolutions/${ID}/vote$`) },
  { method: "GET", pattern: /^portal\/meeting-proxies$/ },
  { method: "POST", pattern: /^portal\/meeting-proxies$/ },
  { method: "POST", pattern: new RegExp(`^portal/meeting-proxies/${ID}/revoke$`) },
  { method: "GET", pattern: /^portal\/property-contacts$/ },
  { method: "GET", pattern: /^portal\/hoa-account$/ },
  // P13: Chat zur Meldung (M21-01), Eigentümerübersicht (M21-06, M21-07, SA-05), Einwilligung in
  // die lesende Support-Sicht (SA-02).
  // AE28 (M7-06, SA-04): Assistent für die eigenen Unterlagen (Berechtigungsfilter in der API).
  { method: "GET", pattern: /^portal\/assistant\/(status|scope|questions)$/ },
  { method: "POST", pattern: /^portal\/assistant\/(questions|questions\/async|privacy-ack)$/ },
  // GAE-29: asynchrone Antwort, Status der eigenen Frage (nur eigener Zugang, API prüft).
  { method: "GET", pattern: new RegExp(`^portal/assistant/questions/${ID}$`) },
  { method: "GET", pattern: new RegExp(`^portal/tickets/${ID}/messages$`) },
  { method: "POST", pattern: new RegExp(`^portal/tickets/${ID}/messages$`) },
  { method: "GET", pattern: /^portal\/owner\/(tickets|payment-resolutions|consumption-info|allocation-properties|rental-income|statements|takeover-checklist)$/ },
  { method: "GET", pattern: new RegExp(`^portal/owner/consumption-info/${ID}$`) },
  { method: "GET", pattern: /^portal\/support-consent$/ },
  { method: "POST", pattern: /^portal\/support-consent$/ },
  { method: "DELETE", pattern: /^portal\/support-consent$/ },
  // Regel H03: monatliche Verbrauchsinformation der eigenen Einheit (lesend).
  { method: "GET", pattern: /^portal\/consumption-info$/ },
  { method: "GET", pattern: new RegExp(`^portal/consumption-info/${ID}$`) },
  // Schwarzes Brett (M21-01, A54): current notices of the own properties.
  { method: "GET", pattern: /^portal\/notices$/ },
  { method: "POST", pattern: new RegExp(`^portal/notices/${ID}/read$`) },
  { method: "GET", pattern: /^portal\/work-orders$/ },
  { method: "POST", pattern: new RegExp(`^portal/work-orders/${ID}/decline$`) },
  { method: "POST", pattern: new RegExp(`^portal/work-orders/${ID}/quote$`) },
  { method: "POST", pattern: new RegExp(`^portal/work-orders/${ID}/appointment$`) },
  // A58: Terminvorschläge (Dienstleister) und Bestätigung (betroffener Bewohner).
  { method: "GET", pattern: new RegExp(`^portal/work-orders/${ID}/appointment-proposals$`) },
  { method: "POST", pattern: new RegExp(`^portal/work-orders/${ID}/appointment-proposals$`) },
  { method: "POST", pattern: new RegExp(`^portal/work-orders/${ID}/appointment-proposals/${ID}/accept$`) },
  { method: "GET", pattern: new RegExp(`^portal/work-orders/${ID}/rating$`) },
  { method: "POST", pattern: new RegExp(`^portal/work-orders/${ID}/rating$`) },
  { method: "POST", pattern: new RegExp(`^portal/work-orders/${ID}/complete$`) },
  { method: "POST", pattern: new RegExp(`^portal/work-orders/${ID}/invoice$`) },
  // M22-01: XML e-invoice upload (multipart), read into a proposal.
  { method: "POST", pattern: new RegExp(`^portal/work-orders/${ID}/einvoice$`) },
  // Übergabeprotokolle (M30 Stufe 3): fill in, photos, signatures, completion.
  { method: "GET", pattern: /^portal\/handover$/ },
  // Staff mit Portalrecht handover:read (M2-08 entschieden): Liste aller Protokolle des Mandanten.
  { method: "GET", pattern: /^portal\/handover\/protocols$/ },
  { method: "GET", pattern: new RegExp(`^portal/handover/${ID}$`) },
  { method: "PATCH", pattern: new RegExp(`^portal/handover/${ID}$`) },
  { method: "GET", pattern: new RegExp(`^portal/handover/${ID}/hints$`) },
  { method: "POST", pattern: new RegExp(`^portal/handover/${ID}/(documents|signatures|complete)$`) },
  { method: "DELETE", pattern: new RegExp(`^portal/handover/${ID}/(documents|signatures)/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^portal/handover/${ID}/${SECTION}(/order)?$`) },
  { method: "PATCH", pattern: new RegExp(`^portal/handover/${ID}/${SECTION}/${ID}$`) },
  { method: "DELETE", pattern: new RegExp(`^portal/handover/${ID}/${SECTION}/${ID}$`) },
  // Prüfungsraum des Beirats (A52): read, and the note or question as the only action.
  { method: "GET", pattern: /^portal\/board\/engagements$/ },
  { method: "GET", pattern: new RegExp(`^portal/board/engagements/${ID}$`) },
  { method: "POST", pattern: new RegExp(`^portal/board/engagements/${ID}/notes$`) },
  // M25-04: Kontext einer Prüfposition (lesend).
  { method: "GET", pattern: new RegExp(`^portal/board/engagements/${ID}/positions/${ID}/context$`) },
  // A76: reports of the engagement and the board statement on a report version (text only).
  { method: "GET", pattern: new RegExp(`^portal/board/engagements/${ID}/reports$`) },
  { method: "POST", pattern: new RegExp(`^portal/board/engagements/${ID}/reports/${ID}/statement$`) },
];

/** Paths whose POST body is forwarded as multipart/form-data instead of JSON. */
const MULTIPART = new RegExp(`^portal/(handover/${ID}/documents|uploads|work-orders/${ID}/einvoice)$`);
/** Upper bound for proxied uploads; the API enforces its own document_max_bytes. */
const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

type Context = { params: Promise<{ path: string[] }> };

async function proxy(request: Request, context: Context): Promise<Response> {
  const method = request.method.toUpperCase();
  const path = (await context.params).path.join("/");
  if (!ALLOWED.some((rule) => rule.method === method && rule.pattern.test(path))) {
    return problemJson(404, "Nicht gefunden");
  }
  if (method !== "GET") {
    const rejected = rejectForeignOrigin(request);
    if (rejected) return rejected;
  }
  const headers = new Headers({ accept: "application/json" });
  // AE34: client address chain for the acceptance evidence of the terms (keyed hash in the API).
  const forwarded = request.headers.get("x-forwarded-for");
  if (forwarded) headers.set("x-forwarded-for", forwarded.slice(0, 200));
  let body: string | ArrayBuffer | undefined;
  if (method === "POST" && MULTIPART.test(path)) {
    const type = request.headers.get("content-type") ?? "";
    if (!type.toLowerCase().startsWith("multipart/form-data")) {
      return problemJson(415, "Nicht unterstützter Inhaltstyp");
    }
    const length = Number(request.headers.get("content-length") ?? "0");
    if (length > MAX_UPLOAD_BYTES) return problemJson(413, "Datei zu groß");
    body = await request.arrayBuffer();
    if (body.byteLength > MAX_UPLOAD_BYTES) return problemJson(413, "Datei zu groß");
    headers.set("content-type", type);
  } else if (method === "POST" || method === "PATCH") {
    body = await request.text();
    headers.set("content-type", "application/json");
  }
  const search = new URL(request.url).search;
  let upstream: Response;
  try {
    upstream = await serverFetch(`/api/v1/${path}${search}`, { method, headers, body });
  } catch {
    return problemJson(
      502,
      "Schnittstelle nicht erreichbar",
      "Die Schnittstelle ist derzeit nicht erreichbar. Bitte später erneut versuchen.",
    );
  }
  const out = new Headers({ "cache-control": "no-store" });
  const type = upstream.headers.get("content-type");
  if (type) out.set("content-type", type);
  const payload = upstream.status === 204 ? null : await upstream.arrayBuffer();
  return new Response(payload, { status: upstream.status, headers: out });
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const DELETE = proxy;

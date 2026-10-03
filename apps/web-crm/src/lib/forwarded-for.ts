/**
 * GAI-311: forwards the client chain (X-Forwarded-For) from the CRM server to the API, so the
 * API rate limit counts the real client instead of the CRM container. Only active when
 * MHVP_RATE_LIMIT_TRUSTED_PROXIES is set for the CRM process (same variable as the API; the
 * API must list the CRM container network there, otherwise it ignores the header). Without
 * the variable nothing is forwarded (default off, AJ07-01 open).
 *
 * AL06-02 (AM15): when the caller knows the direct peer of the incoming request (the socket
 * address), it is appended as the rightmost hop, like a proxy does. Next.js route handlers do
 * not expose the socket address, so the callers currently pass none; the chain is then only
 * trustworthy while the CRM is reachable exclusively through Traefik (runbook server-setup,
 * section "Vertrauensgrenze für X-Forwarded-For").
 */
const MAX_LENGTH = 512;
const ALLOWED = /^[0-9A-Fa-f.:, ]+$/;
const PEER = /^[0-9A-Fa-f.:]{2,45}$/;

/** Normalised peer address or null (strips the IPv4 mapped IPv6 prefix). */
export function peerAddress(peer: string | null | undefined): string | null {
  const value = (peer ?? "").trim().replace(/^::ffff:(?=\d+\.\d+\.\d+\.\d+$)/i, "");
  return PEER.test(value) && (value.includes(".") || value.includes(":")) ? value : null;
}

export function forwardingEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return (env.MHVP_RATE_LIMIT_TRUSTED_PROXIES ?? "").trim() !== "";
}

/** Sanitised X-Forwarded-For value or null (only IP characters, bounded length). */
export function forwardedForValue(
  source: Headers,
  env: NodeJS.ProcessEnv = process.env,
  peer?: string | null,
): string | null {
  if (!forwardingEnabled(env)) return null;
  const own = peerAddress(peer);
  const raw = (source.get("x-forwarded-for") ?? "").trim();
  const incoming = raw && raw.length <= MAX_LENGTH && ALLOWED.test(raw) ? raw : "";
  if (own) {
    // A malformed incoming chain is dropped; the peer alone still identifies the hop.
    return incoming ? `${incoming}, ${own}` : own;
  }
  return incoming || null;
}

/** Header record for API calls made on behalf of the incoming request. */
export function forwardedForHeaders(
  source: Headers,
  env: NodeJS.ProcessEnv = process.env,
  peer?: string | null,
): Record<string, string> {
  const value = forwardedForValue(source, env, peer);
  return value ? { "x-forwarded-for": value } : {};
}

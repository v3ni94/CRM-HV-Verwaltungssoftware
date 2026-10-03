/**
 * GAI-311: forwards the client chain (X-Forwarded-For) from the CRM server to the API, so the
 * API rate limit counts the real client instead of the CRM container. Only active when
 * MHVP_RATE_LIMIT_TRUSTED_PROXIES is set for the CRM process (same variable as the API; the
 * API must list the CRM container network there, otherwise it ignores the header). Without
 * the variable nothing is forwarded (default off, AJ07-01 open).
 */
const MAX_LENGTH = 512;
const ALLOWED = /^[0-9A-Fa-f.:, ]+$/;

export function forwardingEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return (env.MHVP_RATE_LIMIT_TRUSTED_PROXIES ?? "").trim() !== "";
}

/** Sanitised X-Forwarded-For value or null (only IP characters, bounded length). */
export function forwardedForValue(
  source: Headers,
  env: NodeJS.ProcessEnv = process.env,
): string | null {
  if (!forwardingEnabled(env)) return null;
  const value = (source.get("x-forwarded-for") ?? "").trim();
  if (!value || value.length > MAX_LENGTH || !ALLOWED.test(value)) return null;
  return value;
}

/** Header record for API calls made on behalf of the incoming request. */
export function forwardedForHeaders(
  source: Headers,
  env: NodeJS.ProcessEnv = process.env,
): Record<string, string> {
  const value = forwardedForValue(source, env);
  return value ? { "x-forwarded-for": value } : {};
}

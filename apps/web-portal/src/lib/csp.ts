/**
 * Content Security Policy with a nonce per request (GAH-303, Masterprompt Kapitel 16).
 *
 * Next 15 reads the nonce from the `content-security-policy` request header that the
 * middleware forwards and adds it to its own inline scripts; the root layout reads `x-nonce`
 * for the theme script. Reading the header makes every page dynamic, which a nonce needs.
 *
 * script-src: no 'unsafe-inline'. 'strict-dynamic' lets the nonced Next bootstrap load its
 * chunks. Development only adds 'unsafe-eval' (React dev tooling and Fast Refresh need eval).
 * style-src keeps 'unsafe-inline': React `style` props, next/font and Tailwind runtime classes
 * emit inline styles without a nonce; style injection is no script execution path.
 */
export const NONCE_HEADER = "x-nonce";
export const CSP_HEADER = "Content-Security-Policy";

export function createNonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes));
}

export function buildCsp(nonce: string, dev: boolean = process.env.NODE_ENV === "development"): string {
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    `connect-src 'self'${dev ? " ws: wss:" : ""}`,
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
  ].join("; ");
}

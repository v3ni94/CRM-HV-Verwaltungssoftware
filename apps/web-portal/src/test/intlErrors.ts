import { type IntlError, IntlErrorCode } from "next-intl";

/**
 * Strict next-intl error handling for the test suites. Each of these codes means the real UI
 * shows a raw key, a fallback path or an unformatted message, so a test must fail on it:
 * a missing key, a key that points at a nested object, missing or wrong ICU arguments and
 * unparsable messages. ENVIRONMENT_FALLBACK (no time zone or "now") stays a console warning.
 */
const STRICT_CODES: ReadonlySet<string> = new Set([
  IntlErrorCode.MISSING_MESSAGE,
  IntlErrorCode.INSUFFICIENT_PATH,
  IntlErrorCode.FORMATTING_ERROR,
  IntlErrorCode.INVALID_MESSAGE,
  IntlErrorCode.INVALID_KEY,
  IntlErrorCode.MISSING_FORMAT,
]);

const STRICT_CODE_VALUES: readonly string[] = [...STRICT_CODES];

/** Errors seen during the current test; checked and reset by vitest.setup.ts after each test. */
export const intlErrors: string[] = [];

function isStrict(code: unknown): boolean {
  return typeof code === "string" && STRICT_CODES.has(code);
}

/** onError for NextIntlClientProvider in tests: records the error and throws it. */
export function onIntlError(error: IntlError): void {
  if (isStrict(error.code)) {
    intlErrors.push(error.message);
    throw error;
  }
  console.error(error);
}

/**
 * Safety net for providers without onIntlError (the next-intl default handler logs to
 * console.error): records IntlErrors that reach the console so the test still fails.
 */
export function recordConsoleIntlError(args: unknown[]): void {
  const [first] = args;
  if (first instanceof Error && isStrict((first as Error & { code?: unknown }).code)) {
    intlErrors.push(first.message);
  } else if (typeof first === "string" && STRICT_CODE_VALUES.some((code) => first.startsWith(`${code}:`))) {
    intlErrors.push(first);
  }
}

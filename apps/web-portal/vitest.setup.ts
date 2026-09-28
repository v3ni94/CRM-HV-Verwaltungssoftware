import "@testing-library/jest-dom/vitest";

import { intlErrors, recordConsoleIntlError } from "@/test/intlErrors";

// Strict i18n: IntlErrors (missing key, key on a nested object, missing ICU arguments) fail
// the test even when a component swallows the thrown error or a provider without the strict
// onError logs it through the next-intl default handler (console.error).
const consoleError = console.error.bind(console);
console.error = (...args: unknown[]) => {
  recordConsoleIntlError(args);
  consoleError(...args);
};

beforeEach(() => {
  intlErrors.length = 0;
});

afterEach(() => {
  const seen = [...new Set(intlErrors)];
  intlErrors.length = 0;
  if (seen.length > 0) {
    throw new Error(`next-intl reported ${seen.length} error(s) in this test:\n${seen.join("\n")}`);
  }
});

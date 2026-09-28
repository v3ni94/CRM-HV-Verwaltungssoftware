import { render } from "@testing-library/react";
import { type AbstractIntlMessages, NextIntlClientProvider } from "next-intl";

import messages from "../../messages/de.json";

import { onIntlError } from "./intlErrors";

export { messages };

/**
 * Strict test provider: a missing key, a key on a nested object or missing ICU arguments
 * throw (see intlErrors.ts) instead of rendering the raw key.
 */
export function IntlTestProvider({
  children,
  locale = "de",
  catalogue = messages,
}: {
  children: React.ReactNode;
  locale?: string;
  catalogue?: AbstractIntlMessages;
}) {
  return (
    <NextIntlClientProvider locale={locale} messages={catalogue} timeZone="Europe/Berlin" onError={onIntlError}>
      {children}
    </NextIntlClientProvider>
  );
}

export function renderIntl(ui: React.ReactElement) {
  return render(<IntlTestProvider>{ui}</IntlTestProvider>);
}

export function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": status >= 400 ? "application/problem+json" : "application/json", ...headers },
  });
}

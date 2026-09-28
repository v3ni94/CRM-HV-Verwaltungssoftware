import { render } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import messages from "../../messages/de.json";

import { onIntlError } from "./intlErrors";

/**
 * Strict test provider: a missing key, a key on a nested object or missing ICU arguments
 * throw (see intlErrors.ts) instead of rendering the raw key.
 */
export function renderIntl(ui: React.ReactElement) {
  return render(
    <NextIntlClientProvider locale="de" messages={messages} timeZone="Europe/Berlin" onError={onIntlError}>
      {ui}
    </NextIntlClientProvider>,
  );
}

export function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": status >= 400 ? "application/problem+json" : "application/json", ...headers },
  });
}

import { render } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import messages from "../../messages/de.json";

export function renderIntl(ui: React.ReactElement) {
  return render(
    <NextIntlClientProvider locale="de" messages={messages} timeZone="Europe/Berlin">
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

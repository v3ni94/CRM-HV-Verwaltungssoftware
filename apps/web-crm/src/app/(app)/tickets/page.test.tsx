import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";

import messages from "../../../../messages/de.json";

// Renders the server component /tickets (page.tsx) end to end with a mocked API. Incident
// 27.09.2026: the production build failed with "Attempted to call asAttention() from the
// server" because the helper was imported from a "use client" module; the mapping now uses
// components/tickets/attention.ts. The data mirrors old imported tickets: no title, no SLA,
// no activity, attention missing or unknown.
// Minimal server translator over de.json (next-intl/server needs the request scope).
vi.mock("next-intl/server", async () => {
  const { default: de } = await import("../../../../messages/de.json");
  return {
    getTranslations: async (namespace: string) => (key: string, values: Record<string, unknown> = {}) => {
      const raw = `${namespace}.${key}`.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown> | undefined)?.[part], de);
      if (typeof raw !== "string") throw new Error(`INSUFFICIENT_PATH ${namespace}.${key}`);
      return raw.replace(/\{(\w+)\}/g, (_, name: string) => String(values[name] ?? ""));
    },
  };
});
// One stable instance: TicketFilters syncs its state in an effect keyed on the params object.
const { searchParams } = vi.hoisted(() => ({ searchParams: new URLSearchParams() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  useSearchParams: () => searchParams,
  redirect: (url: string) => {
    throw new Error(`redirect ${url}`);
  },
}));
const { serverFetch } = vi.hoisted(() => ({ serverFetch: vi.fn() }));
vi.mock("@/lib/api-server", () => ({
  serverFetch: (...args: unknown[]) => serverFetch(...args),
  redirectIfUnauthenticated: () => undefined,
  serverApi: () => ({ GET: vi.fn() }),
}));
vi.mock("@/lib/me", () => ({
  getMe: async () => ({
    data: { user_id: "u1", permissions: ["tickets:read"] },
    error: undefined,
    response: new Response("{}"),
  }),
}));
vi.mock("@/lib/bff", () => ({ bff: async () => ({ ok: false, message: "offline" }) }));


const OLD_TICKET = {
  id: "0199a1b2-0000-7000-8000-000000000001",
  number: 12,
  title: null,
  priority: "normal",
  status: "new",
  sla_due_at: null,
  sla_breached: false,
  last_activity_at: null,
  last_inbound_at: null,
  created_at: "2019-01-01T00:00:00Z",
};

async function renderPage(body: unknown, init: ResponseInit = {}) {
  serverFetch.mockResolvedValue(
    new Response(typeof body === "string" ? body : JSON.stringify(body), {
      status: 200,
      headers: { "content-type": "application/json", "x-total-count": "2" },
      ...init,
    }),
  );
  const { default: TicketsPage } = await import("./page");
  const element = await TicketsPage({ searchParams: Promise.resolve({}) });
  return render(
    <NextIntlClientProvider locale="de" messages={messages} timeZone="Europe/Berlin">
      {element}
    </NextIntlClientProvider>,
  );
}

describe("TicketsPage", () => {
  it("renders old tickets without title, SLA, activity or attention", async () => {
    await renderPage([
      OLD_TICKET,
      {
        ...OLD_TICKET,
        id: "0199a1b2-0000-7000-8000-000000000002",
        number: 13,
        attention: "weird",
        sla_due_at: "not-a-date",
        last_activity_at: "0000-00-00",
      },
    ]);
    const rows = screen.getAllByTestId("ticket-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveAttribute("data-attention", "none");
    expect(rows[1]).toHaveAttribute("data-attention", "none");
    expect(screen.getByTestId("tickets-pagination")).toHaveTextContent("1 bis 2 von 2");
  });

  it("shows a notice instead of crashing when the API answers with a problem", async () => {
    await renderPage({ title: "Dienst nicht erreichbar", status: 503 }, { status: 503 });
    expect(screen.getByRole("alert")).toHaveTextContent("Dienst nicht erreichbar");
  });

  it("shows a notice when the API cannot be reached at all", async () => {
    serverFetch.mockRejectedValue(new TypeError("fetch failed"));
    const element = await (await import("./page")).default({ searchParams: Promise.resolve({}) });
    render(
      <NextIntlClientProvider locale="de" messages={messages} timeZone="Europe/Berlin">
        {element}
      </NextIntlClientProvider>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("nicht erreichbar");
  });
});

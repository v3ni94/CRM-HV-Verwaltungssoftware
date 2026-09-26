import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { WebhookSubscriptionsAdmin, type WebhookSubscription } from "./WebhookSubscriptionsAdmin";

const HOOK_ID = "11111111-1111-4111-8111-111111111111";
const NEW_ID = "22222222-2222-4222-8222-222222222222";
const DELIVERY_ID = "33333333-3333-4333-8333-333333333333";

const hook: WebhookSubscription = {
  id: HOOK_ID,
  url: "https://empfaenger.example.org/hook",
  event_types: ["contact.updated"],
  active: true,
  description: "Buchhaltung",
  created_at: "2026-09-26T08:00:00+00:00",
  last_delivery_status: "failed",
  last_delivery_status_code: 500,
  last_delivery_at: "2026-09-26T09:15:00+00:00",
};

const eventTypes = [
  { type: "contact.updated", description: "Kontaktstammdaten geändert" },
  { type: "invoice.issued", description: "Verwalterhonorar-Rechnung ausgestellt" },
];

describe("WebhookSubscriptionsAdmin", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists subscriptions with event types, state and last delivery", () => {
    renderIntl(<WebhookSubscriptionsAdmin initial={[hook]} eventTypes={eventTypes} canManage canDelete />);
    const row = screen.getByTestId(`webhook-${HOOK_ID}`);
    expect(within(row).getByText("https://empfaenger.example.org/hook")).toBeInTheDocument();
    expect(within(row).getByText("contact.updated")).toBeInTheDocument();
    expect(within(row).getByText("aktiv")).toBeInTheDocument();
    expect(within(row).getByText("fehlgeschlagen")).toBeInTheDocument();
    expect(within(row).getByText(/HTTP 500/)).toBeInTheDocument();
  });

  it("creates a subscription from the catalogue and shows the secret once", { timeout: 20000 }, async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (String(input).endsWith("/api/bff/tenant/webhooks") && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as { url: string; event_types: string[]; description: string | null };
        return jsonResponse({ id: NEW_ID, ...body, active: true, secret: "geheim-1234" }, 201);
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<WebhookSubscriptionsAdmin initial={[]} eventTypes={eventTypes} canManage canDelete />);
    expect(screen.getByText("Noch keine Abonnements.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Neues Abonnement" }));
    expect(screen.getByText("Verwalterhonorar-Rechnung ausgestellt")).toBeInTheDocument();
    const urlInput = screen.getByLabelText("Ziel-URL");
    await userEvent.type(urlInput, "http://unsicher.example.org/hook");
    await userEvent.click(screen.getByLabelText(/invoice\.issued/));
    await userEvent.click(screen.getByRole("button", { name: "Abonnement anlegen" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Die Ziel-URL muss mit https:// beginnen.");
    expect(fetchMock).not.toHaveBeenCalled();

    await userEvent.clear(urlInput);
    await userEvent.type(urlInput, "https://neu.example.org/hook");
    await userEvent.click(screen.getByRole("button", { name: "Abonnement anlegen" }));
    await waitFor(() => expect(screen.getByTestId("webhook-secret")).toBeInTheDocument());
    expect(screen.getByText("geheim-1234")).toBeInTheDocument();
    const call = fetchMock.mock.calls.find(([input]) => String(input).endsWith("/api/bff/tenant/webhooks"));
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({
      url: "https://neu.example.org/hook",
      event_types: ["invoice.issued"],
      description: null,
    });
    expect(screen.getByTestId(`webhook-${NEW_ID}`)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Verstanden, ausblenden" }));
    expect(screen.queryByText("geheim-1234")).not.toBeInTheDocument();
  });

  it("deactivates, deletes after confirmation and shows the delivery log with redelivery", { timeout: 20000 }, async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith(`/api/bff/tenant/webhooks/${HOOK_ID}`) && init?.method === "PATCH") {
        return jsonResponse({ ...hook, active: false }, 200);
      }
      if (url.endsWith(`/api/bff/tenant/webhooks/${HOOK_ID}`) && init?.method === "DELETE") {
        return new Response(null, { status: 204 });
      }
      if (url.includes(`/api/bff/tenant/webhooks/${HOOK_ID}/deliveries`)) {
        return jsonResponse(
          [
            {
              id: DELIVERY_ID,
              event_id: "44444444-4444-4444-8444-444444444444",
              status: "failed",
              attempts: 7,
              next_attempt_at: null,
              last_status_code: 500,
              last_error: "HTTP 500",
              delivered_at: null,
            },
          ],
          200,
        );
      }
      if (url.endsWith(`/api/bff/tenant/webhook-deliveries/${DELIVERY_ID}/redeliver`) && init?.method === "POST") {
        return new Response(null, { status: 202 });
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    const confirmMock = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    renderIntl(<WebhookSubscriptionsAdmin initial={[hook]} eventTypes={eventTypes} canManage canDelete />);

    await userEvent.click(screen.getByRole("button", { name: "Protokoll" }));
    const log = await screen.findByTestId(`webhook-log-${HOOK_ID}`);
    expect(within(log).getByText("7")).toBeInTheDocument();
    expect(within(log).getByText("HTTP 500")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("page_size=20"))).toBe(true);
    await userEvent.click(within(log).getByRole("button", { name: "Erneut zustellen" }));
    await waitFor(() => expect(screen.getByText("Neuzustellung eingeplant.")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "Deaktivieren" }));
    await waitFor(() => expect(within(screen.getByTestId(`webhook-${HOOK_ID}`)).getByText("inaktiv")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Aktivieren" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Löschen" }));
    expect(screen.getByTestId(`webhook-${HOOK_ID}`)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Löschen" }));
    await waitFor(() => expect(screen.queryByTestId(`webhook-${HOOK_ID}`)).not.toBeInTheDocument());
    expect(confirmMock).toHaveBeenCalledTimes(2);
    const deleteCall = fetchMock.mock.calls.filter(([, init]) => init?.method === "DELETE");
    expect(deleteCall).toHaveLength(1);
  });

  it("is read only without the permissions", () => {
    renderIntl(<WebhookSubscriptionsAdmin initial={[hook]} eventTypes={eventTypes} canManage={false} canDelete={false} />);
    expect(screen.queryByRole("button", { name: "Neues Abonnement" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Deaktivieren" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Löschen" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Protokoll" })).toBeInTheDocument();
  });
});

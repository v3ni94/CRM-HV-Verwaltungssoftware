import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { NotificationPreferences } from "./NotificationPreferences";

const ITEMS = [
  { kind: "*", in_app: true, email: false, muted_until: null, mandatory: false },
  { kind: "ticket_assigned", in_app: true, email: false, muted_until: null, mandatory: false },
  { kind: "sla_escalation", in_app: true, email: false, muted_until: null, mandatory: true },
];

describe("NotificationPreferences", () => {
  const calls: { url: string; method: string; body: string | undefined }[] = [];
  beforeEach(() => {
    calls.length = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      calls.push({ url: String(input), method: init?.method ?? "GET", body: init?.body as string | undefined });
      return jsonResponse({ items: ITEMS });
    });
  });
  afterEach(() => vi.restoreAllMocks());

  it("shows a row per kind, mandatory kinds are locked", async () => {
    renderIntl(<NotificationPreferences />);
    expect(await screen.findByText("Ticket zugewiesen")).toBeInTheDocument();
    expect(screen.getByTestId("pref-inapp-sla_escalation")).toBeDisabled();
    expect(screen.getByTestId("pref-email-sla_escalation")).toBeDisabled();
    expect(screen.getByText("verpflichtend")).toBeInTheDocument();
    expect(screen.getByTestId("pref-email-ticket_assigned")).not.toBeDisabled();
  });

  it("saves channels and the mute without the mandatory rows", async () => {
    renderIntl(<NotificationPreferences />);
    await screen.findByText("Ticket zugewiesen");
    await userEvent.click(screen.getByTestId("pref-email-ticket_assigned"));
    await userEvent.selectOptions(screen.getByLabelText("Stummschalten für"), "8");
    await userEvent.click(screen.getByTestId("pref-save"));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    const put = calls.find((c) => c.method === "PUT")!;
    expect(put.url).toBe("/api/bff/workspace/notification-preferences");
    const body = JSON.parse(put.body!) as { items: { kind: string; email: boolean; muted_until: string | null }[] };
    expect(body.items.map((i) => i.kind)).toEqual(["*", "ticket_assigned"]);
    expect(body.items.find((i) => i.kind === "ticket_assigned")!.email).toBe(true);
    expect(body.items.find((i) => i.kind === "*")!.muted_until).not.toBeNull();
    expect(await screen.findByText("Einstellungen gespeichert.")).toBeInTheDocument();
  });

  it("sends the delivery mode and only enables it with the mail channel", async () => {
    renderIntl(<NotificationPreferences />);
    await screen.findByText("Ticket zugewiesen");
    expect(screen.getByTestId("pref-mode-ticket_assigned")).toBeDisabled();
    await userEvent.click(screen.getByTestId("pref-email-ticket_assigned"));
    await userEvent.selectOptions(screen.getByTestId("pref-mode-ticket_assigned"), "daily");
    await userEvent.click(screen.getByTestId("pref-save"));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    const body = JSON.parse(calls.find((c) => c.method === "PUT")!.body!) as { items: { kind: string; email_mode: string }[] };
    expect(body.items.find((i) => i.kind === "ticket_assigned")!.email_mode).toBe("daily");
  });
});

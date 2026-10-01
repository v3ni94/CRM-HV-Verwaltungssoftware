import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { SerialDispatchForm } from "./SerialDispatchForm";

describe("SerialDispatchForm", () => {
  afterEach(() => vi.restoreAllMocks());

  it("merges the template per recipient and shows the counts per channel", async () => {
    const calls: { url: string; body: unknown }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes("/api/bff/contacts?")) {
        return jsonResponse({ items: [{ id: "c1", display_name: "Anna Test" }] });
      }
      calls.push({ url, body: JSON.parse(String(init?.body)) });
      return jsonResponse(
        { batch: "abc", counts: { post: 1, email: 0 }, by_channel: { post: [{ id: "d1", contact_id: "c1" }] } },
        201,
      );
    });
    renderIntl(<SerialDispatchForm templates={[{ id: "t1", name: "Freier Brief" }]} />);
    const run = screen.getByRole("button", { name: "Serienbrief erzeugen und Zustellungen vorbereiten" });
    expect(run).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Empfänger suchen"), "Anna{enter}");
    await userEvent.click(await screen.findByRole("button", { name: /Anna Test/ }));
    await userEvent.type(screen.getByLabelText(/^Text/), "Hallo");
    await userEvent.click(run);
    await waitFor(() => expect(screen.getByText("Lauf abc")).toBeInTheDocument());
    expect(screen.getByText("Post: 1")).toBeInTheDocument();
    expect(calls[0]).toEqual({
      url: "/api/bff/dispatches/serial-merge",
      body: { template_id: "t1", contact_ids: ["c1"], fields: { betreff: "", text: "Hallo" }, advertising: false },
    });
  });

  it("sends the advertising flag and shows skipped contacts and e-mail fallbacks (AC06)", async () => {
    const calls: { url: string; body: unknown }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.includes("/api/bff/contacts?")) {
        return jsonResponse({ items: [{ id: "c1", display_name: "Anna Test" }] });
      }
      calls.push({ url, body: JSON.parse(String(init?.body)) });
      return jsonResponse(
        {
          batch: "xyz",
          counts: { post: 1 },
          by_channel: { post: [{ id: "d1", contact_id: "c1" }] },
          consent: { marketing_skipped: 2, email_fallback_to_post: 1 },
        },
        201,
      );
    });
    renderIntl(<SerialDispatchForm templates={[{ id: "t1", name: "Freier Brief" }]} />);
    await userEvent.click(screen.getByRole("checkbox", { name: /Werbung/ }));
    await userEvent.type(screen.getByLabelText("Empfänger suchen"), "Anna{enter}");
    await userEvent.click(await screen.findByRole("button", { name: /Anna Test/ }));
    await userEvent.type(screen.getByLabelText(/^Text/), "Hallo");
    await userEvent.click(screen.getByRole("button", { name: "Serienbrief erzeugen und Zustellungen vorbereiten" }));
    await waitFor(() => expect(screen.getByText("Lauf xyz")).toBeInTheDocument());
    expect(screen.getByText("2 Kontakte ohne Werbeeinwilligung übersprungen")).toBeInTheDocument();
    expect(screen.getByText("1 Zustellungen ohne E-Mail-Einwilligung auf Post umgestellt")).toBeInTheDocument();
    expect((calls[0]?.body as { advertising: boolean }).advertising).toBe(true);
  });
});

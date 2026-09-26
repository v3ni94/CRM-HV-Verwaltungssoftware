import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { NewTicket } from "./NewTicket";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

describe("NewTicket", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("requires a title and description before submitting", async () => {
    const user = userEvent.setup();
    renderIntl(<NewTicket />);
    await user.click(screen.getByRole("button", { name: "Melden" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bitte einen Titel eingeben.");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("submits title and description and shows the confirmation", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ id: "t1" }, 201));
    renderIntl(<NewTicket />);
    await user.type(screen.getByLabelText("Titel"), "Wasserschaden");
    await user.type(screen.getByLabelText("Beschreibung"), "Rohrbruch im Bad");
    await user.click(screen.getByRole("button", { name: "Melden" }));
    await waitFor(() => expect(screen.getByText("Meldung wurde übermittelt.")).toBeInTheDocument());
    expect(fetch).toHaveBeenCalledWith(
      "/api/bff/portal/tickets",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ title: "Wasserschaden", description: "Rohrbruch im Bad", document_ids: [] }),
      }),
    );
  });

  it("uploads photos first and links them by document id (A55)", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ id: "d1" }, 201))
      .mockResolvedValueOnce(jsonResponse({ id: "d2" }, 201))
      .mockResolvedValueOnce(jsonResponse({ id: "t1" }, 201));
    renderIntl(<NewTicket />);
    await user.type(screen.getByLabelText("Titel"), "Wasserschaden");
    await user.type(screen.getByLabelText("Beschreibung"), "Rohrbruch im Bad");
    await user.upload(screen.getByLabelText("Fotos anhängen (optional, JPEG oder PNG)"), [
      new File(["a"], "a.jpg", { type: "image/jpeg" }),
      new File(["b"], "b.png", { type: "image/png" }),
    ]);
    await user.click(screen.getByRole("button", { name: "Melden" }));
    await waitFor(() => expect(screen.getByText("Meldung wurde übermittelt.")).toBeInTheDocument());
    const calls = vi.mocked(fetch).mock.calls.map(([url, init]) => [String(url), init ?? {}] as const);
    expect(calls[0]?.[0]).toBe("/api/bff/portal/uploads");
    expect(calls[0]?.[1].body).toBeInstanceOf(FormData);
    expect(calls[1]?.[0]).toBe("/api/bff/portal/uploads");
    expect(calls[2]?.[0]).toBe("/api/bff/portal/tickets");
    expect(JSON.parse(String(calls[2]?.[1].body))).toEqual({
      title: "Wasserschaden",
      description: "Rohrbruch im Bad",
      document_ids: ["d1", "d2"],
    });
  });

  it("stops with the upload error and never creates the ticket", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch).mockResolvedValueOnce(
      jsonResponse({ title: "Upload abgelehnt", detail: "Das Bild konnte nicht gelesen werden." }, 422),
    );
    renderIntl(<NewTicket />);
    await user.type(screen.getByLabelText("Titel"), "Wasserschaden");
    await user.type(screen.getByLabelText("Beschreibung"), "Rohrbruch im Bad");
    await user.upload(
      screen.getByLabelText("Fotos anhängen (optional, JPEG oder PNG)"),
      new File(["a"], "a.jpg", { type: "image/jpeg" }),
    );
    await user.click(screen.getByRole("button", { name: "Melden" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Das Bild konnte nicht gelesen werden.");
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});

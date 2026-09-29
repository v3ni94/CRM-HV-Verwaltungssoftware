import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ContactMasterData } from "./ContactMasterData";

const contact = {
  id: "11111111-1111-4111-8111-111111111111",
  version: 3,
  kind: "person" as const,
  salutation: "Herr",
  first_name: "Max",
  last_name: "Muster",
  language: "de",
  preferred_channel: "email" as const,
  notes: null,
};

describe("ContactMasterData", () => {
  afterEach(() => vi.restoreAllMocks());

  it("saves a field via PATCH with If-Match and shows the saved state", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ ...contact, last_name: "Neu", version: 4 }));
    renderIntl(<ContactMasterData contact={contact} canEdit />);
    expect(screen.getByText("Muster")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Nachname bearbeiten" }));
    const input = screen.getByLabelText("Nachname");
    await userEvent.clear(input);
    await userEvent.type(input, "Neu{Enter}");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`/api/bff/contacts/${contact.id}`);
    expect(init.method).toBe("PATCH");
    expect(new Headers(init.headers).get("if-match")).toBe("3");
    expect(JSON.parse(String(init.body))).toEqual({ last_name: "Neu" });
    await waitFor(() => expect(screen.getByText("Neu")).toBeInTheDocument());
  });

  it("saves the consumer flag as a boolean and shows the help text", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse({ ...contact, is_consumer: true, version: 4 }));
    renderIntl(<ContactMasterData contact={{ ...contact, is_consumer: null }} canEdit />);
    expect(screen.getByText("Kennzeichen für das Mahnwesen (M16-03), keine Angabe bedeutet nicht beurteilt. Dient nur der Prüfung, keine rechtliche Feststellung.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Verbraucher bearbeiten" }));
    await userEvent.selectOptions(screen.getByLabelText("Verbraucher"), "Ja");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ is_consumer: true });
  });

  it("keeps a required field, hides editing without permission and shows the conflict on 412", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ type: "about:blank", title: "Konflikt", status: 412 }, 412));
    const { unmount } = renderIntl(<ContactMasterData contact={contact} canEdit={false} />);
    expect(screen.queryByRole("button", { name: "Bearbeiten" })).not.toBeInTheDocument();
    unmount();
    renderIntl(<ContactMasterData contact={contact} canEdit />);
    await userEvent.click(screen.getByRole("button", { name: "Bearbeiten" }));
    const last = screen.getByLabelText("Nachname");
    await userEvent.clear(last);
    await userEvent.tab();
    expect(screen.getByRole("alert")).toHaveTextContent("Pflichtangabe fehlt.");
    expect(fetchMock).not.toHaveBeenCalled();
    const first = screen.getByLabelText("Vorname");
    await userEvent.clear(first);
    await userEvent.type(first, "Moritz");
    await userEvent.tab();
    await waitFor(() => expect(screen.getByText("Von jemand anderem geändert, neu laden")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Neu laden" })).toBeInTheDocument();
  });
});

describe("ContactQuickActions (M31)", () => {
  it("renders 44 px call and mail actions only for existing values", async () => {
    const { ContactQuickActions } = await import("./ContactQuickActions");
    const { unmount } = renderIntl(<ContactQuickActions phone="+49 2103 123 456" email="max@example.com" />);
    const call = screen.getByRole("link", { name: "Anrufen" });
    expect(call).toHaveAttribute("href", "tel:+492103123456");
    expect(call.className).toContain("min-h-11");
    const mail = screen.getByRole("link", { name: "E-Mail" });
    expect(mail).toHaveAttribute("href", "mailto:max@example.com");
    expect(mail.className).toContain("min-h-11");
    unmount();
    renderIntl(<ContactQuickActions phone={null} email="max@example.com" />);
    expect(screen.queryByRole("link", { name: "Anrufen" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "E-Mail" })).toBeInTheDocument();
    unmount();
    const { container } = renderIntl(<ContactQuickActions phone={null} email={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});

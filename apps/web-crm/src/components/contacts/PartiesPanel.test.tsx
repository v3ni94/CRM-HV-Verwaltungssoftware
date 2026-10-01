import { fireEvent, screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PartiesPanel, type Party } from "./PartiesPanel";

const ME = "11111111-1111-7111-8111-111111111111";
const OTHER = "22222222-2222-7222-8222-222222222222";
const PARTY = "33333333-3333-7333-8333-333333333333";

const party: Party = {
  id: PARTY,
  name: "Anna und Bernd Beispiel",
  members: [
    { contact_id: ME, role: "primary", share_percent: "50.00000000", display_name: "Anna Beispiel" },
    { contact_id: OTHER, role: "co_party", share_percent: "50.00000000", display_name: "Bernd Beispiel" },
  ],
};

function panel(over: Partial<React.ComponentProps<typeof PartiesPanel>> = {}) {
  return renderIntl(<PartiesPanel contactId={ME} contactName="Anna Beispiel" canCreate canUpdate canDelete {...over} />);
}

describe("PartiesPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists the parties of the contact with members, role and share", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([party]));
    panel();
    expect(await screen.findByText("Anna und Bernd Beispiel")).toBeInTheDocument();
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/bff/parties?contact_id=${ME}`);
    expect(screen.getByRole("link", { name: "Bernd Beispiel" })).toHaveAttribute("href", `/kontakte/${OTHER}`);
    expect(screen.getAllByText(/50 Prozent/).length).toBe(2);
  });

  it("shows the empty state and hides all actions without permissions", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([party]));
    panel({ canCreate: false, canUpdate: false, canDelete: false });
    await screen.findByText("Anna und Bernd Beispiel");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("creates a party with the contact as first member", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse(party, 201))
      .mockResolvedValueOnce(jsonResponse([party]));
    panel();
    await screen.findByText("Keine Vertragsparteien vorhanden.");
    fireEvent.click(screen.getByRole("button", { name: "Partei anlegen" }));
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await screen.findByText("Anna und Bernd Beispiel");
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe("/api/bff/parties");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      name: null,
      members: [{ contact_id: ME, role: "primary", share_percent: null }],
    });
  });

  it("patches name, roles and shares and sends the complete member list", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse([party]))
      .mockResolvedValueOnce(jsonResponse(party))
      .mockResolvedValueOnce(jsonResponse([party]));
    panel();
    await screen.findByText("Anna und Bernd Beispiel");
    fireEvent.click(screen.getByRole("button", { name: "Bearbeiten" }));
    fireEvent.change(screen.getByLabelText("Anteil in Prozent für Bernd Beispiel"), { target: { value: "25,5" } });
    fireEvent.change(screen.getByLabelText("Rolle von Bernd Beispiel"), { target: { value: "guarantor" } });
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe(`/api/bff/parties/${PARTY}`);
    expect(init.method).toBe("PATCH");
    const body = JSON.parse(String(init.body));
    expect(body.members).toEqual([
      { contact_id: ME, role: "primary", share_percent: "50.00000000" },
      { contact_id: OTHER, role: "guarantor", share_percent: "25.5" },
    ]);
  });

  it("refuses shares above 100 percent before calling the API", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([party]));
    panel();
    await screen.findByText("Anna und Bernd Beispiel");
    fireEvent.click(screen.getByRole("button", { name: "Bearbeiten" }));
    fireEvent.change(screen.getByLabelText("Anteil in Prozent für Bernd Beispiel"), { target: { value: "80" } });
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Die Anteile übersteigen 100 Prozent.");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("deletes after confirmation and shows the API refusal for a party in use", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse([party]))
      .mockResolvedValueOnce(
        jsonResponse({ title: "Konflikt", status: 409, detail: "Die Partei wird noch verwendet." }, 409),
      );
    panel();
    await screen.findByText("Anna und Bernd Beispiel");
    fireEvent.click(screen.getByRole("button", { name: "Löschen" }));
    await screen.findByRole("alert");
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(url).toBe(`/api/bff/parties/${PARTY}`);
    expect(init.method).toBe("DELETE");
    expect(screen.getByRole("alert")).toHaveTextContent("verwendet");
  });
});

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ResolutionKindsSettings } from "./ResolutionKindsSettings";

const KINDS = {
  kinds: [
    { code: "auskunft_erteilt", label: "Auskunft erteilt", builtin: true, active: true },
    { code: "weitergeleitet", label: "Weitergeleitet", builtin: true, active: true },
    { code: "zusammengefuehrt", label: "Zusammengeführt", builtin: true, active: true },
    { code: "sonstiges", label: "Sonstiges", builtin: true, active: true },
  ],
};

function mockFetch() {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/api/bff/tickets/resolution-kinds")) return jsonResponse(KINDS);
    if (url.endsWith("/api/bff/tenant/settings") && init?.method === "PATCH") {
      return jsonResponse({ resolution_kinds: JSON.parse(String(init.body)).resolution_kinds });
    }
    return jsonResponse({ title: "unerwartet" }, 500);
  });
}

describe("ResolutionKindsSettings", () => {
  afterEach(() => vi.restoreAllMocks());

  it("deactivates a built in kind and keeps Sonstiges and Zusammengeführt locked", async () => {
    const fetchMock = mockFetch();
    renderIntl(<ResolutionKindsSettings initial={{ disabled: [], custom: [] }} canUpdate />);
    const box = await screen.findByLabelText("Weitergeleitet");
    expect(screen.getByLabelText("Sonstiges")).toBeDisabled();
    expect(screen.getByLabelText("Zusammengeführt")).toBeDisabled();
    await userEvent.setup().click(box);
    await waitFor(() => expect(screen.getByText("Gespeichert.")).toBeInTheDocument());
    expect(box).not.toBeChecked();
    const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH")!;
    expect(JSON.parse(String(patch[1]?.body))).toEqual({ resolution_kinds: { disabled: ["weitergeleitet"], custom: [] } });
  });

  it("adds and removes an own kind and validates the code", async () => {
    const fetchMock = mockFetch();
    renderIntl(<ResolutionKindsSettings initial={{ disabled: [], custom: [] }} canUpdate />);
    const user = userEvent.setup();
    await screen.findByLabelText("Weitergeleitet");
    await user.type(screen.getByLabelText("Code"), "Schlüssel");
    await user.type(screen.getByLabelText("Bezeichnung"), "Schlüssel übergeben");
    await user.click(screen.getByText("Hinzufügen"));
    expect(screen.getByRole("alert")).toHaveTextContent("Der Code darf nur Kleinbuchstaben");
    await user.clear(screen.getByLabelText("Code"));
    await user.type(screen.getByLabelText("Code"), "sonstiges");
    await user.click(screen.getByText("Hinzufügen"));
    expect(screen.getByRole("alert")).toHaveTextContent("bereits vergeben");
    await user.clear(screen.getByLabelText("Code"));
    await user.type(screen.getByLabelText("Code"), "schluessel_uebergeben");
    await user.click(screen.getByText("Hinzufügen"));
    const list = await screen.findByTestId("resolution-kinds-custom");
    expect(within(list).getByText(/Schlüssel übergeben/)).toBeInTheDocument();
    const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH")!;
    expect(JSON.parse(String(patch[1]?.body))).toEqual({
      resolution_kinds: { disabled: [], custom: [{ code: "schluessel_uebergeben", label: "Schlüssel übergeben" }] },
    });
    await user.click(within(list).getByText("Entfernen"));
    await waitFor(() => expect(screen.queryByTestId("resolution-kinds-custom")).not.toBeInTheDocument());
  });

  it("is read only without the update permission", async () => {
    mockFetch();
    renderIntl(<ResolutionKindsSettings initial={{ disabled: [], custom: [{ code: "eigene", label: "Eigene Art" }] }} canUpdate={false} />);
    expect(await screen.findByLabelText("Weitergeleitet")).toBeDisabled();
    expect(screen.queryByText("Hinzufügen")).not.toBeInTheDocument();
    expect(screen.queryByText("Entfernen")).not.toBeInTheDocument();
    expect(screen.getByText("Die Änderung erfordert das Recht Mandanteneinstellungen ändern.")).toBeInTheDocument();
  });
});

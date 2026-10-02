import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ProspectSelfDisclosureLinks } from "./ProspectSelfDisclosureLinks";

describe("ProspectSelfDisclosureLinks (GAI-420)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists the links with status and never shows a token", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse([
        { id: "01920000-0000-7000-8000-0000000a1701", expires_at: "2099-01-31T00:00:00Z", submitted_at: "2026-10-01T10:00:00Z", consent_privacy: true },
        { id: "01920000-0000-7000-8000-0000000a1702", expires_at: "2020-01-01T00:00:00Z", submitted_at: null, consent_privacy: false },
      ]),
    );
    renderIntl(<ProspectSelfDisclosureLinks prospectId="01920000-0000-7000-8000-0000000a1701" />);
    await userEvent.click(screen.getByRole("button", { name: "Links anzeigen" }));
    const box = await screen.findByTestId("self-disclosure-links");
    expect(box).toHaveTextContent("eingereicht am 01.10.2026");
    expect(box).toHaveTextContent("abgelaufen");
    expect(f.mock.calls[0]![0]).toBe("/api/bff/letting/prospects/01920000-0000-7000-8000-0000000a1701/self-disclosure-links");
  });

  it("shows the empty state and API errors", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ title: "Verboten", status: 403 }, 403));
    renderIntl(<ProspectSelfDisclosureLinks prospectId="01920000-0000-7000-8000-0000000a1701" />);
    await userEvent.click(screen.getByRole("button", { name: "Links anzeigen" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    f.mockResolvedValueOnce(jsonResponse([]));
    await userEvent.click(screen.getByRole("button", { name: "Links anzeigen" }));
    expect(await screen.findByText("Noch kein Link erzeugt.")).toBeInTheDocument();
  });
});

import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ResolutionMajorityCheck } from "./ResolutionMajorityCheck";

describe("ResolutionMajorityCheck (GAI-413)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads stored and current check of the resolution", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ stored: null, current: { result: "erreicht", rule_text: "Einfache Mehrheit" } }),
    );
    renderIntl(<ResolutionMajorityCheck resolutionId="01920000-0000-7000-8000-0000000a1701" />);
    await userEvent.click(screen.getByRole("button", { name: "Mehrheit prüfen" }));
    expect(await screen.findByTestId("majority-current")).toHaveTextContent("Einfache Mehrheit");
    expect(screen.getByTestId("majority-stored")).toHaveTextContent("Kein Ergebnis gespeichert");
    expect(f.mock.calls[0]![0]).toBe("/api/bff/hoa/resolutions/01920000-0000-7000-8000-0000000a1701/majority-check");
  });

  it("shows the API error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Nicht gefunden", status: 404 }, 404));
    renderIntl(<ResolutionMajorityCheck resolutionId="01920000-0000-7000-8000-0000000a1701" />);
    await userEvent.click(screen.getByRole("button"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

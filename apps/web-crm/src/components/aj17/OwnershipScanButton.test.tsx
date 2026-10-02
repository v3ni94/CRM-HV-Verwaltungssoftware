import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { OwnershipScanButton } from "./OwnershipScanButton";

describe("OwnershipScanButton (GAI-412)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("posts the scan and shows the counts", async () => {
    const f = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ events: 3, noted: 2 }));
    renderIntl(<OwnershipScanButton canEdit />);
    await userEvent.click(screen.getByRole("button", { name: "Eigentümerwechsel prüfen" }));
    expect(await screen.findByTestId("owner-scan-result")).toHaveTextContent("3 Eigentümerwechsel geprüft, 2 Prüfvermerke angelegt.");
    expect(f.mock.calls[0]![0]).toBe("/api/bff/hoa/inspection-requests/ownership-transfers/scan");
  });

  it("renders nothing without the right and shows API errors", async () => {
    const { container } = renderIntl(<OwnershipScanButton canEdit={false} />);
    expect(container).toBeEmptyDOMElement();
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ title: "Verboten", detail: "Fehlendes Recht.", status: 403 }, 403));
    renderIntl(<OwnershipScanButton canEdit />);
    await userEvent.click(screen.getByRole("button"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

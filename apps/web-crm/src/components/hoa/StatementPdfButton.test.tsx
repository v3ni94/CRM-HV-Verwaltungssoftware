import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { StatementPdfButton } from "./StatementPdfButton";

const ID = "0192abcd-0000-7000-8000-000000000077";

describe("StatementPdfButton (Q02)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("downloads the PDF from the BFF path", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({ ok: true, status: 200, blob: async () => new Blob(["%PDF"]) } as unknown as Response);
    const create = vi.fn(() => "blob:x");
    const revoke = vi.fn();
    Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    renderIntl(<StatementPdfButton statementId={ID} year={2025} version={1} />);
    await userEvent.click(screen.getByRole("button", { name: "Gesamtabrechnung als PDF" }));
    await waitFor(() => expect(click).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`/api/bff/hoa/statements/${ID}/pdf`);
    expect(revoke).toHaveBeenCalled();
  });

  it("shows the problem when the gate or the approval blocks the PDF", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ title: "Gesperrt", status: 403, code: "MHVP-GATE-0001", detail: "Freigabestufe G4 geschlossen." }, 403));
    renderIntl(<StatementPdfButton statementId={ID} year={2025} version={1} />);
    await userEvent.click(screen.getByRole("button", { name: "Gesamtabrechnung als PDF" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});

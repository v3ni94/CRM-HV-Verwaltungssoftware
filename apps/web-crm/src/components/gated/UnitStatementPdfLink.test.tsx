import { screen } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { UnitStatementPdfLink } from "./UnitStatementPdfLink";

const ST = "0192abcd-0000-7000-8000-0000000023f1";
const U1 = "0192abcd-0000-7000-8000-0000000023f2";
const units = [{ unit_id: U1, unit_number: "W1" }];

function gates(open: boolean) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([{ gate: "G4", label: "G4", open, scopes: [] }]));
}

describe("UnitStatementPdfLink (GAJ-203, G4)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("stays disabled while G4 is closed", async () => {
    gates(false);
    renderIntl(<UnitStatementPdfLink statementId={ST} units={units} approved />);
    expect(await screen.findByText(/geschlossen/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Einheit W1" })).toBeDisabled();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("links the BFF PDF path when G4 is open and the statement approved", async () => {
    gates(true);
    renderIntl(<UnitStatementPdfLink statementId={ST} units={units} approved />);
    const link = await screen.findByRole("link", { name: "Einheit W1" });
    expect(link).toHaveAttribute("href", `/api/bff/hoa/statements/${ST}/units/${U1}/pdf`);
  });

  it("stays disabled without internal approval and renders nothing without units", async () => {
    gates(true);
    const { container, unmount } = renderIntl(<UnitStatementPdfLink statementId={ST} units={units} approved={false} />);
    expect(await screen.findByText("Erst nach interner Freigabe der Abrechnung möglich.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Einheit W1" })).toBeDisabled();
    unmount();
    const empty = renderIntl(<UnitStatementPdfLink statementId={ST} units={[]} approved />);
    expect(empty.container).toBeEmptyDOMElement();
    void container;
  });
});

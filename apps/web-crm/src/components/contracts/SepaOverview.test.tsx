import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { SepaOverview, type SepaMandateRow } from "./SepaOverview";

const row = (id: string, patch: Partial<SepaMandateRow>): SepaMandateRow => ({
  id,
  party_id: `p-${id}`,
  reference: `MND-${id}`,
  iban_masked: "DE02 **** **** 2051",
  signed_at: "2025-01-01",
  type: "core",
  sequence: "first",
  valid_until: null,
  status: "active",
  last_used_at: null,
  revoked_at: null,
  ...patch,
});

const rows = [
  row("1", { valid_until: "2026-11-15", last_used_at: "2026-09-01T08:00:00Z", sequence: "recurring" }),
  row("2", { valid_until: "2028-01-01" }),
  row("3", { status: "revoked", revoked_at: "2026-05-01T08:00:00Z" }),
  row("4", { status: "expired", valid_until: "2026-03-31" }),
];

describe("SepaOverview", () => {
  it("shows all mandates with German dates and status", () => {
    renderIntl(<SepaOverview rows={rows} today="2026-09-30" />);
    expect(screen.getByTestId("sepa-count")).toHaveTextContent("4 von 4 Mandaten");
    expect(screen.getByText("15.11.2026")).toBeInTheDocument();
    expect(screen.getAllByText("Widerrufen")).toHaveLength(2);
    expect(screen.getAllByText("unbefristet")).toHaveLength(1);
  });

  it("filters by status, never used and expiry within 90 days", async () => {
    renderIntl(<SepaOverview rows={rows} today="2026-09-30" />);
    await userEvent.selectOptions(screen.getByLabelText("Status"), "revoked");
    expect(screen.getByTestId("sepa-count")).toHaveTextContent("1 von 4");
    await userEvent.selectOptions(screen.getByLabelText("Status"), "");
    await userEvent.click(screen.getByLabelText("Noch nie verwendet"));
    expect(screen.getByTestId("sepa-count")).toHaveTextContent("3 von 4");
    await userEvent.click(screen.getByLabelText("Noch nie verwendet"));
    await userEvent.click(screen.getByLabelText("Läuft innerhalb von 90 Tagen ab"));
    expect(screen.getByTestId("sepa-count")).toHaveTextContent("1 von 4");
    expect(screen.getByText("MND-1")).toBeInTheDocument();
  });

  it("searches the reference and shows an empty state", async () => {
    renderIntl(<SepaOverview rows={rows} today="2026-09-30" />);
    await userEvent.type(screen.getByLabelText("Referenz oder IBAN"), "MND-2");
    expect(screen.getByTestId("sepa-count")).toHaveTextContent("1 von 4");
    await userEvent.clear(screen.getByLabelText("Referenz oder IBAN"));
    await userEvent.type(screen.getByLabelText("Referenz oder IBAN"), "gibtesnicht");
    expect(screen.getByText("Keine Mandate für diese Auswahl.")).toBeInTheDocument();
  });
});

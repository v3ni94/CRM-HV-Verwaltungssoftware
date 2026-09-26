import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { ServiceContracts, type ServiceContract } from "./ServiceContracts";

const row: ServiceContract = {
  id: "01920000-0000-7000-8000-0000000000aa",
  provider_contact_id: "01920000-0000-7000-8000-0000000000bb",
  property_id: null,
  title: "Hausmeisterdienst",
  starts_at: "2024-01-01",
  ends_at: "2026-12-31",
  notice_period_days: 3,
  notice_period_unit: "months",
  auto_renewal_months: 12,
  cancelled_at: null,
  notes: null,
  status: "running",
  next_possible_end: "2026-12-31",
  latest_notice_date: "2026-09-30",
  orientation_only: true,
};

describe("ServiceContracts", () => {
  it("renders the empty state and the create form", () => {
    renderIntl(
      <ServiceContracts initial={[]} providers={[]} properties={[]} canCreate canUpdate={false} canDelete={false} />,
    );
    expect(screen.getByText("Noch keine Dienstleisterverträge erfasst.")).toBeInTheDocument();
    expect(screen.getByText("Dienstleistervertrag anlegen")).toBeInTheDocument();
  });

  it("renders computed dates with the orientation badge and hides the form without rights", () => {
    renderIntl(
      <ServiceContracts
        initial={[row]}
        providers={[{ id: row.provider_contact_id, label: "Muster Service GmbH" }]}
        properties={[]}
        canCreate={false}
        canUpdate={false}
        canDelete={false}
      />,
    );
    expect(screen.getByText("Muster Service GmbH")).toBeInTheDocument();
    expect(screen.getByText("30.09.2026")).toBeInTheDocument();
    expect(screen.getByText("3 Monate")).toBeInTheDocument();
    expect(screen.getByText("Laufend")).toBeInTheDocument();
    expect(screen.getByText("Orientierung, zu prüfen")).toBeInTheDocument();
    expect(screen.queryByText("Dienstleistervertrag anlegen")).not.toBeInTheDocument();
  });
});

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

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
  afterEach(() => vi.restoreAllMocks());

  it("renders the empty state and the create form", () => {
    renderIntl(
      <ServiceContracts
        initial={[]}
        providers={[]}
        properties={[]}
        canCreate
        canUpdate={false}
        canDelete={false}
      />,
    );
    expect(
      screen.getByText("Noch keine Dienstleisterverträge erfasst."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Dienstleistervertrag anlegen"),
    ).toBeInTheDocument();
  });

  it("renders computed dates with the orientation badge and hides the form without rights", () => {
    renderIntl(
      <ServiceContracts
        initial={[row]}
        providers={[
          { id: row.provider_contact_id, label: "Muster Service GmbH" },
        ]}
        properties={[]}
        canCreate={false}
        canUpdate={false}
        canDelete={false}
      />,
    );
    const table = within(screen.getByTestId("service-contracts-table"));
    expect(table.getByText("Muster Service GmbH")).toBeInTheDocument();
    expect(table.getByText("30.09.2026")).toBeInTheDocument();
    expect(table.getByText("3 Monate")).toBeInTheDocument();
    expect(table.getByText("Laufend")).toBeInTheDocument();
    expect(table.getByText("Verlängerung um 12 Monate")).toBeInTheDocument();
    // Both computed dates carry the orientation badge (next possible end and notice date).
    expect(table.getAllByText("Orientierung, zu prüfen")).toHaveLength(2);
    expect(
      screen.getByText(
        /aus Laufzeit, Kündigungsfrist und Verlängerung berechnet/,
      ),
    ).toBeInTheDocument();
    // Phone width cards carry the same content and no actions without rights.
    const cards = within(screen.getByTestId("service-contracts-cards"));
    expect(cards.getByText("Hausmeisterdienst")).toBeInTheDocument();
    expect(cards.queryByRole("button")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Dienstleistervertrag anlegen"),
    ).not.toBeInTheDocument();
  });

  it("uses singular units for a one month notice period", () => {
    renderIntl(
      <ServiceContracts
        initial={[
          { ...row, notice_period_days: 1, notice_period_unit: "months" },
        ]}
        providers={[]}
        properties={[]}
        canCreate={false}
        canUpdate={false}
        canDelete={false}
      />,
    );
    expect(
      within(screen.getByTestId("service-contracts-table")).getByText(
        "1 Monat",
      ),
    ).toBeInTheDocument();
  });

  it("rejects an end before the start without calling the API and saves a valid contract", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (input, init) => {
        if (
          String(input).endsWith("/api/bff/service-contracts") &&
          init?.method === "POST"
        ) {
          const body = JSON.parse(String(init.body)) as Record<string, unknown>;
          return jsonResponse(
            { ...row, ...body, id: "01920000-0000-7000-8000-0000000000ad" },
            201,
          );
        }
        return jsonResponse({ title: "unerwartet" }, 500);
      });
    renderIntl(
      <ServiceContracts
        initial={[]}
        providers={[
          { id: row.provider_contact_id, label: "Muster Service GmbH" },
        ]}
        properties={[]}
        canCreate
        canUpdate={false}
        canDelete={false}
      />,
    );
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Bezeichnung"), "Gartenpflege");
    await user.selectOptions(
      screen.getByLabelText("Dienstleister"),
      row.provider_contact_id,
    );
    await user.type(screen.getByLabelText("Beginn"), "2026-10-01");
    await user.type(screen.getByLabelText("Ende (optional)"), "2026-09-01");
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Das Ende darf nicht vor dem Beginn liegen.",
    );
    expect(fetchMock).not.toHaveBeenCalled();
    await user.clear(screen.getByLabelText("Ende (optional)"));
    await user.type(screen.getByLabelText("Ende (optional)"), "2027-09-30");
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(
        "Dienstleistervertrag gespeichert.",
      ),
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(
      within(screen.getByTestId("service-contracts-table")).getByText(
        "Gartenpflege",
      ),
    ).toBeInTheDocument();
  });
});

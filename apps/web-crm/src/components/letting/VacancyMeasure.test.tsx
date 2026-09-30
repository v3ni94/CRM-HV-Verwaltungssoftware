import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { VacancyMeasure } from "./VacancyMeasure";

const base = {
  unitId: "u1",
  status: "open",
  targetRent: null,
  monthlyCosts: null,
  followUpOn: null,
  note: null,
  canEdit: true,
  canCreateListing: true,
};

describe("VacancyMeasure", () => {
  afterEach(() => vi.restoreAllMocks());

  it("saves the measure with empty values as null", async () => {
    let body: unknown;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      body = JSON.parse(String(init?.body));
      return jsonResponse({ status: "viewing" });
    });
    renderIntl(<VacancyMeasure {...base} />);
    await userEvent.click(screen.getByRole("button", { name: "Maßnahme" }));
    await userEvent.selectOptions(screen.getByLabelText("Status"), "viewing");
    await userEvent.type(screen.getByLabelText("Sollmiete je Monat"), "600.00");
    await userEvent.click(screen.getByRole("button", { name: "Maßnahme speichern" }));
    await waitFor(() => expect(screen.getByText("Besichtigung")).toBeInTheDocument());
    expect(body).toEqual({
      status: "viewing",
      target_rent: "600.00",
      monthly_costs: null,
      follow_up_on: null,
      note: null,
    });
  });

  it("creates the listing draft and moves an open measure to advertised; no buttons without rights", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ id: "l1" }, 201));
    const { unmount } = renderIntl(<VacancyMeasure {...base} />);
    await userEvent.click(screen.getByRole("button", { name: "Anzeige anlegen" }));
    await waitFor(() => expect(screen.getByText("Anzeigenentwurf angelegt.")).toBeInTheDocument());
    expect(screen.getByText("inseriert")).toBeInTheDocument();
    unmount();
    renderIntl(<VacancyMeasure {...base} canEdit={false} canCreateListing={false} />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});

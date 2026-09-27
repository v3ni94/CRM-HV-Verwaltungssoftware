import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TaxSettingsAdmin, type TaxSettings } from "./TaxSettingsAdmin";

const initial: TaxSettings = {
  input_tax_enabled: false,
  input_tax_account_number: null,
  construction_withholding_enabled: false,
  construction_withholding_percent: "15.00000000",
  section_35a_enabled: false,
  approval_limits_enabled: false,
  approval_limits: [],
};
const roles = [{ code: "accountant_no_banking", name: "Buchhalter ohne Onlinebanking" }];
const PROPERTY = "01920000-0000-7000-8000-00000000c001";
const properties = [{ id: PROPERTY, number: "751", name: "Steuerhaus" }];
const contacts = [{ id: "01920000-0000-7000-8000-00000000d001", display_name: "Bau GmbH" }];

describe("TaxSettingsAdmin", () => {
  afterEach(() => vi.restoreAllMocks());

  it("saves switches and a role limit", async () => {
    let body: Record<string, unknown> | null = null;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === "/api/bff/accounting/tax/settings" && init?.method === "PUT") {
        body = JSON.parse(String(init.body)) as Record<string, unknown>;
        return jsonResponse({ ...initial, ...body });
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(
      <TaxSettingsAdmin initial={initial} roles={roles} properties={properties} contacts={contacts} canManageSettings canManageProfiles />,
    );
    const user = userEvent.setup();
    await user.click(screen.getByLabelText(/Freigabegrenzen je Rolle anwenden/));
    await user.click(screen.getByRole("button", { name: "Grenze hinzufügen" }));
    await user.selectOptions(screen.getByLabelText("Rolle"), "accountant_no_banking");
    await user.type(screen.getByLabelText("Grenze in EUR"), "500.00");
    await user.click(screen.getByRole("button", { name: "Einstellungen speichern" }));
    await waitFor(() => expect(screen.getByText("Gespeichert.")).toBeInTheDocument());
    expect(body).toMatchObject({
      approval_limits_enabled: true,
      approval_limits: [{ role_code: "accountant_no_banking", limit_amount: "500.00" }],
      construction_withholding_percent: "15.00000000",
    });
  });

  it("loads and saves a property profile, read only without rights", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/profile") && (init?.method ?? "GET") === "GET") {
        return jsonResponse({ property_id: PROPERTY, vat_opted: true, revenue_key_percent: "60.00000000", note: null });
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(
      <TaxSettingsAdmin
        initial={initial}
        roles={roles}
        properties={properties}
        contacts={contacts}
        canManageSettings={false}
        canManageProfiles={false}
      />,
    );
    expect(screen.queryByRole("button", { name: "Einstellungen speichern" })).not.toBeInTheDocument();
    const user = userEvent.setup();
    const [loadButton] = screen.getAllByRole("button", { name: "Laden" });
    if (!loadButton) throw new Error("Laden fehlt");
    await user.click(loadButton);
    await waitFor(() => expect(screen.getByLabelText("Umsatzsteueroption ausgeübt")).toBeChecked());
    expect(screen.getByLabelText("Umsatzsteueroption ausgeübt")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Objekt speichern" })).not.toBeInTheDocument();
  });
});

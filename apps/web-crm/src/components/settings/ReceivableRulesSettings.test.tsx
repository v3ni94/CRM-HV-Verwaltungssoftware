import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ReceivableRulesSettings, type ReceivableRules } from "./ReceivableRulesSettings";

const INITIAL: ReceivableRules = {
  enabled: false,
  proration_method: "calendar_days",
  vat_enabled: false,
  payment_interval: null,
};

describe("ReceivableRulesSettings", () => {
  afterEach(() => vi.restoreAllMocks());

  it("saves the tenant defaults for the receivable agent", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api/bff/tenant/settings") && init?.method === "PATCH") {
        return jsonResponse({ receivable_rules: JSON.parse(String(init.body)).receivable_rules });
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<ReceivableRulesSettings initial={INITIAL} canUpdate />);
    await userEvent.setup().click(screen.getByRole("checkbox", { name: "Sollstellungsagent für diesen Mandanten aktivieren" }));
    await userEvent.setup().selectOptions(screen.getByLabelText("Zeitanteilsregel"), "thirty_360");
    await userEvent.setup().click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(screen.getByText("Gespeichert.")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/bff/tenant/settings",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({
          receivable_rules: {
            enabled: true,
            proration_method: "thirty_360",
            vat_enabled: false,
            payment_interval: null,
          },
        }),
      }),
    );
  });

  it("saves a tenant default payment interval", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api/bff/tenant/settings") && init?.method === "PATCH") {
        return jsonResponse({ receivable_rules: JSON.parse(String(init.body)).receivable_rules });
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<ReceivableRulesSettings initial={INITIAL} canUpdate />);
    await userEvent.setup().selectOptions(screen.getByLabelText("Zahlweise"), "quarterly");
    await userEvent.setup().click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(screen.getByText("Gespeichert.")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/bff/tenant/settings",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({
          receivable_rules: {
            enabled: false,
            proration_method: "calendar_days",
            vat_enabled: false,
            payment_interval: "quarterly",
          },
        }),
      }),
    );
  });

  it("is read only without the update permission", () => {
    renderIntl(<ReceivableRulesSettings initial={INITIAL} canUpdate={false} />);
    expect(screen.getByRole("checkbox", { name: "Sollstellungsagent für diesen Mandanten aktivieren" })).toBeDisabled();
    expect(screen.getByText("Die Änderung erfordert das Recht Mandanteneinstellungen ändern.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Speichern" })).not.toBeInTheDocument();
  });
});

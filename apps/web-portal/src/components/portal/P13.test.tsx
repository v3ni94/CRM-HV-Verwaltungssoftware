import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { OwnerOverview } from "./OwnerOverview";
import { PortalChat } from "./PortalChat";
import { SupportConsent } from "./SupportConsent";

describe("PortalChat", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("shows the history and sends a message", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch)
      .mockResolvedValueOnce(
        jsonResponse([{ id: "m1", direction: "management", body: "Wir melden uns", created_at: "2026-09-30T10:00:00Z" }]),
      )
      .mockResolvedValueOnce(jsonResponse({ id: "m2", direction: "own", body: "Danke", created_at: "2026-09-30T10:05:00Z" }, 201))
      .mockResolvedValueOnce(
        jsonResponse([
          { id: "m1", direction: "management", body: "Wir melden uns", created_at: "2026-09-30T10:00:00Z" },
          { id: "m2", direction: "own", body: "Danke", created_at: "2026-09-30T10:05:00Z" },
        ]),
      );
    renderIntl(<PortalChat ticketId="t1" />);
    expect(await screen.findByText("Wir melden uns")).toBeInTheDocument();
    expect(screen.getByText(/kein Notdienst/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Ihre Nachricht"), "Danke");
    await user.click(screen.getByRole("button", { name: "Nachricht senden" }));
    expect(await screen.findByText("Danke")).toBeInTheDocument();
    const post = vi.mocked(fetch).mock.calls.at(1);
    expect(String(post?.[0])).toBe("/api/bff/portal/tickets/t1/messages");
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ body: "Danke" });
  });
});

describe("OwnerOverview", () => {
  it("lists payments with validity and the note, and shows empty states", () => {
    renderIntl(
      <OwnerOverview
        note="Information, keine Zahlung."
        tickets={[]}
        payments={[
          {
            resolution_id: "r1",
            number: 3,
            decided_on: "2026-05-15",
            subject: "Sonderumlage Dach",
            kind: "special_levy",
            legal_entity_name: "WEG",
            valid_from: "2026-07-01",
            valid_to: null,
            rhythm: null,
            due_day: null,
            instalments: 3,
            total: "12000.00",
            purpose: "Dachsanierung",
            sepa: null,
          },
        ]}
      />,
    );
    expect(screen.getByText("Information, keine Zahlung.")).toBeInTheDocument();
    expect(screen.getByText(/Sonderumlage Dach/)).toBeInTheDocument();
    expect(screen.getByText(/12\.000,00 EUR/)).toBeInTheDocument();
    expect(screen.getByText("Keine für Eigentümer freigegebenen Meldungen.")).toBeInTheDocument();
  });

  it("shows the own share, allocation properties and rental income (M21-06, SA-05)", () => {
    renderIntl(
      <OwnerOverview
        note="n"
        tickets={[]}
        payments={[
          {
            resolution_id: "r2",
            number: 4,
            decided_on: "2026-05-15",
            subject: "Wirtschaftsplan 2027",
            kind: "economic_plan",
            legal_entity_name: "WEG",
            valid_from: "2027-01-01",
            valid_to: null,
            rhythm: "monthly",
            due_day: 3,
            instalments: null,
            total: null,
            purpose: null,
            sepa: null,
            own_share: [{ unit_number: "01", annual: { hoa_fee: "1200.00" }, monthly: { hoa_fee: "100.00" } }],
          },
        ]}
        allocations={[
          {
            unit_id: "u1",
            unit_number: "01",
            property_name: "WEG Musterstraße",
            keys: [{ code: "MEA", name: "Miteigentumsanteile", unit_of_measure: "/1000", kind: "static", value: "125.0000" }],
          },
        ]}
        income={[
          {
            property_id: "p1",
            property_name: "WEG Musterstraße",
            total_gross: "650.00",
            units: [{ unit_number: "01", gross: "650.00", components: [] }],
          },
        ]}
      />,
    );
    expect(screen.getByTestId("owner-share")).toHaveTextContent(/100,00 EUR/);
    expect(screen.getByText("Umlageeigenschaften")).toBeInTheDocument();
    expect(screen.getByText(/Miteigentumsanteile: 125.0000/)).toBeInTheDocument();
    expect(screen.getByText(/650,00 EUR je Monat/)).toBeInTheDocument();
  });
});

describe("SupportConsent", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("grants and revokes the consent", async () => {
    const user = userEvent.setup();
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ active: true, expires_at: "2026-10-01T10:00:00Z" }, 201))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    renderIntl(<SupportConsent initial={{ active: false, expires_at: null }} />);
    await user.click(screen.getByRole("button", { name: "Einwilligung erteilen" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Die Verwaltung darf lesend Einsicht nehmen");
    await user.click(screen.getByRole("button", { name: "Einwilligung widerrufen" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Einwilligung erteilen" })).toBeInTheDocument());
  });
});

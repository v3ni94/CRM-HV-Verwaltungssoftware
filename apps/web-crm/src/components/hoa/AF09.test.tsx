import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MeetingDisruptions } from "./MeetingDisruptions";
import { MeetingInvitationRecipients } from "./MeetingInvitationRecipients";
import { ReserveOpeningChanges } from "./ReserveOpeningChanges";
import { StatementCorrectionReport } from "./StatementCorrectionReport";
import { StatementCostsFromLedger } from "./StatementCostsFromLedger";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));
const ID = "0192abcd-0000-7000-8000-000000000090";

describe("AF09 Versammlung und Abrechnung", () => {
  afterEach(() => vi.restoreAllMocks());

  it("zeigt Empfänger mit Vertretung", () => {
    renderIntl(
      <MeetingInvitationRecipients
        rows={[{ contract_id: ID, unit_number: "3", party_name: "Meier", recipients: [{ contact_id: "c1", display_name: "Anna Verwalter", channel: "post", represents_name: "Meier" }] }]}
      />,
    );
    expect(screen.getByText(/Anna Verwalter/)).toHaveTextContent("für Meier");
  });

  it("verlangt Beschreibung und Zeitpunkt für eine Störung und sendet sie", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ id: ID }, 201));
    renderIntl(<MeetingDisruptions meetingId={ID} rows={[]} closed={false} />);
    await userEvent.click(screen.getByRole("button", { name: "Eintrag speichern" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bitte Beschreibung und Zeitpunkt angeben.");
    expect(fetchMock).not.toHaveBeenCalled();
    await userEvent.type(screen.getByLabelText("Beschreibung"), "Ton ausgefallen");
    await userEvent.type(screen.getByLabelText("Zeitpunkt"), "2026-10-01T10:00");
    await userEvent.click(screen.getByRole("button", { name: "Eintrag speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(`/api/bff/hoa/meetings/${ID}/disruptions`);
  });

  it("zeigt den Korrekturbericht", () => {
    const tri = { old: "10.00", new: "12.00", difference: "2.00" };
    renderIntl(
      <StatementCorrectionReport
        report={{ old: { version: 1 }, new: { version: 2 }, owners: [{ owner: "Meier", units: ["3"], cost_share: tri, advances_resolved: tri, result: tri }], correction: { reason: "Fehler", basis: "Beschluss", legal_note: "Hinweis" } }}
      />,
    );
    expect(screen.getByTestId("correction-report")).toHaveTextContent("Meier");
  });

  it("übernimmt Kosten aus dem Hauptbuch", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ created: [{}], skipped: [{ journal_entry_id: "e1", reason: "net_credit" }] }, 201));
    renderIntl(<StatementCostsFromLedger statementId={ID} accounts={[{ id: "a1", number: "4000", name: "Strom" }]} keys={[{ id: "k1", name: "MEA" }]} />);
    await userEvent.selectOptions(screen.getByLabelText("Kostenkonto"), "a1");
    await userEvent.selectOptions(screen.getByLabelText("Verteilerschlüssel"), "k1");
    await userEvent.type(screen.getByLabelText("Verteilungsgrundlage"), "Beschluss 3");
    await userEvent.click(screen.getByRole("button", { name: "Positionen übernehmen" }));
    expect(await screen.findByRole("status")).toHaveTextContent("1 Positionen übernommen.");
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(`/api/bff/hoa/statements/${ID}/costs/from-ledger`);
  });

  it("gibt Eröffnungsänderung frei", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse({ id: ID }));
    renderIntl(<ReserveOpeningChanges name="Instandhaltung" rows={[{ id: ID, status: "pending", reason: "Korrektur", changes: { opening_balance: { old: "1.00", new: "2.00" } }, requested_at: "2026-10-01T10:00:00Z" }]} />);
    await userEvent.click(screen.getByRole("button", { name: "Freigeben" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(`/api/bff/hoa/reserve-opening-changes/${ID}/approve`);
  });
});

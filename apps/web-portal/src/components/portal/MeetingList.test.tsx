import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { MeetingList } from "./MeetingList";
import type { PortalMeeting } from "./types";

const row: PortalMeeting = {
  id: "m1",
  legal_entity_name: "WEG Portalstraße 5",
  kind: "ordinary",
  mode: "virtual",
  mode_label: "Virtuell",
  scheduled_at: "2026-11-05T18:00:00+01:00",
  location: null,
  status: "invited",
  invited_at: "2026-10-10",
  notice: "Die Versammlung findet als virtuelle Versammlung statt.",
  dial_in_url: "https://meet.example.org/weg",
  dial_in_access: "PIN 1234",
  dial_in_note: "Zugangsdaten nur für Eigentümer.",
};

describe("MeetingList", () => {
  it("renders form, notice and dial-in data when the API delivers them", () => {
    renderIntl(<MeetingList rows={[row]} />);
    expect(screen.getByTestId("portal-meeting")).toHaveTextContent("Virtuell");
    expect(screen.getByTestId("dial-in")).toHaveTextContent("PIN 1234");
    expect(screen.getByRole("link", { name: "https://meet.example.org/weg" })).toHaveAttribute("href", "https://meet.example.org/weg");
  });

  it("shows no dial-in block without data and the empty notice without rows", () => {
    renderIntl(<MeetingList rows={[{ ...row, mode: "presence", dial_in_url: null, dial_in_access: null, dial_in_note: null, notice: null }]} />);
    expect(screen.queryByTestId("dial-in")).toBeNull();
    renderIntl(<MeetingList rows={[]} />);
    expect(screen.getByText("Keine Versammlungen vorhanden.")).toBeInTheDocument();
  });

  it("shows the public description (GA03-01)", () => {
    renderIntl(<MeetingList rows={[{ ...row, public_description: "Bitte Unterlagen mitbringen." }]} />);
    expect(screen.getByTestId("meeting-description")).toHaveTextContent("Unterlagen mitbringen");
  });
});

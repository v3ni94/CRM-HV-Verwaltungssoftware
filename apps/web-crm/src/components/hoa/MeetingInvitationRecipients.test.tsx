import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { MeetingInvitationRecipients } from "./MeetingInvitationRecipients";

describe("MeetingInvitationRecipients", () => {
  it("lists recipients with channel and represented owner", () => {
    renderIntl(
      <MeetingInvitationRecipients
        rows={[
          {
            contract_id: "k1",
            unit_number: "WE 01",
            party_name: "Erika Beispiel",
            recipients: [{ contact_id: "c1", display_name: "Max Vertreter", channel: "post", represents_name: "Erika Beispiel" }],
          },
        ]}
      />,
    );
    expect(screen.getByTestId("invitation-recipients")).toBeInTheDocument();
    expect(screen.getByText("WE 01")).toBeInTheDocument();
    expect(screen.getByText(/Max Vertreter/)).toBeInTheDocument();
    expect(screen.getByText(/post/)).toBeInTheDocument();
  });

  it("shows the none hint without rows", () => {
    renderIntl(<MeetingInvitationRecipients rows={[]} />);
    expect(screen.queryByRole("table")).toBeNull();
  });
});

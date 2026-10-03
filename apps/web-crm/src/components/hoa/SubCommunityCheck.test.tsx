import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { SubCommunityCheck } from "./SubCommunityCheck";

const ISSUE = { cost_item_id: "c1", label: "Aufzug Haus 1", amount: "1000.00", sub_community_id: "s1" };

describe("SubCommunityCheck (AP21, GAM-109)", () => {
  it("shows a hint without lock by default", () => {
    renderIntl(<SubCommunityCheck data={{ lock_active: false, blocks_internal_approval: false, issues: [ISSUE], note: "AP21-01" }} names={{ s1: "H1 Haus 1" }} />);
    expect(screen.getByText(/Prüfhinweis/)).toBeInTheDocument();
    expect(screen.getByTestId("sub-community-check")).toHaveTextContent("H1 Haus 1");
  });

  it("shows the lock when the switch is on", () => {
    renderIntl(<SubCommunityCheck data={{ lock_active: true, blocks_internal_approval: true, issues: [ISSUE], note: "" }} names={{}} />);
    expect(screen.getByText(/Interne Freigabe gesperrt/)).toBeInTheDocument();
    expect(screen.getByTestId("sub-community-check")).toHaveTextContent("s1");
  });

  it("renders nothing without issues", () => {
    const { container } = renderIntl(<SubCommunityCheck data={{ lock_active: true, blocks_internal_approval: false, issues: [], note: "" }} names={{}} />);
    expect(container).toBeEmptyDOMElement();
  });
});

import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { APPROVAL_LINKS, ApprovalsColumn } from "./ApprovalsColumn";

describe("ApprovalsColumn (GAI-615)", () => {
  it("says so when the caller may decide no kind", () => {
    renderIntl(<ApprovalsColumn counts={{}} />);
    expect(screen.queryByTestId("approval-mail")).not.toBeInTheDocument();
    expect(screen.getByTestId("approvals-column").querySelector("ul")).toBeNull();
  });

  it("says so when nothing is pending", () => {
    renderIntl(<ApprovalsColumn counts={{ mail: 0, release_gates: 0 }} />);
    expect(screen.getByTestId("approvals-column").querySelector("ul")).toBeNull();
  });

  it("shows only pending kinds with count and target, in the fixed order", () => {
    renderIntl(<ApprovalsColumn counts={{ release_gates: 2, mail: 1234, dunning_runs: 0 }} />);
    const items = screen.getAllByTestId(/^approval-/);
    expect(items.map((i) => i.getAttribute("data-testid"))).toEqual(["approval-mail", "approval-release_gates"]);
    expect(items[0]!.querySelector("a")).toHaveAttribute("href", APPROVAL_LINKS.mail);
    expect(items[0]).toHaveTextContent("1.234");
    expect(screen.queryByTestId("approval-dunning_runs")).not.toBeInTheDocument();
  });
});

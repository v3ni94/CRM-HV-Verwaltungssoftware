import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { reasoningOf } from "@/lib/ai";
import { renderIntl } from "@/test/intl";

import { ProposalBadge } from "./ProposalBadge";

describe("ProposalBadge", () => {
  it("labels the output as proposal with confidence and a Warum disclosure", async () => {
    const reasoning = reasoningOf({ answer: "x", sources: [{ document_id: "0192abcd-0000", excerpt: "Hausgeld 250 EUR" }], open_points: ["Belege fehlen"] });
    renderIntl(<ProposalBadge confidence="0.87" reasoning={reasoning} />);
    expect(screen.getByTestId("proposal-badge")).toHaveTextContent("Vorschlag");
    expect(screen.getByText("Sicherheit 87 %")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Warum?"));
    expect(screen.getByText("Hausgeld 250 EUR")).toBeVisible();
    expect(screen.getByText("Belege fehlen")).toBeVisible();
  });
});

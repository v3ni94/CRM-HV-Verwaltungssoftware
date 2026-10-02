import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { ResolutionList } from "./ResolutionList";
import type { PortalResolution } from "./types";

const row: PortalResolution = {
  id: "r1",
  number: 3,
  decided_on: "2026-05-04",
  subject: "Dachsanierung",
  wording: "Die Eigentümer beschließen die Sanierung.",
  status: "positive",
  kind: "meeting",
  majority_basis: "einfache Mehrheit",
  votes: { principle: null, yes: "7", no: "2", abstain: "1" },
  legal_entity_name: null,
};

describe("ResolutionList", () => {
  it("shows an empty notice without rows", () => {
    renderIntl(<ResolutionList rows={[]} />);
    expect(screen.queryByRole("list")).toBeNull();
    expect(screen.getByText(/\S/)).toBeInTheDocument();
  });

  it("renders subject, wording, TT.MM.JJJJ date and majority basis", () => {
    renderIntl(<ResolutionList rows={[row]} />);
    const item = screen.getByRole("listitem");
    expect(item.textContent).toContain("Dachsanierung");
    expect(item.textContent).toContain("Die Eigentümer beschließen die Sanierung.");
    expect(item.textContent).toContain("04.05.2026");
    expect(item.textContent).toContain("einfache Mehrheit");
  });

  it("shows unknown status and kind codes as they are instead of failing", () => {
    renderIntl(<ResolutionList rows={[{ ...row, status: "future_status", kind: "future_kind", votes: null, majority_basis: null }]} />);
    const item = screen.getByRole("listitem");
    expect(item.textContent).toContain("future_status");
    expect(item.textContent).toContain("future_kind");
  });
});

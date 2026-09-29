import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { HandoverList, currentWeek } from "./HandoverList";
import type { Protocol } from "./types";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh: vi.fn() }),
  usePathname: () => "/makler/uebergabe",
  useSearchParams: () => new URLSearchParams(),
}));

const row = {
  id: "0192abcd-0000-7000-8000-000000000060",
  number: "UP-20260925-001",
  version: 2,
  status: "in_progress",
  kind: "rental",
  address: "Musterweg 12, 40789 Monheim am Rhein",
  unit_number: "03",
  unit_label: "links",
  participants_summary: "Alt, Neu GmbH",
  handover_date: "2026-09-25",
  finalized: false,
  locked: false,
  ticket_number: null,
} as unknown as Protocol;
const params = { q: "", status: "", art: "", archiv: false, datum: "", von: "", bis: "" };

describe("HandoverList", () => {
  beforeEach(() => push.mockReset());

  it("renders cards below sm and the table from sm", () => {
    renderIntl(<HandoverList rows={[row]} params={params} />);
    const cards = screen.getByTestId("handover-cards");
    expect(cards.className).toContain("sm:hidden");
    const card = within(cards).getByTestId("handover-card");
    expect(card).toHaveTextContent("UP-20260925-001 V2");
    expect(card).toHaveTextContent("In Bearbeitung");
    expect(card).toHaveTextContent("Musterweg 12");
    expect(card).toHaveTextContent("Alt, Neu GmbH");
    expect(card).toHaveTextContent("25.09.2026");
    expect(within(card).getByRole("link")).toHaveAttribute("href", `/makler/uebergabe/${row.id}`);
    const table = screen.getByTestId("handover");
    expect(table.className).toContain("sm:block");
    expect(within(table).getByRole("table")).toBeInTheDocument();
  });

  it("folds the filters and sets handover_date with the today chip", async () => {
    renderIntl(<HandoverList rows={[row]} params={params} />);
    expect(screen.getByTestId("filters-panel").className).toContain("hidden");
    await userEvent.click(screen.getByTestId("filters-toggle"));
    expect(screen.getByTestId("filters-panel").className).not.toContain("hidden");
    await userEvent.click(screen.getByTestId("chip-today"));
    const today = new Date();
    const iso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
    expect(push).toHaveBeenCalledWith(`/makler/uebergabe?datum=${iso}`);
    await userEvent.click(screen.getByTestId("chip-week"));
    const week = currentWeek();
    expect(push).toHaveBeenLastCalledWith(`/makler/uebergabe?von=${week.from}&bis=${week.to}`);
  });

  it("computes Monday to Sunday of the current week", () => {
    expect(currentWeek(new Date(2026, 8, 30))).toEqual({ from: "2026-09-28", to: "2026-10-04" });
    expect(currentWeek(new Date(2026, 9, 4))).toEqual({ from: "2026-09-28", to: "2026-10-04" });
  });
});

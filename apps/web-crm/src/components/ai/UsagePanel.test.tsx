import { screen } from "@testing-library/react";

import type { Usage } from "@/lib/ai";
import { renderIntl } from "@/test/intl";

import { UsagePanel } from "./UsagePanel";

describe("UsagePanel", () => {
  it("labels known tasks from the catalogue and shows unknown task codes as they are", () => {
    const usage = {
      month: "2026-09",
      spent_eur: "12.50",
      budget_eur: "50.00",
      warning: false,
      blocked: false,
      by_task: { extract_invoice: "10.00", summarize: "2.00", future_task: "0.50" },
    } as unknown as Usage;
    renderIntl(<UsagePanel usage={usage} />);
    const items = screen.getAllByRole("listitem").map((li) => li.textContent);
    expect(items[0]).toMatch(/^Rechnungserkennung: 10,00/);
    expect(items[1]).toMatch(/^Zusammenfassung: 2,00/);
    expect(items[2]).toMatch(/^future_task: 0,50/);
  });

  it("shows runs and tokens per task when the API delivers them (M7-09)", () => {
    const usage = {
      month: "2026-09",
      spent_eur: "1.00",
      budget_eur: "50.00",
      warning: false,
      blocked: false,
      by_task: { summarize: "1.00" },
      runs_by_task: { summarize: 3 },
      tokens_in_by_task: { summarize: 1000 },
      tokens_out_by_task: { summarize: 200 },
    } as unknown as Usage;
    renderIntl(<UsagePanel usage={usage} />);
    expect(screen.getByRole("listitem").textContent).toMatch(/3 Läufe, 1200 Token|3 Läufe, 1\.200 Token/);
  });
});

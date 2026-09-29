import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import type { DeadlineEntry } from "./DeadlineCreatePanel";
import { DeadlineEntriesPanel } from "./DeadlineEntriesPanel";

const ENTRY: DeadlineEntry = {
  id: "01920000-0000-7000-8000-0000000000e2",
  type_id: "t",
  type_name: "Verwalterwechsel",
  title: "Verwalterwechsel Objekt 101 Testhaus",
  trigger_on: "2026-10-01",
  due_on: "2026-10-31",
  due_computed: false,
  verify: true,
  responsible_user_id: null,
  responsible_name: null,
  source_type: "property",
  source_id: "01920000-0000-7000-8000-0000000000p1",
  href: "/objekte/01920000-0000-7000-8000-0000000000p1",
  status: "open",
  done_at: null,
  warnings: ["ES-10"],
};

describe("DeadlineEntriesPanel", () => {
  const calls: { url: string; method: string }[] = [];
  beforeEach(() => {
    calls.length = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push({ url, method });
      if (url.endsWith("/done")) return jsonResponse({ ...ENTRY, status: "done" });
      return jsonResponse([ENTRY]);
    });
  });
  afterEach(() => vi.restoreAllMocks());

  it("renders the table with source link, ES-10 hint and the types link", async () => {
    renderIntl(<DeadlineEntriesPanel canUpdate canManageTypes />);
    expect(await screen.findByText("Verwalterwechsel Objekt 101 Testhaus")).toBeInTheDocument();
    expect(screen.getByText("31.10.2026")).toBeInTheDocument();
    expect(screen.getByText("ohne Verantwortlichen (ES-10)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Zur Quelle" })).toHaveAttribute("href", ENTRY.href);
    expect(screen.getByRole("link", { name: "Fristtypen pflegen" })).toHaveAttribute("href", "/einstellungen/fristtypen");
    expect(calls[0]!.url).toContain("status=open");
  });

  it("finishes an entry and reloads with done entries when requested", async () => {
    renderIntl(<DeadlineEntriesPanel canUpdate={false} canManageTypes={false} />);
    await screen.findByText("Verwalterwechsel Objekt 101 Testhaus");
    expect(screen.queryByRole("button", { name: "Erledigt" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Fristtypen pflegen" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByTestId("entries-show-done"));
    await waitFor(() => expect(calls.some((c) => c.url.includes("status=all"))).toBe(true));
  });
});

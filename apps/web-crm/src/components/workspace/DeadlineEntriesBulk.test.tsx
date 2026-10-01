import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import type { DeadlineEntry } from "./DeadlineCreatePanel";
import { DeadlineEntriesPanel } from "./DeadlineEntriesPanel";

const base = {
  type_id: "t",
  type_name: "Verwalterwechsel",
  trigger_on: "2026-10-01",
  due_on: "2026-10-31",
  due_computed: false,
  verify: true,
  responsible_user_id: null,
  responsible_name: null,
  source_type: "property",
  source_id: "s",
  href: null,
  done_at: null,
  warnings: [],
} satisfies Partial<DeadlineEntry>;
const A: DeadlineEntry = { ...base, id: "e1", title: "Frist A", status: "open" };
const B: DeadlineEntry = { ...base, id: "e2", title: "Frist B", status: "open" };

describe("DeadlineEntriesPanel bulk action (M9-04)", () => {
  const posts: { url: string; body: Record<string, unknown> }[] = [];
  beforeEach(() => {
    posts.length = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      if (init?.method === "POST") {
        posts.push({ url: String(input), body: JSON.parse(String(init.body)) as Record<string, unknown> });
        return jsonResponse({ changed: 2 });
      }
      return jsonResponse([A, B]);
    });
  });
  afterEach(() => vi.restoreAllMocks());

  it("finishes the selected deadlines in one call", async () => {
    renderIntl(<DeadlineEntriesPanel canUpdate canManageTypes={false} />);
    await screen.findByText("Frist A");
    await userEvent.click(screen.getByTestId("entry-select-e1"));
    await userEvent.click(screen.getByTestId("entry-select-e2"));
    await userEvent.click(screen.getByTestId("entries-bulk-done"));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]!.url).toBe("/api/bff/workspace/bulk");
    expect(posts[0]!.body).toEqual({ action: "deadline_entries.done", ids: ["e1", "e2"] });
    expect(await screen.findByText("2 Fristen erledigt.")).toBeInTheDocument();
  });

  it("reports an empty selection and offers no selection without update permission", async () => {
    renderIntl(<DeadlineEntriesPanel canUpdate canManageTypes={false} />);
    await screen.findByText("Frist A");
    await userEvent.click(screen.getByTestId("entries-bulk-done"));
    expect(await screen.findByText("Keine Fristen markiert.")).toBeInTheDocument();
    expect(posts).toHaveLength(0);
  });

  it("hides selection and bulk button for read only users", async () => {
    renderIntl(<DeadlineEntriesPanel canUpdate={false} canManageTypes={false} />);
    await screen.findByText("Frist A");
    expect(screen.queryByTestId("entries-bulk-done")).not.toBeInTheDocument();
    expect(screen.queryByTestId("entry-select-e1")).not.toBeInTheDocument();
  });
});

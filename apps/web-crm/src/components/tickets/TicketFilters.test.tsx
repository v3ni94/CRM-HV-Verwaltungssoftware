import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TicketFilters } from "./TicketFilters";

const push = vi.fn();
let currentParams = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => currentParams,
}));

describe("TicketFilters", () => {
  beforeEach(() => {
    push.mockClear();
    currentParams = new URLSearchParams();
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url.includes("/tenant/members"))
        return jsonResponse([{ user_id: "u1", display_name: "Anna Beispiel" }]);
      if (url.includes("/units")) return jsonResponse([]);
      if (url.includes("/properties"))
        return jsonResponse({
          items: [{ id: "p1", number: "001", name: "Objekt Eins" }],
        });
      return jsonResponse([]);
    });
  });
  afterEach(() => vi.restoreAllMocks());

  it("reflects the URL's initial filter values", async () => {
    currentParams = new URLSearchParams({ status: "new", mine: "1" });
    renderIntl(<TicketFilters meUserId="u1" />);
    expect(await screen.findByTestId("filter-status")).toHaveValue("new");
    expect(screen.getByTestId("filter-mine")).toHaveAttribute(
      "aria-checked",
      "true",
    );
  });

  it("pushes q to the URL after debouncing", async () => {
    renderIntl(<TicketFilters meUserId="u1" />);
    await userEvent.type(screen.getByTestId("filter-q"), "Heizung");
    await waitFor(() => expect(push).toHaveBeenCalled(), { timeout: 2000 });
    const last = push.mock.calls.at(-1)?.[0] as string;
    expect(last).toContain("q=Heizung");
  });

  it("sets mine and the current user as assignee", async () => {
    renderIntl(<TicketFilters meUserId="u42" />);
    await userEvent.click(screen.getByTestId("filter-mine"));
    expect(push).toHaveBeenCalledWith(expect.stringContaining("mine=1"));
    expect(push).toHaveBeenCalledWith(
      expect.stringContaining("assignee_user_id=u42"),
    );
  });

  it("resets all filters", async () => {
    currentParams = new URLSearchParams({ status: "new", property_id: "p1" });
    renderIntl(<TicketFilters meUserId="u1" />);
    await userEvent.click(screen.getByTestId("filter-reset"));
    expect(push).toHaveBeenCalledWith("/tickets");
  });

  it("toggles erledigt=1 and keeps other filters", async () => {
    currentParams = new URLSearchParams({ status: "new", page: "3" });
    renderIntl(<TicketFilters meUserId="u1" />);
    const toggle = await screen.findByTestId("filter-closed");
    expect(toggle).toHaveAttribute("aria-checked", "false");
    expect(toggle).toHaveTextContent("Erledigte anzeigen");
    await userEvent.click(toggle);
    expect(push).toHaveBeenLastCalledWith("/tickets?status=new&erledigt=1");
  });

  it("removes erledigt when switched off", async () => {
    currentParams = new URLSearchParams({ erledigt: "1" });
    renderIntl(<TicketFilters meUserId="u1" />);
    const toggle = await screen.findByTestId("filter-closed");
    expect(toggle).toHaveAttribute("aria-checked", "true");
    await userEvent.click(toggle);
    expect(push).toHaveBeenLastCalledWith("/tickets");
  });

  it("switches the sort to created_desc with the toggle Nach Eingang and back to urgency", async () => {
    currentParams = new URLSearchParams({ status: "new", page: "2" });
    renderIntl(<TicketFilters meUserId="u1" />);
    const toggle = await screen.findByTestId("filter-sort-created");
    expect(toggle).toHaveAttribute("aria-checked", "false");
    expect(toggle).toHaveTextContent("Nach Eingang");
    await userEvent.click(toggle);
    expect(push).toHaveBeenLastCalledWith(
      "/tickets?status=new&sort=created_desc",
    );
  });

  it("keeps the sort when another filter changes", async () => {
    currentParams = new URLSearchParams({ sort: "created_desc" });
    renderIntl(<TicketFilters meUserId="u1" />);
    const toggle = await screen.findByTestId("filter-sort-created");
    expect(toggle).toHaveAttribute("aria-checked", "true");
    await userEvent.selectOptions(
      await screen.findByTestId("filter-status"),
      "new",
    );
    expect(push).toHaveBeenLastCalledWith(
      "/tickets?status=new&sort=created_desc",
    );
    await userEvent.click(toggle);
    expect(push).toHaveBeenLastCalledWith("/tickets");
  });
  it("keeps the filters collapsed until the toggle is used (operator 27.09.2026)", async () => {
    renderIntl(<TicketFilters meUserId="u1" />);
    expect(screen.getByTestId("filters-panel").className).toContain("hidden");
    await userEvent.click(screen.getByTestId("filters-toggle"));
    await waitFor(() =>
      expect(screen.getByTestId("filters-panel").className).not.toContain(
        "hidden",
      ),
    );
  });
});

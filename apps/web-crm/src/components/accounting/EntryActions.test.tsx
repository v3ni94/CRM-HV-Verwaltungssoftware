import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { EntryActions } from "./EntryActions";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const base = "/api/bff/accounting/ledgers/l1/entries/e1";
const draft = { id: "e1", status: "draft", kind: "manual" };

describe("EntryActions", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    refresh.mockReset();
  });

  it("shows no actions without permission", () => {
    renderIntl(<EntryActions ledgerId="l1" entry={draft} canCreate={false} canApprove={false} />);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("posts a draft after confirmation and refreshes", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<EntryActions ledgerId="l1" entry={draft} canCreate canApprove={false} />);
    const [post] = screen.getAllByRole("button");
    await act(async () => {
      await userEvent.click(post as HTMLElement);
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`${base}/post`);
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("POST");
    expect(refresh).toHaveBeenCalled();
  });

  it("blocks posting an opening balance until a second person approved it", () => {
    renderIntl(<EntryActions ledgerId="l1" entry={{ id: "e1", status: "draft", kind: "opening_balance" }} canCreate canApprove={false} />);
    expect(screen.getAllByRole("button").some((b) => (b as HTMLButtonElement).disabled)).toBe(true);
  });

  it("offers approval to an approver of an unapproved opening balance", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<EntryActions ledgerId="l1" entry={{ id: "e1", status: "draft", kind: "opening_balance" }} canCreate canApprove />);
    await act(async () => {
      await userEvent.click(screen.getAllByRole("button")[0] as HTMLElement);
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe(`${base}/approve`);
  });

  it("does not call the API when the confirmation is declined", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<EntryActions ledgerId="l1" entry={draft} canCreate canApprove={false} />);
    await userEvent.click(screen.getAllByRole("button")[0] as HTMLElement);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the API error when deleting a draft is refused (403)", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403)));
    renderIntl(<EntryActions ledgerId="l1" entry={draft} canCreate canApprove={false} />);
    const buttons = screen.getAllByRole("button");
    await act(async () => {
      await userEvent.click(buttons[buttons.length - 1] as HTMLElement);
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled();
  });
});

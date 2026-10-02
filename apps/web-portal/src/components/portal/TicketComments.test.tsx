import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { TicketComments } from "./TicketComments";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh }) }));

describe("TicketComments", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    refresh.mockReset();
  });

  it("lists existing comments", () => {
    renderIntl(<TicketComments ticketId="t1" comments={["Erster", "Zweiter"]} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("does not post an empty comment", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<TicketComments ticketId="t1" comments={[]} />);
    await userEvent.click(screen.getByRole("button"));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("posts a trimmed comment to the portal ticket path and refreshes", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: "c1" }));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<TicketComments ticketId="t1" comments={[]} />);
    await userEvent.type(screen.getByRole("textbox"), "  Hallo  ");
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/portal/tickets/t1/comments");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ body: "Hallo" });
    expect(await screen.findByRole("status")).toBeInTheDocument();
    expect(refresh).toHaveBeenCalled();
  });

  it("shows the error for a refused comment (403)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403)));
    renderIntl(<TicketComments ticketId="t1" comments={[]} />);
    await userEvent.type(screen.getByRole("textbox"), "Hallo");
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled();
  });
});

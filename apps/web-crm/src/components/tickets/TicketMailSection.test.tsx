import { screen } from "@testing-library/react";

import { jsonResponse, messages, renderIntl } from "@/test/intl";

import { TicketMailSection } from "./TicketMailSection";

vi.mock("@/components/mail/CompactView", () => ({ CompactView: ({ messageId }: { messageId: string }) => <div data-testid="compact">{messageId}</div> }));
vi.mock("@/components/tickets/TicketMailThread", () => ({
  TicketMailThread: ({ messages }: { messages: { id: string }[] }) => <div data-testid="thread">{messages.map((x) => x.id).join(",")}</div>,
}));
vi.mock("@/components/tickets/TicketReplyPanel", () => ({
  TicketReplyPanel: ({ canSend, ticketId }: { canSend: boolean; ticketId: string }) => <div data-testid="reply">{`${ticketId}:${canSend}`}</div>,
}));

const m = messages.Tickets.mailThread;

describe("TicketMailSection", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads the thread and builds the compact view from the latest inbound mail", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse([
        { id: "m1", direction: "in" },
        { id: "m2", direction: "out" },
        { id: "m3", direction: "in" },
        { id: "m4", direction: "out" },
      ]),
    );
    renderIntl(<TicketMailSection ticketId="t1" canReply />);
    expect(await screen.findByTestId("thread")).toHaveTextContent("m1,m2,m3,m4");
    expect(String(fetchMock.mock.calls[0]![0])).toBe("/api/bff/tickets/t1/messages");
    expect(screen.getByTestId("compact")).toHaveTextContent("m3");
    expect(screen.getByTestId("reply")).toHaveTextContent("t1:true");
    expect(screen.getByRole("heading", { name: m.title })).toBeInTheDocument();
  });

  it("shows no compact view without inbound mail and passes canReply=false on", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([{ id: "m2", direction: "out" }]));
    renderIntl(<TicketMailSection ticketId="t1" canReply={false} />);
    await screen.findByTestId("thread");
    expect(screen.queryByTestId("compact")).toBeNull();
    expect(screen.getByTestId("reply")).toHaveTextContent("t1:false");
  });

  it("shows the load error and an empty thread when loading fails", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ title: "Fehler", status: 500 }, 500));
    renderIntl(<TicketMailSection ticketId="t1" canReply />);
    expect(await screen.findByRole("alert")).toHaveTextContent(m.loadFailed);
    expect(screen.getByTestId("thread")).toBeEmptyDOMElement();
  });
});

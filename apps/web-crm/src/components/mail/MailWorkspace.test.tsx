import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MailWorkspace } from "./MailWorkspace";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));

describe("MailWorkspace Erledigte anzeigen", () => {
  let fetchMock: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    window.history.replaceState(null, "", "/mail");
    fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse([]));
  });
  afterEach(() => vi.restoreAllMocks());

  const messageUrls = () =>
    fetchMock.mock.calls.map((c: unknown[]) => String(c[0])).filter((u: string) => u.includes("/mail/messages?"));

  it("hides done mails by default and requests include_closed when switched on", async () => {
    renderIntl(<MailWorkspace canApprove={false} canReadMembers={false} />);
    await waitFor(() => expect(messageUrls().length).toBeGreaterThan(0));
    expect(messageUrls().every((u: string) => !u.includes("include_closed"))).toBe(true);

    await userEvent.click(screen.getByLabelText("Erledigte anzeigen"));
    await waitFor(() => expect(messageUrls().at(-1)).toContain("include_closed=true"));
    expect(window.location.search).toContain("erledigt=1");
  });
});

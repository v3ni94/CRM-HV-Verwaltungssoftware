import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { NotificationBell } from "./NotificationBell";

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

/** M31 phone layout of the bell; the behaviour (unread count, mark as read) stays covered in
 *  Workspace.test.tsx. */
describe("NotificationBell (M31)", () => {
  it("is a 44 px round button with an accessible name and a label visible from lg", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(jsonResponse([{ id: "n1", kind: "custom", title: "Neu", body: null, href: null, read_at: null, created_at: "2026-09-28T08:00:00Z" }])),
    );
    renderIntl(<NotificationBell />);
    const button = screen.getByRole("button", { name: "Benachrichtigungen" });
    expect(button).toHaveClass("h-11", "w-11", "sm:w-auto", "sm:pointer-fine:h-9");
    const label = screen.getByText("Benachrichtigungen", { selector: "span" });
    // label from lg only: between sm and lg the one row header must fit a 768 px tablet
    expect(label).toHaveClass("hidden", "lg:inline");
    expect(label.className).not.toMatch(/(^|\s)(sm|md):inline/);
    expect(await screen.findByTestId("unread-count")).toHaveTextContent("1");
    await userEvent.click(button);
    const popover = document.getElementById("notifications") as HTMLElement;
    expect(popover).toHaveClass("fixed", "inset-x-4", "top-[calc(var(--mhvp-header-h)+0.5rem)]", "max-h-[70vh]", "overflow-auto", "sm:absolute", "sm:w-80");
    expect(screen.getByText("Neu").closest("button")).toHaveClass("min-h-11");
  });

  it("mutes all notifications for a period with one call", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse([])));
    renderIntl(<NotificationBell />);
    await userEvent.click(screen.getByRole("button", { name: "Benachrichtigungen" }));
    await userEvent.click(screen.getByRole("button", { name: "24 Stunden" }));
    const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/notifications/mute"))!;
    expect(call).toBeDefined();
    const body = JSON.parse(String(call[1].body));
    expect(new Date(body.muted_until).getTime()).toBeGreaterThan(Date.now() + 23 * 3_600_000);
  });
});

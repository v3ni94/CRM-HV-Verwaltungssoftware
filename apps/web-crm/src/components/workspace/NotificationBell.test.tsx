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
  it("is a 44 px round button with an accessible name and a label visible from sm", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(jsonResponse([{ id: "n1", kind: "custom", title: "Neu", body: null, href: null, read_at: null, created_at: "2026-09-28T08:00:00Z" }])),
    );
    renderIntl(<NotificationBell />);
    const button = screen.getByRole("button", { name: "Benachrichtigungen" });
    expect(button).toHaveClass("h-11", "w-11", "sm:w-auto", "sm:pointer-fine:h-9");
    const label = screen.getByText("Benachrichtigungen", { selector: "span" });
    expect(label).toHaveClass("hidden", "sm:inline");
    expect(await screen.findByTestId("unread-count")).toHaveTextContent("1");
    await userEvent.click(button);
    const popover = document.getElementById("notifications") as HTMLElement;
    expect(popover).toHaveClass("fixed", "inset-x-4", "top-[calc(var(--mhvp-header-h)+0.5rem)]", "max-h-[70vh]", "overflow-auto", "sm:absolute", "sm:w-80");
    expect(screen.getByText("Neu").closest("button")).toHaveClass("min-h-11");
  });
});

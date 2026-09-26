import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { InstallHint } from "./InstallHint";

function firePrompt() {
  const event = new Event("beforeinstallprompt") as Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: "accepted" }> };
  event.prompt = vi.fn(async () => undefined);
  event.userChoice = Promise.resolve({ outcome: "accepted" as const });
  act(() => {
    window.dispatchEvent(event);
  });
  return event;
}

describe("InstallHint", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false })));
  });

  it("stays hidden until the browser offers the installation", () => {
    renderIntl(<InstallHint />);
    expect(screen.queryByTestId("install-hint")).toBeNull();
    firePrompt();
    expect(screen.getByTestId("install-hint")).toHaveTextContent("MH Portal installieren");
  });

  it("calls the browser prompt on install and remembers a dismissal", async () => {
    const user = userEvent.setup();
    renderIntl(<InstallHint />);
    const event = firePrompt();
    await user.click(screen.getByRole("button", { name: "Installieren" }));
    expect(event.prompt).toHaveBeenCalled();
    expect(window.localStorage.getItem("mhvp-portal-install-hint-dismissed")).toBe("1");
    expect(screen.queryByTestId("install-hint")).toBeNull();
  });

  it("does not show again after a dismissal", async () => {
    const user = userEvent.setup();
    const { unmount } = renderIntl(<InstallHint />);
    firePrompt();
    await user.click(screen.getByRole("button", { name: "Später" }));
    unmount();
    renderIntl(<InstallHint />);
    firePrompt();
    expect(screen.queryByTestId("install-hint")).toBeNull();
  });
});

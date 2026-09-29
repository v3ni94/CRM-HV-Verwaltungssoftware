import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { InstallHint, isAppleTouchDevice } from "./InstallHint";

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

  it("shows the Safari hint on an iPad that reports itself as a Mac (iPadOS)", () => {
    // jsdom knows neither maxTouchPoints nor a Mac platform: define them for this case only.
    Object.defineProperty(navigator, "platform", { value: "MacIntel", configurable: true });
    Object.defineProperty(navigator, "maxTouchPoints", { value: 5, configurable: true });
    Object.defineProperty(navigator, "userAgent", {
      value: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1.15",
      configurable: true,
    });
    try {
      renderIntl(<InstallHint />);
      expect(screen.getByTestId("install-hint")).toHaveTextContent("Zum Home-Bildschirm");
    } finally {
      Object.defineProperty(navigator, "maxTouchPoints", { value: 0, configurable: true });
    }
  });
});

describe("isAppleTouchDevice", () => {
  it("tells an iPad from a Mac by the touch points", () => {
    const ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)";
    expect(isAppleTouchDevice({ userAgent: ua, platform: "MacIntel", maxTouchPoints: 5 })).toBe(true);
    expect(isAppleTouchDevice({ userAgent: ua, platform: "MacIntel", maxTouchPoints: 0 })).toBe(false);
    expect(isAppleTouchDevice({ userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)", platform: "iPhone", maxTouchPoints: 5 })).toBe(true);
    expect(isAppleTouchDevice({ userAgent: "Mozilla/5.0 (Linux; Android 14)", platform: "Linux armv8l", maxTouchPoints: 5 })).toBe(false);
  });
});

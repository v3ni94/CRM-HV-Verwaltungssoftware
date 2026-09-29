import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { InstallHint, isAppleTouchDevice } from "./InstallHint";

function firePrompt(outcome: "accepted" | "dismissed" = "accepted") {
  const event = new Event("beforeinstallprompt") as Event & {
    prompt: () => Promise<void>;
    userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
  };
  event.prompt = vi.fn(async () => undefined);
  event.userChoice = Promise.resolve({ outcome });
  act(() => {
    window.dispatchEvent(event);
  });
  return event;
}

function setNavigator(values: { platform?: string; maxTouchPoints?: number; userAgent?: string }) {
  for (const [key, value] of Object.entries(values)) {
    Object.defineProperty(navigator, key, { value, configurable: true });
  }
}

describe("InstallHint (Als App installieren, M31 WP5)", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false })));
    setNavigator({ platform: "Linux x86_64", maxTouchPoints: 0, userAgent: "Mozilla/5.0 (X11; Linux x86_64) Chrome/130" });
  });

  it("stays hidden until the browser offers the installation, then opens the browser prompt", async () => {
    renderIntl(<InstallHint />);
    expect(screen.queryByTestId("install-hint")).toBeNull();
    const event = firePrompt();
    await userEvent.click(screen.getByRole("menuitem", { name: "Als App installieren" }));
    expect(event.prompt).toHaveBeenCalled();
    expect(window.localStorage.getItem("mhvp-crm-install-hint-dismissed")).toBe("1");
    expect(screen.queryByTestId("install-hint")).toBeNull();
  });

  it("shows the Safari steps on an iPad that reports itself as a Mac (iPadOS) and remembers the dismissal", async () => {
    setNavigator({ platform: "MacIntel", maxTouchPoints: 5, userAgent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1.15" });
    const { unmount } = renderIntl(<InstallHint />);
    await userEvent.click(screen.getByRole("menuitem", { name: "Als App installieren" }));
    expect(screen.getByRole("note")).toHaveTextContent("Zum Home-Bildschirm");
    await userEvent.click(screen.getByRole("button", { name: "Nicht mehr anzeigen" }));
    expect(screen.queryByTestId("install-hint")).toBeNull();
    unmount();
    renderIntl(<InstallHint />);
    expect(screen.queryByTestId("install-hint")).toBeNull();
  });

  it("stays hidden inside the installed app", () => {
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true })));
    renderIntl(<InstallHint />);
    firePrompt();
    expect(screen.queryByTestId("install-hint")).toBeNull();
  });

  it("survives a blocked localStorage (private mode)", async () => {
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    renderIntl(<InstallHint />);
    firePrompt();
    await userEvent.click(screen.getByRole("menuitem", { name: "Als App installieren" }));
    expect(screen.queryByTestId("install-hint")).toBeNull();
    spy.mockRestore();
    vi.restoreAllMocks();
  });
});

describe("isAppleTouchDevice", () => {
  it("tells an iPad from a Mac by the touch points", () => {
    const mac = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)";
    expect(isAppleTouchDevice({ userAgent: mac, platform: "MacIntel", maxTouchPoints: 5 })).toBe(true);
    expect(isAppleTouchDevice({ userAgent: mac, platform: "MacIntel", maxTouchPoints: 0 })).toBe(false);
    expect(isAppleTouchDevice({ userAgent: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)", platform: "iPhone", maxTouchPoints: 5 })).toBe(true);
    expect(isAppleTouchDevice({ userAgent: "Mozilla/5.0 (Linux; Android 14)", platform: "Linux armv8l", maxTouchPoints: 5 })).toBe(false);
  });
});

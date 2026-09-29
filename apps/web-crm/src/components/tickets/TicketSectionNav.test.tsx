import { act, screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { TicketSectionNav } from "./TicketSectionNav";

type ObserverCallback = (entries: Partial<IntersectionObserverEntry>[]) => void;

describe("TicketSectionNav (M31)", () => {
  const original = globalThis.IntersectionObserver;
  afterEach(() => {
    globalThis.IntersectionObserver = original;
  });

  it("renders anchor links for the given sections and survives without an observer", () => {
    // @ts-expect-error jsdom has no IntersectionObserver; the component must not crash.
    delete globalThis.IntersectionObserver;
    renderIntl(<TicketSectionNav sections={["bearbeiten", "kommentare", "verlauf"]} />);
    const nav = screen.getByTestId("ticket-section-nav");
    expect(nav.className).toContain("sticky top-[var(--mhvp-header-h)]");
    expect(screen.getByRole("link", { name: "Kommentare" })).toHaveAttribute("href", "#kommentare");
    expect(screen.getByRole("link", { name: "Bearbeiten" }).className).toContain("min-h-11");
    expect(screen.queryByRole("link", { name: "Mail" })).not.toBeInTheDocument();
  });

  it("marks the section in view when an observer reports it", () => {
    let callback: ObserverCallback | null = null;
    const observe = vi.fn();
    const disconnect = vi.fn();
    class FakeObserver {
      root = null;
      rootMargin = "";
      thresholds = [];
      constructor(cb: ObserverCallback) {
        callback = cb;
      }
      observe = observe;
      disconnect = disconnect;
      unobserve = vi.fn();
      takeRecords = () => [];
    }
    globalThis.IntersectionObserver = FakeObserver as unknown as typeof IntersectionObserver;
    const comments = document.createElement("section");
    comments.id = "kommentare";
    document.body.appendChild(comments);
    const { unmount } = renderIntl(<TicketSectionNav sections={["bearbeiten", "kommentare"]} />);
    expect(observe).toHaveBeenCalledWith(comments);
    act(() => {
      callback?.([{ isIntersecting: true, target: comments, boundingClientRect: { top: 10 } as DOMRectReadOnly }]);
    });
    expect(screen.getByRole("link", { name: "Kommentare" })).toHaveAttribute("aria-current", "location");
    expect(screen.getByRole("link", { name: "Bearbeiten" })).not.toHaveAttribute("aria-current");
    unmount();
    expect(disconnect).toHaveBeenCalled();
    comments.remove();
  });
});

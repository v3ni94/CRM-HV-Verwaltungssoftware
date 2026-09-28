import { act, renderHook } from "@testing-library/react";

import { PHONE, TABLET, useMediaQuery } from "./useMediaQuery";

type Listener = (event: { matches: boolean }) => void;

function stubMatchMedia(matches: boolean) {
  const listeners = new Set<Listener>();
  const list = {
    matches,
    media: "",
    addEventListener: (_: string, fn: Listener) => listeners.add(fn),
    removeEventListener: (_: string, fn: Listener) => listeners.delete(fn),
  };
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => list),
  );
  return {
    list,
    fire(next: boolean) {
      list.matches = next;
      for (const fn of listeners) fn({ matches: next });
    },
    listeners,
  };
}

describe("useMediaQuery", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("is false without matchMedia instead of crashing", () => {
    vi.stubGlobal("matchMedia", undefined);
    const { result } = renderHook(() => useMediaQuery(PHONE));
    expect(result.current).toBe(false);
  });

  it("is false when matchMedia throws", () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => {
        throw new Error("not supported");
      }),
    );
    const { result } = renderHook(() => useMediaQuery(TABLET));
    expect(result.current).toBe(false);
  });

  it("reflects the stubbed query and follows change events", () => {
    const stub = stubMatchMedia(true);
    const { result, unmount } = renderHook(() => useMediaQuery(PHONE));
    expect(window.matchMedia).toHaveBeenCalledWith(PHONE);
    expect(result.current).toBe(true);
    act(() => stub.fire(false));
    expect(result.current).toBe(false);
    unmount();
    expect(stub.listeners.size).toBe(0);
  });

  it("exports the three device tiers as queries", () => {
    expect(PHONE).toContain("639.98px");
    expect(TABLET).toContain("640px");
    expect(TABLET).toContain("1023.98px");
  });
});

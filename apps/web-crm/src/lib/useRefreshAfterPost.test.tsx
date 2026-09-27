import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useRefreshAfterPost } from "./useRefreshAfterPost";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

afterEach(() => {
  vi.useRealTimers();
  refresh.mockReset();
});

describe("useRefreshAfterPost", () => {
  it("stays refreshing until the server delivers a new revision", () => {
    const { result, rerender } = renderHook(({ rev }) => useRefreshAfterPost(rev), { initialProps: { rev: "1" } });
    expect(result.current.refreshing).toBe(false);
    act(() => result.current.refresh());
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(result.current.refreshing).toBe(true);
    rerender({ rev: "2" });
    expect(result.current.refreshing).toBe(false);
  });

  it("repeats the refresh while the revision is unchanged and releases the guard after the fallback", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useRefreshAfterPost("1", 3000, 1000));
    act(() => result.current.refresh());
    expect(result.current.refreshing).toBe(true);
    act(() => vi.advanceTimersByTime(2500));
    expect(refresh).toHaveBeenCalledTimes(3);
    expect(result.current.refreshing).toBe(true);
    act(() => vi.advanceTimersByTime(500));
    expect(result.current.refreshing).toBe(false);
    const calls = refresh.mock.calls.length;
    act(() => vi.advanceTimersByTime(3000));
    expect(refresh).toHaveBeenCalledTimes(calls);
  });
});

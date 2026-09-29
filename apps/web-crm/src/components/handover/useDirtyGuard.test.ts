import { act, renderHook } from "@testing-library/react";

import { useDirtyGuardState } from "./useDirtyGuard";

describe("useDirtyGuardState", () => {
  it("tracks dirty ids, exposes isDirty and registers beforeunload only while dirty", () => {
    const add = vi.spyOn(window, "addEventListener");
    const remove = vi.spyOn(window, "removeEventListener");
    const { result } = renderHook(() => useDirtyGuardState());
    const first = result.current.guard;
    expect(first.isDirty()).toBe(false);
    act(() => first.setDirty("object", true));
    expect(result.current.guard.isDirty()).toBe(true);
    expect(result.current.dirty).toBe(true);
    expect(result.current.guard).toBe(first);
    expect(add).toHaveBeenCalledWith("beforeunload", expect.any(Function));
    act(() => first.setDirty("rooms", true));
    act(() => first.setDirty("object", false));
    expect(first.isDirty()).toBe(true);
    act(() => first.reset());
    expect(result.current.guard.isDirty()).toBe(false);
    expect(remove).toHaveBeenCalledWith("beforeunload", expect.any(Function));
  });
});

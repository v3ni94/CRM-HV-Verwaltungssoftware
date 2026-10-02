import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useBusy } from "./use-busy";

describe("useBusy", () => {
  it("ignores a second call while the first one runs and resets busy afterwards", async () => {
    const { result } = renderHook(() => useBusy());
    let calls = 0;
    let release: () => void = () => {};
    const handler = result.current.guard(
      () =>
        new Promise<void>((resolve) => {
          calls += 1;
          release = resolve;
        }),
    );
    let first: Promise<void> = Promise.resolve();
    await act(async () => {
      first = handler();
      await handler();
    });
    expect(calls).toBe(1);
    expect(result.current.busy).toBe(true);
    await act(async () => {
      release();
      await first;
    });
    expect(result.current.busy).toBe(false);
    await act(async () => {
      const again = result.current.guard(async () => {
        calls += 1;
      })();
      await again;
    });
    expect(calls).toBe(2);
  });

  it("prevents the default of a submit event even when ignored", async () => {
    const { result } = renderHook(() => useBusy());
    let release: () => void = () => {};
    const handler = result.current.guard((e: { type: string; preventDefault: () => void }) => {
      void e;
      return new Promise<void>((resolve) => {
        release = resolve;
      });
    });
    let prevented = 0;
    const ev = { type: "submit", preventDefault: () => (prevented += 1) };
    let first: Promise<void> = Promise.resolve();
    await act(async () => {
      first = handler(ev);
      await handler(ev);
    });
    expect(prevented).toBe(2);
    await act(async () => {
      release();
      await first;
    });
  });
});

"use client";

import { useCallback, useRef, useState } from "react";

/** Double submit protection for write actions (GAI-422): `guard(fn)` returns an event handler that
 *  ignores further calls while the previous one is still running and exposes `busy` for `disabled`.
 *  A submit event is always prevented, also when the call is ignored. */
export function useBusy() {
  const [busy, setBusy] = useState(false);
  const running = useRef(false);
  const guard = useCallback(
    <A extends unknown[]>(fn: (...args: A) => unknown) =>
      async (...args: A): Promise<void> => {
        const first = args[0] as { preventDefault?: () => void } | undefined;
        if (first && typeof first.preventDefault === "function" && (first as { type?: string }).type === "submit") first.preventDefault();
        if (running.current) return;
        running.current = true;
        setBusy(true);
        try {
          await fn(...args);
        } finally {
          running.current = false;
          setBusy(false);
        }
      },
    [],
  );
  return { busy, guard };
}

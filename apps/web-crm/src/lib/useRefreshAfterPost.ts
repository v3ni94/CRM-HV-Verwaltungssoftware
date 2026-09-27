"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

/** Refresh the server component after a successful post and report `refreshing` until the
 *  server has re-rendered with a new `revision` (a string the page derives from the data the
 *  post changes). Buttons stay disabled meanwhile, so a second post cannot start while a
 *  refresh is in flight (Next.js coalesces overlapping router.refresh calls). A plain state
 *  flag is used instead of wrapping router.refresh in useTransition: that pending flag could
 *  stay true indefinitely in Next.js 15 and blocked the page (e2e money and workflow paths).
 *  Next.js may also drop a refresh whose payload arrives while another router update is being
 *  committed (observed in the e2e runs: the server rendered the new data, the page kept the old
 *  one), so the refresh is repeated every `retryMs` while the revision is unchanged. If a post
 *  does not change the revision, the guard is released after `fallbackMs`. */
export function useRefreshAfterPost(revision: string, fallbackMs = 8000, retryMs = 1000) {
  const router = useRouter();
  const [waitingOn, setWaitingOn] = useState<string | null>(null);
  const refreshing = waitingOn !== null && waitingOn === revision;
  useEffect(() => {
    if (!refreshing) return;
    const timer = setTimeout(() => setWaitingOn(null), fallbackMs);
    const retry = setInterval(() => router.refresh(), retryMs);
    return () => {
      clearTimeout(timer);
      clearInterval(retry);
    };
  }, [refreshing, fallbackMs, retryMs, router]);
  const refresh = useCallback(() => {
    setWaitingOn(revision);
    router.refresh();
  }, [revision, router]);
  return { refreshing, refresh };
}

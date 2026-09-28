"use client";

import { useEffect, useState } from "react";

/** Whether the browser reports a network connection (`navigator.onLine` plus the `online`
 *  and `offline` events). `true` on the server and before the first effect, so a page never
 *  starts with an offline notice it then has to retract. The value is a hint only: `true`
 *  does not prove the API is reachable, a failed request still needs its own handling. */
export function useOnline(): boolean {
  const [online, setOnline] = useState(true);
  useEffect(() => {
    const update = () => setOnline(typeof navigator === "undefined" ? true : navigator.onLine !== false);
    update();
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);
  return online;
}

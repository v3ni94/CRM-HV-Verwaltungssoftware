"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";

/** Statuses of a bank connection that count as separated (OP-02): hidden by default. */
export const DISCONNECTED_STATUSES: ReadonlySet<string> = new Set(["disabled", "disconnected", "revoked"]);

export function isDisconnected(status: string): boolean {
  return DISCONNECTED_STATUSES.has(status);
}

export const SHOW_DISCONNECTED_KEY = "mhvp.bank.showDisconnected";

function readStored(): boolean {
  try {
    return window.localStorage.getItem(SHOW_DISCONNECTED_KEY) === "1";
  } catch {
    return false;
  }
}

/** Per viewer (browser) switch "Getrennte anzeigen"; view only, no data change. */
export function useShowDisconnected(): [boolean, (value: boolean) => void] {
  const [show, setShow] = useState(false);
  useEffect(() => {
    setShow(readStored());
  }, []);
  function update(value: boolean) {
    setShow(value);
    try {
      window.localStorage.setItem(SHOW_DISCONNECTED_KEY, value ? "1" : "0");
    } catch {
      // storage blocked (private mode): the switch still works for this page view
    }
  }
  return [show, update];
}

export function DisconnectedToggle({ count, show, onChange }: { count: number; show: boolean; onChange: (value: boolean) => void }) {
  const t = useTranslations("BankConnections");
  if (count === 0) return null;
  return (
    <label className="mt-2 flex items-center gap-2 text-sm">
      <input type="checkbox" checked={show} onChange={(e) => onChange(e.target.checked)} data-testid="show-disconnected" />
      {t("showDisconnected", { count })}
    </label>
  );
}

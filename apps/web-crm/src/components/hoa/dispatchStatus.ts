const KNOWN = ["prepared", "sent", "delivered", "failed"] as const;

type Translate = (key: string) => string;

/** Translated dispatch status for the provision log; an unknown status is shown unchanged. */
export function dispatchStatusLabel(t: Translate, status: string): string {
  return (KNOWN as readonly string[]).includes(status) ? t(`status.${status}`) : status;
}

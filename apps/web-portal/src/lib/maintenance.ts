import { apiBaseUrl } from "@/lib/session";

/** GB16-01: announced maintenance window as served by the public feed GET /platform/maintenance/current. */
export type MaintenanceItem = {
  id: string;
  starts_at: string;
  ends_at: string;
  text_de: string;
  text_en: string;
  phase: "announced" | "active";
};

/** Reads the public feed; any failure yields no banner (the banner is a courtesy, never a blocker). */
export async function fetchMaintenance(): Promise<MaintenanceItem[]> {
  try {
    const response = await fetch(`${apiBaseUrl()}/api/v1/platform/maintenance/current`, {
      next: { revalidate: 30 },
      signal: AbortSignal.timeout(2000),
    });
    if (!response.ok) return [];
    const body = (await response.json()) as { items?: MaintenanceItem[] };
    return Array.isArray(body.items) ? body.items : [];
  } catch {
    return [];
  }
}

/** Date and time in German business time (timestamps are stored in UTC). */
export function formatWindow(iso: string, locale: string): string {
  return new Date(iso).toLocaleString(locale === "de" ? "de-DE" : "en-GB", {
    timeZone: "Europe/Berlin",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

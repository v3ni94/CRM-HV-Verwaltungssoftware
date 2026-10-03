import { formatDateTime } from "@/lib/format-date";
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
  void locale; // kept for the call sites, one format for every language
  // One UI format (TT.MM.JJJJ, HH:MM) for every language; the locale stays for the call sites.
  return formatDateTime(iso);
}

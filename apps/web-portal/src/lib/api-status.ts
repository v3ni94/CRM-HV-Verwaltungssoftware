import { createApiClient } from "@mhvp/api-client";

export type ApiStatus = "ready" | "unavailable";

const TIMEOUT_MS = 2000;

/** Server-side readiness probe; never throws, any failure counts as unavailable. */
export async function getApiStatus(): Promise<ApiStatus> {
  const baseUrl = process.env.MHVP_API_INTERNAL_URL;
  if (!baseUrl) return "unavailable";
  try {
    const client = createApiClient(baseUrl);
    const { data, response } = await client.GET("/api/v1/health/ready", {
      signal: AbortSignal.timeout(TIMEOUT_MS),
      cache: "no-store",
    });
    return response.ok && data?.status === "ok" ? "ready" : "unavailable";
  } catch {
    return "unavailable";
  }
}

import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type { components, paths } from "./schema";
export type HealthReport = components["schemas"]["HealthReport"];
export type LiveReport = components["schemas"]["LiveReport"];

export type ApiClient = ReturnType<typeof createClient<paths>>;

/** Thin typed client for the MHVP API. `baseUrl` is the origin, e.g. http://api:8000. */
export function createApiClient(baseUrl: string, fetchImpl?: typeof fetch): ApiClient {
  return createClient<paths>({
    baseUrl: baseUrl.replace(/\/+$/, ""),
    ...(fetchImpl ? { fetch: fetchImpl } : {}),
  });
}

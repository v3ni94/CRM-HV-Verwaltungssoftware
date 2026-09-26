/**
 * Signed-in user for server components, deduplicated per request.
 *
 * The app layout and most pages need `GET /api/v1/auth/me` for the permission checks. Wrapped
 * in React `cache()` the first call in a request performs the HTTP round trip, every further
 * call during the same server render (layout and page) receives the identical result object
 * (review 26.09.2026, M5). The result shape is the same as `serverApi().GET("/api/v1/auth/me")`,
 * so callers keep their `data`, `error` and `response` handling unchanged.
 */
import { cache } from "react";

import { serverApi } from "./api-server";

export const getMe = cache(() => serverApi().GET("/api/v1/auth/me"));

export type MeResult = Awaited<ReturnType<typeof getMe>>;

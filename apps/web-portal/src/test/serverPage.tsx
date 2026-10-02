/**
 * Harness for the server component pages under app/(portal) (GAG-17, GAF-31). The pages are
 * async functions: they are awaited and the returned element is rendered with the strict
 * German provider. The API layer is replaced by a route table, child components by stubs that
 * expose their props as JSON, so a test checks what the page fetches, decides and passes on.
 * No network, no real session.
 */
import { createFormatter, createTranslator } from "next-intl";

import messages from "../../messages/de.json";

import { onIntlError } from "./intlErrors";

export type FakeRoute = { status: number; body?: unknown };

/** Route table of the fake API, keyed by path including the query string; a path without a
 *  match falls back to the same path without query. An unknown path fails the test. */
export const fakeRoutes = new Map<string, FakeRoute>();
export const requestedPaths: string[] = [];

/** Optional answer for every path without a route (GAH-304 axe sweep over all pages). */
export let fallbackRoute: FakeRoute | null = null;
export function setFallbackRoute(hit: FakeRoute | null): void {
  fallbackRoute = hit;
}

export function resetRoutes(): void {
  fallbackRoute = null;
  fakeRoutes.clear();
  requestedPaths.length = 0;
}

export function route(path: string, status: number, body?: unknown): void {
  fakeRoutes.set(path, { status, body });
}

function lookup(path: string): FakeRoute {
  requestedPaths.push(path);
  const hit = fakeRoutes.get(path) ?? fakeRoutes.get(path.split("?")[0] ?? path);
  if (!hit && fallbackRoute) return fallbackRoute;
  if (!hit) throw new Error(`unmocked API path: ${path}`);
  return hit;
}

function respond(hit: FakeRoute): Response {
  const json = hit.body !== undefined;
  return new Response(json ? JSON.stringify(hit.body) : null, {
    status: hit.status,
    headers: json ? { "content-type": "application/json" } : {},
  });
}

/** Factory for vi.mock("@/lib/api-server"). */
export function apiServerMock() {
  return {
    serverFetch: async (path: string) => respond(lookup(path)),
    serverApi: () => ({
      GET: async (path: string, init?: { params?: { path?: Record<string, string> } }) => {
        let resolved = path;
        for (const [key, value] of Object.entries(init?.params?.path ?? {})) {
          resolved = resolved.replace(`{${key}}`, value);
        }
        const hit = lookup(resolved);
        const ok = hit.status >= 200 && hit.status < 300;
        return {
          data: ok ? hit.body : undefined,
          error: ok ? undefined : (hit.body ?? `HTTP ${hit.status}`),
          response: respond(hit),
        };
      },
    }),
    redirectIfUnauthenticated: (response: Response) => {
      if (response.status === 401) throw new Error("NEXT_REDIRECT:/anmelden");
    },
    sessionContext: async () => ({}),
  };
}

/** Factory for vi.mock("next/navigation"). */
export function navigationMock() {
  return {
    redirect: (url: string) => {
      throw new Error(`NEXT_REDIRECT:${url}`);
    },
    notFound: () => {
      throw new Error("NEXT_NOT_FOUND");
    },
    useRouter: () => ({ push: () => undefined, replace: () => undefined, refresh: () => undefined }),
    usePathname: () => "/",
    useSearchParams: () => new URLSearchParams(),
  };
}

/** Factory for vi.mock("next-intl/server"): the real translator on the German messages. */
export function intlServerMock() {
  return {
    getTranslations: async (namespace?: string) =>
      createTranslator({ locale: "de", messages, namespace: namespace as never, onError: onIntlError }),
    getFormatter: async () => createFormatter({ locale: "de", timeZone: "Europe/Berlin" }),
  };
}

/** Stub components: render their props as JSON (functions are dropped). */
export function stubModule(names: string[]): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const name of names) {
    out[name] = (props: Record<string, unknown>) => (
      <div data-testid={name} data-props={JSON.stringify(props) ?? "{}"} />
    );
  }
  return out;
}

export function stubProps<T = Record<string, unknown>>(el: HTMLElement): T {
  return JSON.parse(el.dataset.props ?? "{}") as T;
}

/** German text of a message key, read from the same file the UI uses. */
export function de(namespace: string, key: string): string {
  const value = (messages as unknown as Record<string, Record<string, unknown>>)[namespace]?.[key];
  if (typeof value !== "string") throw new Error(`message ${namespace}.${key} missing`);
  return value;
}

import { createApiClient } from "@mhvp/api-client";
import { NextResponse } from "next/server";

import { rejectForeignOrigin } from "@/lib/csrf";
import { problemJson } from "@/lib/problem";
import { apiBaseUrl, isSecureHost } from "@/lib/session";

export function publicApi() {
  return createApiClient(apiBaseUrl());
}

export function secureOf(request: Request): boolean {
  return isSecureHost(request.headers.get("x-forwarded-host") ?? request.headers.get("host"));
}

/** Origin check plus JSON body parsing for mutating session handlers. */
export async function guardedJson(
  request: Request,
): Promise<{ body: Record<string, unknown> } | { error: Response }> {
  const rejected = rejectForeignOrigin(request);
  if (rejected) return { error: rejected };
  try {
    const body: unknown = await request.json();
    if (typeof body !== "object" || body === null) throw new Error("not an object");
    return { body: body as Record<string, unknown> };
  } catch {
    return { error: problemJson(400, "Anfrage ungültig", "Der Inhalt der Anfrage ist ungültig.") };
  }
}

/** Relays an API problem to the browser without tokens or internals. */
export function relayProblem(status: number, problem: unknown): Response {
  if (problem && typeof problem === "object") {
    const { title, detail, errors, code } = problem as Record<string, unknown>;
    return NextResponse.json(
      { title, detail, errors, code, status },
      { status, headers: { "content-type": "application/problem+json" } },
    );
  }
  return problemJson(status >= 400 ? status : 502, "Schnittstelle nicht erreichbar");
}

export function unreachable(): Response {
  return problemJson(
    502,
    "Schnittstelle nicht erreichbar",
    "Die Schnittstelle ist derzeit nicht erreichbar. Bitte später erneut versuchen.",
  );
}

export function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/** Public origin of the request (honours the reverse proxy headers). */
export function publicOrigin(request: Request): string {
  const url = new URL(request.url);
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host") ?? url.host;
  const proto = request.headers.get("x-forwarded-proto") ?? url.protocol.replace(":", "");
  return `${proto}://${host}`;
}

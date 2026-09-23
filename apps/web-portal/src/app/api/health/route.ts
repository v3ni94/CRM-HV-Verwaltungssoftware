import { SERVICE_NAME, appVersion } from "@/lib/version";

export const dynamic = "force-dynamic";

export function GET(): Response {
  return Response.json(
    { status: "ok", service: SERVICE_NAME, version: appVersion() },
    { headers: { "Cache-Control": "no-store" } },
  );
}

import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import QRCode from "qrcode";

import { rejectForeignOrigin } from "@/lib/csrf";
import { problemJson } from "@/lib/problem";
import { COOKIE } from "@/lib/session";

import { postJson, relayProblem, unreachable } from "../../_shared";

/**
 * M2-04: login step "Zweiten Faktor einrichten". The tenant policy demands a second factor the
 * user has not set up yet; with the setup token from step 1 (httpOnly cookie) the API creates a
 * pending TOTP secret. Returns the secret and the otpauth URI as QR code (data URL, generated
 * here with the existing "qrcode" library, same as under Einstellungen, Meine Daten).
 */
export async function POST(request: Request): Promise<Response> {
  const rejected = rejectForeignOrigin(request);
  if (rejected) return rejected;
  const setupToken = (await cookies()).get(COOKIE.mfaSetup)?.value;
  if (!setupToken) {
    return problemJson(401, "Anmeldung erforderlich", "Bitte zuerst E-Mail und Passwort eingeben.");
  }
  try {
    const { status, data } = await postJson(
      "/api/v1/auth/mfa/setup/start",
      { mfa_setup_token: setupToken },
      request.headers.get("user-agent") ?? "",
      request.headers,
    );
    if (status >= 400 || !data) return relayProblem(status, data);
    const uri = String(data.otpauth_uri ?? "");
    const qr = await QRCode.toDataURL(uri, { margin: 1, width: 220 });
    return NextResponse.json(
      { secret: data.secret, otpauth_uri: uri, qr },
      { headers: { "cache-control": "no-store" } },
    );
  } catch {
    return unreachable();
  }
}

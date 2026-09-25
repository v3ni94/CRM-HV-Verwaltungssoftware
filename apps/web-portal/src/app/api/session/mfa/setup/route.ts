import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import QRCode from "qrcode";

import { problemJson } from "@/lib/problem";
import { COOKIE } from "@/lib/session";

import { guardedJson, publicApi, relayProblem, unreachable } from "../../_shared";

/** Starts the TOTP setup; returns the secret and the otpauth URI as QR code (data URL). */
export async function POST(request: Request): Promise<Response> {
  const parsed = await guardedJson(request);
  if ("error" in parsed) return parsed.error;
  const mfaToken = (await cookies()).get(COOKIE.mfa)?.value;
  if (!mfaToken) {
    return problemJson(401, "Anmeldung erforderlich", "Bitte zuerst E-Mail und Passwort eingeben.");
  }
  try {
    const { data, error, response } = await publicApi().POST("/api/v1/auth/mfa/setup", {
      body: { mfa_token: mfaToken },
    });
    if (!data) return relayProblem(response.status, error);
    const qr = await QRCode.toDataURL(data.otpauth_uri, { margin: 1, width: 220 });
    return NextResponse.json(
      { secret: data.secret, otpauth_uri: data.otpauth_uri, qr },
      { headers: { "cache-control": "no-store" } },
    );
  } catch {
    return unreachable();
  }
}

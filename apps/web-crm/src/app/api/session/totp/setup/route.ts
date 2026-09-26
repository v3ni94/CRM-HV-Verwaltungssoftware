import { NextResponse } from "next/server";
import QRCode from "qrcode";

import { serverApi } from "@/lib/api-server";
import { rejectForeignOrigin } from "@/lib/csrf";

import { relayProblem, unreachable } from "../../_shared";

/**
 * Einstellungen, Sicherheit: starts the optional TOTP setup for the signed in user (operator
 * 26.09.2026, M2-01) and returns the secret with the otpauth URI as QR code (data URL). The
 * second factor becomes effective only after POST /api/bff/auth/totp/confirm.
 */
export async function POST(request: Request): Promise<Response> {
  const rejected = rejectForeignOrigin(request);
  if (rejected) return rejected;
  try {
    const { data, error, response } = await serverApi().POST("/api/v1/auth/totp/setup");
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

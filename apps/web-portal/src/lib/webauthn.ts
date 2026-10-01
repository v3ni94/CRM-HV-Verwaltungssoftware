/** Browser helpers for passkeys (S16-01): converts the API options (base64url) into the
 *  ArrayBuffers of navigator.credentials and the answers back into base64url JSON. */

export type PublicKeyOptions = Record<string, unknown>;
export type WebAuthnOptions = { challenge_id: string; public_key: PublicKeyOptions };

export function b64urlToBuffer(value: string): ArrayBuffer {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

export function bufferToB64url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function passkeysSupported(): boolean {
  return typeof window !== "undefined" && typeof window.PublicKeyCredential === "function" && !!navigator.credentials;
}

type Descriptor = { type: "public-key"; id: string; transports?: string[] };

function descriptors(list: unknown): PublicKeyCredentialDescriptor[] {
  return ((list as Descriptor[] | undefined) ?? []).map((d) => ({
    type: "public-key",
    id: b64urlToBuffer(d.id),
    transports: d.transports as AuthenticatorTransport[] | undefined,
  }));
}

export async function createPasskey(options: PublicKeyOptions) {
  const user = options.user as { id: string; name: string; displayName: string };
  const credential = (await navigator.credentials.create({
    publicKey: {
      ...(options as unknown as PublicKeyCredentialCreationOptions),
      challenge: b64urlToBuffer(String(options.challenge)),
      user: { ...user, id: b64urlToBuffer(user.id) },
      excludeCredentials: descriptors(options.excludeCredentials),
    },
  })) as PublicKeyCredential | null;
  if (!credential) throw new Error("aborted");
  const response = credential.response as AuthenticatorAttestationResponse;
  return {
    credential_id: bufferToB64url(credential.rawId),
    response: {
      client_data_json: bufferToB64url(response.clientDataJSON),
      attestation_object: bufferToB64url(response.attestationObject),
      transports: typeof response.getTransports === "function" ? response.getTransports() : [],
    },
  };
}

export async function getPasskeyAssertion(options: PublicKeyOptions) {
  const credential = (await navigator.credentials.get({
    publicKey: {
      ...(options as unknown as PublicKeyCredentialRequestOptions),
      challenge: b64urlToBuffer(String(options.challenge)),
      allowCredentials: descriptors(options.allowCredentials),
    },
  })) as PublicKeyCredential | null;
  if (!credential) throw new Error("aborted");
  const response = credential.response as AuthenticatorAssertionResponse;
  return {
    credential_id: bufferToB64url(credential.rawId),
    response: {
      client_data_json: bufferToB64url(response.clientDataJSON),
      authenticator_data: bufferToB64url(response.authenticatorData),
      signature: bufferToB64url(response.signature),
      user_handle: response.userHandle ? bufferToB64url(response.userHandle) : null,
    },
  };
}

export type PasskeySignIn =
  | { ok: true; tenant_id: string | null }
  | { ok: false; reason: "unsupported" | "aborted" | "failed"; message?: string };

/** Full passkey sign in through the session BFF: options, browser ceremony, verify. */
export async function signInWithPasskey(
  mode: "mfa" | "passwordless",
  extra: { remember_device?: boolean } = {},
): Promise<PasskeySignIn> {
  if (!passkeysSupported()) return { ok: false, reason: "unsupported" };
  const { bff } = await import("./bff");
  const options = await bff<WebAuthnOptions>("/api/session/webauthn/options", {
    method: "POST",
    body: JSON.stringify({ mode }),
  });
  if (!options.ok) return { ok: false, reason: "failed", message: options.message };
  let assertion: Awaited<ReturnType<typeof getPasskeyAssertion>>;
  try {
    assertion = await getPasskeyAssertion(options.data.public_key);
  } catch {
    return { ok: false, reason: "aborted" };
  }
  const verified = await bff<{ tenant_id: string | null }>("/api/session/webauthn/verify", {
    method: "POST",
    body: JSON.stringify({ mode, challenge_id: options.data.challenge_id, ...assertion, ...extra }),
  });
  if (!verified.ok) return { ok: false, reason: "failed", message: verified.message };
  return { ok: true, tenant_id: verified.data.tenant_id };
}

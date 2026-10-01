import { b64urlToBuffer, bufferToB64url, signInWithPasskey } from "./webauthn";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

describe("webauthn helpers (S16-01)", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("round-trips base64url without padding", () => {
    const bytes = new Uint8Array([0, 251, 255, 1, 2]);
    const encoded = bufferToB64url(bytes.buffer);
    expect(encoded).toBe("APv_AQI");
    expect(Array.from(new Uint8Array(b64urlToBuffer(encoded)))).toEqual(Array.from(bytes));
  });

  it("reports unsupported browsers without calling the BFF", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("PublicKeyCredential", undefined);
    expect(await signInWithPasskey("passwordless")).toEqual({ ok: false, reason: "unsupported" });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("runs options, ceremony and verify for the second factor", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    fetchMock
      .mockResolvedValueOnce(json({ challenge_id: "cid-1234567890", public_key: { challenge: "AAEC", allowCredentials: [{ type: "public-key", id: "AQI" }] } }))
      .mockResolvedValueOnce(json({ tenant_id: "t1", tenants: [] }));
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("PublicKeyCredential", function PublicKeyCredential() {});
    const buf = (n: number) => new Uint8Array([n]).buffer;
    const get = vi.fn().mockResolvedValue({
      rawId: buf(1),
      response: { clientDataJSON: buf(2), authenticatorData: buf(3), signature: buf(4), userHandle: null },
    });
    vi.stubGlobal("navigator", { credentials: { get } });
    const result = await signInWithPasskey("mfa", { remember_device: true });
    expect(result).toEqual({ ok: true, tenant_id: "t1" });
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/session/webauthn/options");
    const sent = JSON.parse(String(fetchMock.mock.calls[1]![1]?.body));
    expect(sent).toMatchObject({ mode: "mfa", challenge_id: "cid-1234567890", credential_id: "AQ", remember_device: true });
    expect(sent.response).toEqual({ client_data_json: "Ag", authenticator_data: "Aw", signature: "BA", user_handle: null });
  });
});

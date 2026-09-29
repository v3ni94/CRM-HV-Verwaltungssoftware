/** Encryption at rest of the offline queue (rule M30-10, ADR 0016, operator decision
 *  28.09.2026): AES-GCM 256 with a key that exists only in the memory of this page session.
 *  The key is generated on first use after the login (non extractable, never written to
 *  storage, never sent anywhere) and forgotten by `forgetSessionKey()` (logout, session end,
 *  page unload). Records left in IndexedDB without the key are unreadable and are discarded
 *  by the queue on the next read; that is the documented limitation: a page reload while
 *  offline loses the key and therefore the queued changes. A passphrase prompt was rejected
 *  because a passphrase typed on a shared tablet is weaker than an in memory key and would
 *  have to be persisted in some form to survive the reload. */

const subtle = () => {
  const c = globalThis.crypto;
  if (!c?.subtle) throw new Error("WebCrypto unavailable");
  return c.subtle;
};

let sessionKey: Promise<CryptoKey> | null = null;

/** Lazily generated AES-GCM key of this page session. */
export function getSessionKey(): Promise<CryptoKey> {
  if (!sessionKey) {
    sessionKey = subtle().generateKey({ name: "AES-GCM", length: 256 }, false, ["encrypt", "decrypt"]);
  }
  return sessionKey;
}

/** Drops the key: every record encrypted with it is unreadable from now on. */
export function forgetSessionKey(): void {
  sessionKey = null;
}

export type Sealed = { iv: Uint8Array; data: ArrayBuffer };

export async function seal(plain: Uint8Array, key?: CryptoKey): Promise<Sealed> {
  const k = key ?? (await getSessionKey());
  const iv = globalThis.crypto.getRandomValues(new Uint8Array(12));
  const data = await subtle().encrypt({ name: "AES-GCM", iv }, k, plain as BufferSource);
  return { iv, data };
}

/** Throws when the record was sealed with another key (for example before a reload). */
export async function open(sealed: Sealed, key?: CryptoKey): Promise<Uint8Array> {
  const k = key ?? (await getSessionKey());
  const plain = await subtle().decrypt({ name: "AES-GCM", iv: sealed.iv as BufferSource }, k, sealed.data);
  return new Uint8Array(plain);
}

const encoder = new TextEncoder();
const decoder = new TextDecoder();

export async function sealJson(value: unknown, key?: CryptoKey): Promise<Sealed> {
  return seal(encoder.encode(JSON.stringify(value)), key);
}

export async function openJson<T>(sealed: Sealed, key?: CryptoKey): Promise<T> {
  return JSON.parse(decoder.decode(await open(sealed, key))) as T;
}

export function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

export function base64ToBytes(text: string): Uint8Array {
  const binary = atob(text);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

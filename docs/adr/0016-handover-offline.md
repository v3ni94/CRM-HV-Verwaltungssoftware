# ADR 0016: Offline capture of handover protocols on phone and tablet

- Status: Accepted (operator decision 28.09.2026: "vollständig offline" with the data
  protection conditions below; implemented 29.09.2026 as rule M30-10 behind the tenant switch
  `handover_offline_enabled`, default off)
- Date: 2026-09-29

## Context

The operator asked on 28.09.2026 for a full offline capture of handover protocols: a
property manager should be able to record rooms, defects, meters, keys, photos and
signatures in a basement or a building without reception and transfer everything once the
connection is back. M31 WP2 delivers the online editor only: every save goes to the API, a
lost connection shows the notice "Keine Verbindung" and the input stays on the open page
until "Erneut senden" succeeds (docs/plans/M31-handy-tablet.md, open decision 1, M30-07).
Nothing is written to `localStorage`, IndexedDB or a service worker cache, because the
protocol holds personal data of tenants (names, addresses, phone numbers, IBAN of the deposit
account), photos of the flat and signature images, often on a shared tablet.

Product protection per CLAUDE.md section 5 and rule 0.1.3: a risk to data protection or to
evidence locks the productive action until a released rule exists. This ADR describes the
requested mode so it can be built as its own work package once the operator, together with
data protection advice, has decided the open points.

## Decision

The operator chose the full offline mode on 28.09.2026 under these conditions, which are
binding for the implementation (rule M30-10): queue of pending changes and photos in
IndexedDB encrypted at rest with a key held only in memory for the session (derived per
login, never persisted); deletion of the queue on logout and after a successful sync; device
timestamps recorded as "vom Gerät gemeldet" on every queued item; conflict handling on sync
(server state newer: show both and ask); a visible offline banner with the count of pending
items; a sync log per protocol; no photos or protocol data in the service worker cache; a
tenant switch `handover_offline_enabled` (default off).

Offline capture is built as a separate package with these elements, all behind a per tenant
feature flag (default off, ADR 0003 style):

1. Queue: the editor keeps a local write queue of API calls (PATCH protocol, POST and PATCH
   sub records, POST documents with the downscaled file, POST signatures) in IndexedDB, in
   the order they were made, keyed by protocol. While offline the screen renders the
   protocol from the last server copy plus the queued changes. Photos are stored as the
   downscaled JPEG blob (M30-04 pipeline still runs on the server on replay).
2. Replay: on reconnection the queue is replayed in order; a 409 (content lock M30-09,
   duplicate signature) or a 422 stops the queue at that entry and shows the conflict, the
   rest stays queued until the user resolves it. Replay never bypasses the server rules; the
   server remains the only place that decides what is stored.
3. Encryption at rest: the queue is encrypted with a key derived from the user session (for
   example a key wrapped by the session token and held only in memory), so the IndexedDB
   content is unreadable without an active session on that device.
4. Deletion: the queue is deleted on logout, on session expiry, after a successful replay,
   and by an explicit "Lokale Entwürfe löschen" action. A shared device that is handed to a
   participant for the signature must not expose another protocol's queue (open decision
   11, restricted signing mode).
5. Evidence timestamps: every queued entry carries the device time of capture
   (`captured_at`) which the server stores alongside `created_at` (the replay time) as a
   claimed value, never as proof. Signatures capture `signed_at_device`; the server keeps
   its own `signed_at` from the replay and prints both in the PDF with the note that the
   device time is reported by the device. Order of entries in the queue is preserved and
   reported so the server can detect edits after a signature (M30-09 applies on replay).
6. Scope: CRM only (staff users); the portal keeps online only. No money paths are touched.

## Implementation (29.09.2026)

- Client (`apps/web-crm/src/components/handover/offline/`): AES-GCM 256 key generated in
  memory on first use after the login, non extractable, never stored; IndexedDB holds only
  the random record id and the sequence number in plain text, everything else is sealed;
  the queue is wiped on logout and session end (401, `pagehide`), after a successful replay
  per protocol and by "Lokale Entwürfe löschen"; the banner shows the connection state and
  the count of pending items; the replay maps temporary ids to server ids; a conflict opens
  a sheet with both states; a sync log per protocol lives in the session memory.
- Server: `handover_client_write` ledger (RLS, unique per tenant and key, no TTL) with the
  headers `X-Handover-Client-Key`, `X-Captured-At`, `X-Base-Updated-At`; `captured_at` on
  the section rows, `signed_at_device` on signatures, both printed or shown as reported by
  the device; 403 MHVP-HDOV-0003 without the tenant switch, 409 MHVP-HDOV-0004 with the
  server state on a conflict; lock rules M30-01 and M30-09 unchanged on replay.
- The header is deliberately not the generic `Idempotency-Key`: that middleware replays 4xx
  answers for 24 hours, which would freeze a refusal although the switch or the version has
  changed since.

## Consequences and residual risks

- Key only in memory: a page reload or a closed tab while offline loses the key and with it
  the queued changes (they are discarded on the next read and reported as "verworfen").
  The banner tells the person not to reload and not to log out while changes wait. A
  passphrase prompt was considered and rejected: typed on a shared tablet it is weaker than
  the in memory key, and without persisting it in some form it would not survive the
  reload either.
- Device time is a claimed value: `captured_at` and `signed_at_device` can be wrong or
  manipulated on the device; the server time of the replay stays the reference and the PDF
  prints both. The operator's legal advice on M30-02 (evidential value of the signature
  image) has to cover device timestamps and delayed uploads; open in OPEN_QUESTIONS M30-02.
- Sealed records stay in IndexedDB between the capture and the wipe; on a lost or stolen
  device they are unreadable without the key, but the storage itself is not wiped by the
  platform. The retention on lost devices and a maximum age of queued drafts remain
  operator decisions (documented as conditions in M30-07, no gate).
- Deleting photos or signatures, completion, cancellation, new versions and dispatch stay
  online only; the portal stays online only.
- Tests delivered: queue order, dedupe, sealed storage, wipe and lost key (vitest), replay
  with conflict and id mapping (vitest), editor flow offline to online (vitest), server
  switch, ledger, lock, conflict, 403 and tenant separation (pytest). Not delivered: a
  Playwright flow with the network switched off and on (open point).

## Alternatives considered

- Local draft in `localStorage` without encryption: rejected, personal data in plain text
  on a shared device.
- Service worker request queue (Background Sync): rejected for now, iOS Safari support is
  incomplete and the queue would live outside the app's session control.
- Server side "parking" of drafts under a device token: possible later, does not help
  without any connection.

## References

- `docs/plans/M31-handy-tablet.md` (open decisions 1, 11, 13, 14)
- `docs/rules/M30-01.md`, `docs/rules/M30-04` (via OPEN_QUESTIONS M30-04), `docs/rules/M30-09-aenderung-nach-unterschrift.md`
- `docs/OPEN_QUESTIONS.md` M30-02, M30-07
- ADR 0003 (feature flags per tenant), ADR 0013 (responsive primitives)

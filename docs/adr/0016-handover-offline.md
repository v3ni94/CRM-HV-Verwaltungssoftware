# ADR 0016: Offline capture of handover protocols on phone and tablet

- Status: Proposed (operator request 28.09.2026; not part of M31 WP2, own package pending the
  data protection decisions below)
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

## Decision (proposed)

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

## Consequences

- Open data protection points to decide before implementation (owner operator with data
  protection advice; no gate, but the feature stays off until decided): retention of the
  encrypted queue on lost devices; whether photos may be held locally at all or only their
  references; the maximum age of a queued draft; whether replay needs a second confirmation
  by the user; logging of replays as events (6.9.6).
- Evidence: the operator's legal advice on M30-02 (evidential value of the signature image)
  has to cover device timestamps and delayed uploads.
- Tests required: queue order, replay stop on 409 and 422, encryption key gone after logout
  (queue unreadable), deletion on logout and after replay, no plain text in IndexedDB,
  Playwright flow with network off and on.
- Until then: online only with the offline notice and retry (M31 WP2), which is the state
  delivered on 29.09.2026.

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

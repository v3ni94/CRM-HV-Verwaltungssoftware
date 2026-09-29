/** Optimistic view of a protocol while changes wait in the queue (rule M30-10): the last
 *  server copy plus the queued changes in capture order. Items created offline carry their
 *  temporary id and `_pending: true`; the server never sees these fields, the replay maps
 *  the temporary id to the id the server assigns. */

import type { Full, Item } from "../types";
import type { QueuedItem } from "./queue";

export function applyQueued(server: Full, items: QueuedItem[]): Full {
  let p: Full = { ...server };
  for (const { op, capturedAt } of items) {
    switch (op.kind) {
      case "patch_protocol":
        p = { ...p, ...(op.body as Partial<Full>), status: p.status === "draft" ? "in_progress" : p.status };
        break;
      case "create_item": {
        const item: Item = { id: op.tempId, ...(op.body as Record<string, Item[string]>), _pending: true, captured_at: capturedAt };
        p = { ...p, [op.section]: [...p[op.section], item] };
        break;
      }
      case "patch_item":
        p = { ...p, [op.section]: p[op.section].map((x) => (x.id === op.itemId ? { ...x, ...(op.body as Record<string, Item[string]>), _pending: true } : x)) };
        break;
      case "delete_item":
        p = { ...p, [op.section]: p[op.section].filter((x) => x.id !== op.itemId) };
        break;
      case "document":
        p = {
          ...p,
          documents: [
            ...p.documents,
            {
              id: `pending-${capturedAt}-${p.documents.length}`,
              title: op.fileName,
              filename: op.fileName,
              mime_type: op.mime,
              size: Math.round((op.dataBase64.length * 3) / 4),
              kind: op.mime.startsWith("image/") ? "photo" : "attachment",
              section: op.section,
              item_id: op.itemId,
              created_at: capturedAt,
              thumbnail_url: null,
              _pending: true,
            } as Full["documents"][number],
          ],
        };
        break;
      case "signature":
        p = {
          ...p,
          status: p.status === "draft" || p.status === "in_progress" ? "signature_pending" : p.status,
          signatures: [
            ...p.signatures,
            {
              id: `pending-${capturedAt}-${p.signatures.length}`,
              participant_id: (op.body.participant_id as string | null) ?? null,
              signer_name: (op.body.signer_name as string | null) ?? null,
              signer_role: (op.body.signer_role as string | null) ?? null,
              signed_at: capturedAt,
              signed_location: (op.body.signed_location as string | null) ?? null,
              document_id: "",
              _pending: true,
            } as unknown as Full["signatures"][number],
          ],
        };
        break;
    }
  }
  return p;
}

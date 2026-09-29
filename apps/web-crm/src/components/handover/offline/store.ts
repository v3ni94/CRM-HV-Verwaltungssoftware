/** Storage of the sealed queue records (rule M30-10). Only the random record id and the
 *  sequence number are stored in plain text; everything else (protocol id, bodies, photos,
 *  signature images, device times) is inside the AES-GCM payload. The service worker never
 *  sees this database (public/sw.js caches the offline page and icons only). */

export type StoredRecord = { id: string; seq: number; iv: Uint8Array; data: ArrayBuffer };

export interface QueueStore {
  put(record: StoredRecord): Promise<void>;
  all(): Promise<StoredRecord[]>;
  remove(id: string): Promise<void>;
  clear(): Promise<void>;
}

/** In memory store for tests and as fallback where IndexedDB is unavailable. */
export class MemoryStore implements QueueStore {
  private records = new Map<string, StoredRecord>();
  async put(record: StoredRecord): Promise<void> {
    this.records.set(record.id, record);
  }
  async all(): Promise<StoredRecord[]> {
    return [...this.records.values()];
  }
  async remove(id: string): Promise<void> {
    this.records.delete(id);
  }
  async clear(): Promise<void> {
    this.records.clear();
  }
}

const DB_NAME = "mhvp-handover-offline";
const STORE = "records";

function request<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error("IndexedDB request failed"));
  });
}

export class IndexedDbStore implements QueueStore {
  private db: Promise<IDBDatabase> | null = null;

  private open(): Promise<IDBDatabase> {
    if (!this.db) {
      this.db = new Promise((resolve, reject) => {
        const req = indexedDB.open(DB_NAME, 1);
        req.onupgradeneeded = () => {
          if (!req.result.objectStoreNames.contains(STORE)) req.result.createObjectStore(STORE, { keyPath: "id" });
        };
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error ?? new Error("IndexedDB open failed"));
      });
    }
    return this.db;
  }

  private async tx(mode: IDBTransactionMode): Promise<IDBObjectStore> {
    return (await this.open()).transaction(STORE, mode).objectStore(STORE);
  }

  async put(record: StoredRecord): Promise<void> {
    await request((await this.tx("readwrite")).put(record));
  }
  async all(): Promise<StoredRecord[]> {
    return (await request((await this.tx("readonly")).getAll())) as StoredRecord[];
  }
  async remove(id: string): Promise<void> {
    await request((await this.tx("readwrite")).delete(id));
  }
  async clear(): Promise<void> {
    await request((await this.tx("readwrite")).clear());
  }
}

export function defaultStore(): QueueStore {
  return typeof indexedDB === "undefined" ? new MemoryStore() : new IndexedDbStore();
}

/**
 * Client side downscaling of photos before the upload (M31 WP5, portal twin of the CRM
 * helper of WP2): a 12 megapixel phone photo shrinks to at most MAX_EDGE pixels on the long
 * edge and is re-encoded as JPEG. Metadata (EXIF, location) is not copied by the canvas, the
 * server strips it again (M30-04). Anything the browser cannot decode (HEIC on Android, a
 * damaged file) is returned unchanged so the server can still accept or reject it.
 */
export const MAX_EDGE = 1600;
export const JPEG_QUALITY = 0.85;
/** Files below this size are sent as they are (no gain from re-encoding). */
export const SKIP_BELOW_BYTES = 400 * 1024;

const DOWNSCALABLE = new Set(["image/jpeg", "image/png", "image/webp"]);

export function isImageAccepted(type: string): boolean {
  return ["image/jpeg", "image/png", "image/heic", "image/heif", "image/webp"].includes(type.toLowerCase());
}

async function decode(file: File): Promise<ImageBitmap | HTMLImageElement> {
  if (typeof createImageBitmap === "function") {
    return createImageBitmap(file);
  }
  const url = URL.createObjectURL(file);
  try {
    return await new Promise<HTMLImageElement>((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error("decode failed"));
      img.src = url;
    });
  } finally {
    URL.revokeObjectURL(url);
  }
}

export async function downscaleImage(file: File): Promise<File> {
  if (typeof document === "undefined") return file;
  if (!DOWNSCALABLE.has(file.type) || file.size < SKIP_BELOW_BYTES) return file;
  try {
    const source = await decode(file);
    const width = "naturalWidth" in source ? source.naturalWidth : source.width;
    const height = "naturalHeight" in source ? source.naturalHeight : source.height;
    const scale = Math.min(1, MAX_EDGE / Math.max(width, height));
    if (scale === 1 && file.type === "image/jpeg") return file;
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(width * scale));
    canvas.height = Math.max(1, Math.round(height * scale));
    const ctx = canvas.getContext("2d");
    if (!ctx) return file;
    ctx.drawImage(source, 0, 0, canvas.width, canvas.height);
    if ("close" in source) source.close();
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", JPEG_QUALITY));
    if (!blob || blob.size >= file.size) return file;
    const name = file.name.replace(/\.[a-z0-9]+$/i, "") + ".jpg";
    return new File([blob], name, { type: "image/jpeg", lastModified: file.lastModified });
  } catch {
    return file;
  }
}

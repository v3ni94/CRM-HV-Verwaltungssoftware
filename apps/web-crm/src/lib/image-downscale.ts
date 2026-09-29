/** Client side downscale of a photo before the upload (M31 WP2): the longest edge becomes
 *  2000 px and the result a JPEG at quality 0.85, so an 8 MB phone photo travels as well
 *  under 1 MB on a weak connection. Transport only: the server pipeline `sanitize_image`
 *  (M30-04) stays the single way into the storage and strips metadata; the checksum applies
 *  to the cleaned server image (docs/rules/M30-01.md). The original file is returned when the
 *  browser cannot decode it (HEIC without decoder), when it is already small or when no canvas
 *  is available. Nothing is stored in the browser. */

export const MAX_EDGE = 2000;
export const SMALL_BYTES = 1.5 * 1024 * 1024;

export async function downscale(file: File, maxEdge = MAX_EDGE): Promise<File> {
  if (typeof createImageBitmap !== "function" || typeof document === "undefined") return file;
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    return file;
  }
  try {
    const { width, height } = bitmap;
    if (!width || !height) return file;
    const longest = Math.max(width, height);
    if (longest <= maxEdge && file.size <= SMALL_BYTES) return file;
    const scale = Math.min(1, maxEdge / longest);
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(width * scale));
    canvas.height = Math.max(1, Math.round(height * scale));
    const ctx = canvas.getContext("2d");
    if (!ctx) return file;
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((resolve) => {
      try {
        canvas.toBlob((b) => resolve(b), "image/jpeg", 0.85);
      } catch {
        resolve(null);
      }
    });
    if (!blob) return file;
    const name = file.name.replace(/\.[^.]+$/, "") + ".jpg";
    return new File([blob], name, { type: "image/jpeg", lastModified: file.lastModified });
  } finally {
    if (typeof bitmap.close === "function") bitmap.close();
  }
}

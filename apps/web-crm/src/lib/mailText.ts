/** Helpers for the ticket mail thread (operator 26.09.2026): quote folding of plain text
 *  mails and human readable sizes. Pure functions, no DOM. */

const QUOTE_START = [
  /^>\s?/, // quoted line
  /^-{2,}\s*(Ursprüngliche Nachricht|Original Message|Originalnachricht|Weitergeleitete Nachricht|Forwarded message)\s*-{2,}/i,
  /^(Am|On) .{4,120}(schrieb|wrote)\b.*:?\s*$/i,
  /^Von:\s.+$/,
  /^From:\s.+$/,
  /^_{5,}\s*$/,
];

/** Splits a plain text mail into the visible part and the quoted tail (previous mails). The
 *  quoted part starts at the first line that opens a quote block; a lone ">" line inside
 *  the own text is only treated as quote when everything after it is quoted or empty. */
export function splitQuoted(text: string | null | undefined): { visible: string; quoted: string | null } {
  if (!text) return { visible: "", quoted: null };
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  let start = -1;
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i] ?? "";
    if (QUOTE_START.some((re) => re.test(line))) {
      start = i;
      break;
    }
  }
  if (start <= 0) {
    if (start === 0) return { visible: "", quoted: text.trim() || null };
    return { visible: text.trim(), quoted: null };
  }
  const visible = lines.slice(0, start).join("\n").trim();
  const quoted = lines.slice(start).join("\n").trim();
  return { visible, quoted: quoted || null };
}

export function formatBytes(size: number | null | undefined): string {
  if (size === null || size === undefined || Number.isNaN(size)) return "";
  if (size < 1024) return `${size} B`;
  const kb = size / 1024;
  if (kb < 1024) return `${kb.toFixed(kb < 10 ? 1 : 0).replace(".", ",")} KB`;
  const mb = kb / 1024;
  return `${mb.toFixed(mb < 10 ? 1 : 0).replace(".", ",")} MB`;
}

export const PREVIEW_MIME_TYPES = ["application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp"];

export function isPreviewable(mime: string | null | undefined): boolean {
  return Boolean(mime) && PREVIEW_MIME_TYPES.includes(String(mime));
}

/** Loose address list parsing for the reply form ("a@x.de, b@y.de"). */
export function parseAddressList(value: string): string[] {
  return value
    .split(/[,;\n]/)
    .map((a) => a.trim())
    .filter(Boolean);
}

export function isValidAddress(value: string): boolean {
  return /^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/.test(value);
}

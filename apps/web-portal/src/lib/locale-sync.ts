import { bff } from "@/lib/bff";
import { LOCALE_COOKIE, isLocale, type PortalLocale } from "@/lib/locale";

/** GA11-01: the language is stored at the portal account (PATCH /portal/me/locale). Errors are
 *  ignored on purpose: the cookie keeps the choice for the browser, the account copy is a bonus. */
export async function persistAccountLocale(locale: PortalLocale): Promise<void> {
  try {
    await bff("/api/bff/portal/me/locale", { method: "PATCH", body: JSON.stringify({ locale }) });
  } catch {
    /* best effort */
  }
}

export function readLocaleCookie(cookieString: string): PortalLocale | undefined {
  const entry = cookieString.split(";").map((part) => part.trim()).find((part) => part.startsWith(`${LOCALE_COOKIE}=`));
  const value = entry?.slice(LOCALE_COOKIE.length + 1);
  return isLocale(value) ? value : undefined;
}

/** After sign-in: the language stored at the account wins and is written to the cookie; an
 *  account without a choice takes over the language the visitor picked on the sign-in page. */
export async function adoptAccountLocale(): Promise<void> {
  try {
    const me = await bff<{ locale?: string | null }>("/api/bff/portal/me");
    if (!me.ok) return;
    const stored = me.data.locale;
    const current = readLocaleCookie(document.cookie);
    if (isLocale(stored)) {
      if (stored !== current) {
        await fetch("/api/locale", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ locale: stored }),
        });
      }
    } else if (current) {
      await persistAccountLocale(current);
    }
  } catch {
    /* best effort */
  }
}

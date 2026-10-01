import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { legalLinks, type LegalCode, type PortalBranding } from "@/lib/branding";

const LABEL: Record<LegalCode, "imprint" | "privacy" | "terms"> = {
  impressum: "imprint",
  datenschutz: "privacy",
  nutzungsbedingungen: "terms",
};

/** Logo (light and dark variant, PNG or JPEG) and name of the tenant; the neutral product name
 *  when the tenant configured neither. The logo comes from the same-origin route
 *  /api/branding-logo, the name is always rendered as text for assistive technology. */
export async function BrandMark({ branding, fallback }: { branding: PortalBranding; fallback: string }) {
  const t = await getTranslations("Branding");
  const name = branding.name ?? fallback;
  const hasLogo = branding.hasLogoLight || branding.hasLogoDark;
  return (
    <div className="mb-1 flex items-center gap-3">
      {hasLogo ? (
        <>
          {/* eslint-disable-next-line @next/next/no-img-element -- tenant logo, dynamic source */}
          <img
            src={`/api/branding-logo/${branding.hasLogoLight ? "light" : "dark"}`}
            alt={t("logoAlt", { name })}
            className={`h-8 w-auto max-w-[8rem] object-contain ${branding.hasLogoLight && branding.hasLogoDark ? "brand-logo-day" : ""}`}
          />
          {branding.hasLogoLight && branding.hasLogoDark ? (
            // eslint-disable-next-line @next/next/no-img-element -- tenant logo, dynamic source
            <img src="/api/branding-logo/dark" alt="" aria-hidden className="brand-logo-evening h-8 w-auto max-w-[8rem] object-contain" />
          ) : null}
        </>
      ) : null}
      <p className="mhvp-label">{name}</p>
    </div>
  );
}

/** Imprint, privacy and terms links of the tenant (AE29): the released text on the portal page
 *  /rechtliches/<code>, else the https link of the branding; nothing when neither exists. */
export async function LegalLinks({ branding }: { branding: PortalBranding }) {
  const links = legalLinks(branding);
  if (links.length === 0) return null;
  const t = await getTranslations("Branding");
  return (
    <p className="flex flex-wrap gap-x-3 text-xs text-subtle">
      {links.map((link) =>
        link.external ? (
          <a key={link.code} href={link.href} className="underline hover:text-fg" rel="noopener noreferrer" target="_blank">
            {t(LABEL[link.code])}
          </a>
        ) : (
          <Link key={link.code} href={link.href} className="underline hover:text-fg">
            {t(LABEL[link.code])}
          </Link>
        ),
      )}
    </p>
  );
}

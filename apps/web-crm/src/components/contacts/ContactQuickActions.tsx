import { useTranslations } from "next-intl";

import { ui } from "@/lib/ui";

/** Call and e-mail actions of a contact head (M31 WP3): 44 px targets that open the phone or
 *  mail app of the device via `tel:` and `mailto:`. Rendered only for values that exist. No
 *  hooks beyond translations, so server pages may render it. */
export function ContactQuickActions({ phone, email, className = "" }: { phone?: string | null; email?: string | null; className?: string }) {
  const t = useTranslations("Contacts");
  if (!phone && !email) return null;
  return (
    <div className={`flex flex-wrap gap-2 ${className}`.trim()} data-testid="contact-quick-actions">
      {phone ? (
        <a href={`tel:${phone.replace(/\s+/g, "")}`} className={ui.button} data-testid="contact-call">
          {t("call")}
        </a>
      ) : null}
      {email ? (
        <a href={`mailto:${email}`} className={ui.button} data-testid="contact-mail">
          {t("mail")}
        </a>
      ) : null}
    </div>
  );
}

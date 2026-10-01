import { useTranslations } from "next-intl";

import type { LegalText } from "@/lib/legal-texts";
import { ui } from "@/lib/ui";

/** Legal text of the tenant (AE29): the approved version as plain text, otherwise the marker
 *  "Text nicht freigegeben" (with the external https link of the branding, if any). No HTML is
 *  rendered, the text keeps its line breaks. */
export function LegalTextView({ text }: { text: LegalText | null }) {
  const t = useTranslations("Legal");
  const code = (text?.code ?? "impressum") as "impressum" | "datenschutz" | "nutzungsbedingungen";
  return (
    <article className="flex flex-col gap-3" aria-labelledby="legal-title" data-testid={`legal-${code}`}>
      <h1 id="legal-title" className={ui.title}>
        {text?.title ?? t(`title.${code}`)}
      </h1>
      {text === null ? (
        <p role="alert" className={ui.alert}>
          {t("loadFailed")}
        </p>
      ) : text.released ? (
        <>
          <p className="text-xs text-subtle">
            {t("version", { version: text.version ?? 0 })}
            {code === "nutzungsbedingungen" && text.termsVersion ? ` · ${t("termsVersion", { label: text.termsVersion })}` : ""}
          </p>
          <div className="whitespace-pre-wrap break-words text-sm">{text.body}</div>
        </>
      ) : (
        <>
          <p className="text-sm font-medium">{t("notReleased")}</p>
          <p className="text-sm text-muted">{t("notReleasedHint")}</p>
          {text.externalUrl ? (
            <p className="text-sm">
              <a href={text.externalUrl} className="underline" rel="noopener noreferrer" target="_blank">
                {t("externalLink")}
              </a>
            </p>
          ) : null}
        </>
      )}
    </article>
  );
}

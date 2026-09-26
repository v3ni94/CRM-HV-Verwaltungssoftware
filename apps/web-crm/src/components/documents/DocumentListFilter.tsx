import { useTranslations } from "next-intl";

import { ui } from "@/lib/ui";

/** Values of the draft filter as they appear in the URL and are passed to
 *  `GET /api/v1/documents?is_draft=`: "" no filter, "true" drafts only, "false" without drafts. */
export const DRAFT_FILTERS = ["", "true", "false"] as const;
export type DraftFilter = (typeof DRAFT_FILTERS)[number];

export function draftFilterOf(value: string | undefined): DraftFilter {
  return value === "true" || value === "false" ? value : "";
}

/** Search form of the document list: full text and the draft select (A83, automatically
 *  generated letters are marked as Entwurf). Plain GET form, works without client JavaScript. */
export function DocumentListFilter({ q, draft }: { q: string; draft: DraftFilter }) {
  const t = useTranslations("DocumentList");
  return (
    <form className="grid gap-3 md:grid-cols-[auto_1fr_auto] md:items-end" role="search">
      <div>
        <label htmlFor="entwurf" className={ui.label}>
          {t("draftFilter")}
        </label>
        <select id="entwurf" name="entwurf" defaultValue={draft} className={ui.input}>
          <option value="">{t("draftAll")}</option>
          <option value="true">{t("draftOnly")}</option>
          <option value="false">{t("draftNone")}</option>
        </select>
      </div>
      <div>
        <label htmlFor="q" className={ui.label}>
          {t("search")}
        </label>
        <input id="q" name="q" defaultValue={q} placeholder={t("searchPlaceholder")} className={ui.input} />
      </div>
      <button type="submit" className={ui.button}>
        {t("search")}
      </button>
    </form>
  );
}

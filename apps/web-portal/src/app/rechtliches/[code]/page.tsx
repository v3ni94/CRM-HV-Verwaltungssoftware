import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { notFound } from "next/navigation";

import { LegalTextView } from "@/components/portal/LegalTextView";
import { fetchLegalText, isLegalCode } from "@/lib/legal-texts";
import { ui } from "@/lib/ui";

export const dynamic = "force-dynamic";

/** Impressum, Datenschutz und Nutzungsbedingungen des Mandanten (AE29, M21-04): öffentlich ohne
 *  Anmeldung, nur die freigegebene Fassung. Ohne Freigabe steht der Vermerk "Text nicht
 *  freigegeben", die Software liefert keine eigenen Rechtstexte. */
export default async function LegalPage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  if (!isLegalCode(code)) notFound();
  const [t, text] = await Promise.all([getTranslations("Legal"), fetchLegalText(code)]);
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-5 px-4 py-8">
      <LegalTextView text={text} />
      <Link href="/" className={`${ui.secondary} ${ui.actionFull} w-fit`}>
        {t("back")}
      </Link>
    </div>
  );
}

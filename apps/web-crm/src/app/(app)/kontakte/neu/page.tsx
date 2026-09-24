import { getTranslations } from "next-intl/server";

import { ContactForm } from "@/components/contacts/ContactForm";
import { ui } from "@/lib/ui";

export default async function NewContactPage() {
  const t = await getTranslations("ContactForm");
  return (
    <div className="flex flex-col gap-4">
      <h1 className={ui.title}>{t("titleNew")}</h1>
      <ContactForm mode="create" />
    </div>
  );
}

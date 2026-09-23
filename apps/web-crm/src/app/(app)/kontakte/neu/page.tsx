import { getTranslations } from "next-intl/server";

import { ContactForm } from "@/components/contacts/ContactForm";

export default async function NewContactPage() {
  const t = await getTranslations("ContactForm");
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-xl font-semibold">{t("titleNew")}</h1>
      <ContactForm mode="create" />
    </div>
  );
}

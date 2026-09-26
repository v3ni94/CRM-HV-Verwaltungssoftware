"use client";

import { useTranslations } from "next-intl";

import type { PropertyContacts } from "@/components/portal/types";
import { ui } from "@/lib/ui";

/** Ansprechpartner je Objekt (A51): zuständige Verwaltung, Hausmeister und Notdienst, soweit
 *  in den Stammdaten für Eigentümer freigegeben. Keine privaten Daten. */
export function PropertyContactList({ rows }: { rows: PropertyContacts[] }) {
  const t = useTranslations("Contacts");
  if (rows.length === 0) return <p className={ui.notice}>{t("empty")}</p>;
  return (
    <ul className="flex flex-col gap-3">
      {rows.map((row) => (
        <li key={row.property_id} className={`${ui.card} flex flex-col gap-3`}>
          <div className="flex flex-col gap-0.5">
            <span className="font-medium">
              {row.property_number} {row.property_name}
            </span>
            {row.address ? <span className="text-sm text-muted">{row.address}</span> : null}
          </div>
          <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-[10rem_1fr]">
            <dt className={ui.label}>{t("manager")}</dt>
            <dd>{row.manager_name ?? t("managerUnknown")}</dd>
            {row.contacts.map((contact, i) => (
              <ContactRow key={`${contact.category}-${i}`} contact={contact} />
            ))}
          </dl>
          {row.contacts.length === 0 ? <p className={ui.help}>{t("noContacts")}</p> : null}
        </li>
      ))}
    </ul>
  );
}

function ContactRow({ contact }: { contact: PropertyContacts["contacts"][number] }) {
  const t = useTranslations("Contacts");
  const label = contact.category === "caretaker" || contact.category === "emergency" ? t(`category.${contact.category}`) : contact.category;
  return (
    <>
      <dt className={ui.label}>{label}</dt>
      <dd className="flex flex-col gap-0.5">
        <span>{contact.name}</span>
        {contact.phones.map((phone) => (
          <a key={phone} href={`tel:${phone}`} className="text-muted underline">
            {phone}
          </a>
        ))}
      </dd>
    </>
  );
}

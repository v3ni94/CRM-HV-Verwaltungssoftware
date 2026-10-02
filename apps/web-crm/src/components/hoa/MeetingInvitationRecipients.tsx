import { useTranslations } from "next-intl";

export type InvitationRecipientRow = {
  contract_id: string;
  unit_number: string | null;
  party_name: string | null;
  recipients: { contact_id: string; display_name: string | null; channel: string; represents_name: string | null }[];
};

/** GAF-15: Empfängerliste der Einladung je Eigentumsvertrag (Zustellregel der Bevollmächtigten).
 *  Nur Anzeige, ohne Versand. */
export function MeetingInvitationRecipients({ rows }: { rows: InvitationRecipientRow[] }) {
  const t = useTranslations("HoaAF09.recipients");
  return (
    <section className="flex flex-col gap-2" data-testid="invitation-recipients">
      <h2 className="text-base font-semibold">{t("title")}</h2>
      <p className="text-sm text-muted">{t("hint")}</p>
      {rows.length === 0 ? (
        <p className="text-sm text-muted">{t("none")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="mhvp-table">
            <thead>
              <tr>
                <th>{t("unit")}</th>
                <th>{t("party")}</th>
                <th>{t("recipient")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.contract_id}>
                  <td>{r.unit_number ?? ""}</td>
                  <td>{r.party_name ?? ""}</td>
                  <td>
                    {r.recipients.length === 0
                      ? t("none")
                      : r.recipients.map((x) => (
                          <div key={`${x.contact_id}-${x.represents_name ?? ""}`}>
                            {x.display_name ?? ""} · {t("channel")}: {x.channel}
                            {x.represents_name ? ` · ${t("represents", { name: x.represents_name })}` : ""}
                          </div>
                        ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

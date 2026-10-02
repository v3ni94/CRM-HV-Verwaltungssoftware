# Zuordnung Glossar (MASTER-PROMPT 20) zu Codebegriffen

Stand: 02.10.2026 (GAI-117). Das Glossar nennt Codebegriffe, die im Quelltext teils anders heißen. Umbenannt wird
nicht ungefragt (Glossar). Diese Tabelle dokumentiert die tatsächliche Abbildung. Pfade relativ zu
`apps/api/src/mhvp/`. Spalte Abweichung: "ja" heißt, der Glossarbegriff kommt im Code nicht oder nicht als Klasse
vor. Zeilen mit "zu bestätigen" wurden nur per Namenssuche zugeordnet.

| Glossar (Deutsch) | Glossar (Code) | Tatsächlicher Codebegriff | Fundstelle | Abweichung |
| --- | --- | --- | --- | --- |
| Mandant | `tenant` | `Tenant` | `platform/models.py` | nein |
| Objekt | `property` | `Property` | `properties/models.py` | nein |
| Gebäude | `building` | `Building` | `properties/models.py` | nein |
| Verwaltungseinheit | `unit` | `Unit` | `properties/models.py` | nein |
| Miteigentumsanteil (MEA) | `co_ownership_share` | Umlageschlüssel `AllocationKey` mit zeitlich gültigem Einheitswert `UnitAllocationValue`; Wert je Einheit, Referenzsumme `expected_total` | `properties/models.py` | ja, kein Feld `co_ownership_share` |
| Umlageschlüssel | `allocation_key` | `AllocationKey` | `properties/models.py` | nein |
| Vertrag | `contract` (`tenancy`, `ownership`) | `Contract` mit `ContractKind` | `contracts/models.py` | nein |
| Vertragspartei, Haushalt | `party` | `Party` | `contacts/models.py` | nein |
| Mieter | `tenant_resident` (Rolle) | Vertrag mit `ContractKind.TENANCY`; Kontaktrolle über `ContactRoleCode` | `contracts/models.py`, `contacts/models.py` | ja, kein Rollenname `tenant_resident` |
| Eigentümer | `owner` | `ContactRoleCode.OWNER` | `contacts/models.py` | nein |
| Wohnungseigentümergemeinschaft | `hoa` | Rechtsträger `LegalEntityKind` (hoa), Domäne `hoa` | `properties/models.py`, `hoa/` | nein |
| Hausgeld | `hoa_fee` | Hausgeld als Zahlungsart und Plan in `hoa/` und `accounting/` (Vorschüsse aus dem Wirtschaftsplan) | `hoa/`, `accounting/` | zu bestätigen |
| Erhaltungsrücklage | `reserve` | `HoaReserve`, `HoaReserveMovement`, `HoaReservePlan` | `hoa/models.py` | Präfix `Hoa` |
| Wirtschaftsplan | `economic_plan` | `EconomicPlan` | `hoa/models.py` | nein |
| Hausgeldabrechnung | `hoa_fee_statement` | `HoaStatement` (Jahresabrechnung der GdWE) | `hoa/models.py` | ja, anderer Name |
| Betriebskostenabrechnung | `operating_cost_statement` | `Statement` mit `StatementKind` (Domäne `billing`); als Eingabeschlüssel `operating_cost_statements` der Eigentümerabrechnung | `billing/models.py`, `billing/owner_statement.py` | ja, anderer Name |
| Abrechnung Mietobjekt | `owner_statement` | `StatementKind.OWNER_STATEMENT` (Eigentümerabrechnung der Mietverwaltung) | `properties/models.py`, `billing/owner_statement.py` | nein |
| Sollstellung | `receivable` | `ReceivableRun`, `ReceivableItem` | `accounting/models.py` | Präfix, Plural |
| Offener Posten | `open_item` | `OpenItem` | `accounting/models.py` | nein |
| Buchungskreis | `ledger` | `Ledger` | `accounting/models.py` | nein |
| Buchungssatz, Buchungszeile | `journal_entry`, `journal_line` | `JournalEntry`, `JournalLine` | `accounting/models.py` | nein |
| Mahnung, Mahnlauf | `dunning_case`, `dunning_run` | `DunningCase`, `DunningRun` | `accounting/models.py` | nein |
| Zahllauf | `payment_run` | `PaymentBatch`, `PaymentOrder` | `banking/models.py` | ja, anderer Name |
| Kaution | `deposit` | `Deposit` | `contracts/models.py` | nein |
| Eigentümerversammlung | `meeting` | `Meeting` | `hoa/models.py` | nein |
| Tagesordnungspunkt | `agenda_item` | `AgendaItem` | `hoa/models.py` | nein |
| Beschluss-Sammlung | `resolution` | `Resolution` | `hoa/models.py` | nein |
| Verwaltungsbeirat | `board` | Kontaktrolle `ContactRoleCode.BOARD_MEMBER` | `contacts/models.py` | ja, Rolle statt Objekt |
| Ticket, Auftrag | `ticket`, `work_order` | `Ticket`, `WorkOrder` | `tickets/models.py` | nein |
| Dienstleister | `service_provider` | `ContactRoleCode.SERVICE_PROVIDER` | `contacts/models.py` | nein, als Rolle |
| Messdienst | `metering_service` | `MeteringConnection`, `MeteringExternalBillingUnit`, `MeteringPropertyAssignment` (Domäne `metering`) | `metering/models.py` | ja, anderer Name |
| Verwalterhonorar | `admin_fee` | `AdminFeeSetting`, `AdminFeeInvoice` | `accounting/models.py` | Präfix |
| Zustellweg | `delivery_channel` | Zustellung in `communication/` und `billing/` (Kanäle Post, E-Mail, Portal) | `communication/`, `billing/models.py` | zu bestätigen |
| Schwarzes Brett | `notice_board` | `PropertyNotice`, Lesenachweis `NoticeBoardRead` | `portal/notices.py`, `portal/models.py` | ja, Tabelle `property_notice` |
| Festschreibung | `lock` | Periodensperre im Buchungskreis (`accounting/`) | `accounting/` | zu bestätigen |

## Pflege

Bei einer Umbenennung im Code nur auf Anweisung des Betreibers. Neue Glossarbegriffe erhalten hier bei der
Einführung eine Zeile. Frage zur Vereinheitlichung (Umbenennung gegen Tabelle): OPEN_QUESTIONS AJ15-02.

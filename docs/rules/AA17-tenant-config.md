# AA17 Mandantenkonfiguration: Zustellweg, Nummernkreise, Ordnerschema, Domains, OIDC-Clients

| Field | Content |
| --- | --- |
| ID | `AA17` (GA01-06 bis GA01-12) |
| Title | Standard-Zustellweg, Nummernkreise je Mandant (vorbereitet), Ordnerschema der Drive-Ablage, Kundendomains und Mandantenstatus, OIDC-Clients per API und Oberfläche, E2E-Kernpfade |
| Scope | `mhvp.platform.admin_routers`, `mhvp.core.number_format`, `mhvp.documents.folder_scheme`, `communication.dispatch`, `contracts.services.contract_number`; CRM Einstellungen Nummernkreise, DMS-Maske, Plattform Domains und OIDC-Clients; Migration 0319 ist ein Platzhalter |
| Source status | Fachliche Umsetzung nach 5.2, 3.3 und 3.4. Keine Rechtsnorm zitiert. Der Rechnungsnummernkreis betrifft umsatzsteuerliche Pflichtangaben und bleibt gesperrt (Offene Frage AA17-01) |
| Acceptance case | `tests/integration/test_aa17_tenant_admin.py`, `tests/unit/test_aa17_formats.py`, `TenantDefaultsAdmin.test.tsx`, `e2e/core-paths-ga01.backend.spec.ts` (nicht ausgeführt) |
| Change reason | Lückenliste 01.10.2026, Welle 12, Paket AA17 |

## Regeln

1. Standard-Zustellweg (`GET/PUT /tenant/delivery-default`, `tenant_settings:read/update`): post, email oder portal, gespeichert in `tenant_settings.sources`. Reihenfolge im Versand: Kanal der Position, Präferenz des Kontakts, Standard des Mandanten, sonst post.
2. Nummernkreise (`GET/PUT /tenant/number-formats`, `POST .../preview`): Präfix (A bis Z, 0 bis 9, höchstens 10 Zeichen), Stellenzahl 1 bis 12, Startwert, Jahresbezug. Ohne Eintrag gelten die bisherigen Formate (Vertrag 6 Stellen, Objekt 3, Ticket und Beleg unformatiert, Rechnung MR-JJJJ-NNNNNN). Angewendet wird die Konfiguration derzeit nur bei Vertragsnummern; der Startwert wirkt nur auf einen noch nicht benutzten Nummernkreis. Objekt, Beleg, Ticket und Rechnung sind vorbereitet, die Erzeugung bleibt unverändert.
3. Der Rechnungsnummernkreis ist gesperrt (`INVOICE_FORMAT_RELEASED = False`), Änderungen antworten 422 bis zur Freigabe durch den Steuerberater.
4. Ordnerschema: `dms_connection.options["folder_scheme"]` (Drive), Platzhalter `{objekt}`, `{jahr}`, `{kategorie}`, höchstens 5 Ebenen, `{objekt}` Pflicht; Standard `{objekt}/{jahr}`. Wirkt auf die Direktablage (`property_filing`). Die Spiegelung nach festen Kategorieordnern 01 bis 06 bleibt unverändert.
5. Kundendomains: `GET/POST /platform/tenants/{id}/domains`, `DELETE .../domains/{domain_id}`, nur Plattformadministrator; Hostname eindeutig über alle Mandanten, Zweck portal, crm oder api. Der CNAME-Hinweis ist ein Text; eine DNS-Prüfung findet nicht statt. `PATCH /platform/tenants/{id}` setzt den Status active oder suspended (protokolliert).
6. OIDC-Clients: `GET/POST /platform/oidc-clients`, `POST .../{client_id}/rotate-secret|activate|deactivate`, nur Plattformadministrator. Das Secret erscheint einmal in der Antwort, gespeichert wird nur der SHA-256-Hash. Die Befehlszeile bleibt erhalten.

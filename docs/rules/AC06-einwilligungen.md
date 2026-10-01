# AC06-einwilligungen: Einwilligungen steuern die Verarbeitung

- ID: AC06-einwilligungen (Befund GA02-06)
- Geltungsbereich: alle Mandanten; Module contacts (consent, consent_rules), communication (Dispatch, Serienversand), portal (Aktivierung, Zugang).
- Spezifikation: 6.1 consent (kind data_sharing, portal_terms, email_delivery, marketing), 7.11 S06 (Pflichtverarbeitung nicht ausschließlich auf widerrufliche Einwilligung stützen).
- Quellenstatus (Anhang C): keine Rechtsquelle im Register für die Einordnung je Zweck. Anforderungstyp Fachliche Umsetzung; die rechtliche Einordnung ist Offene Entscheidung (AC06-01 bis AC06-03). Es werden keine Rechtstexte erstellt.
- Abnahmefall: kein eigener Fall in Anhang D; Tests in apps/api/tests/integration/test_ac06_consents.py, test_ad03_data_sharing.py, apps/web-portal/src/components/auth/TermsAcceptForm.test.tsx und apps/web-crm/src/components/contacts/SerialDispatchForm.test.tsx.

## Gültigkeit

Eine Einwilligung gilt, wenn granted_at nicht in der Zukunft liegt und sie nicht widerrufen ist (A-AC06-01). Ein Widerruf wirkt sofort für folgende Verarbeitungen.

## Regeln je Art

| Art | Verarbeitung | Ohne gültige Einwilligung | Protokoll |
| --- | --- | --- | --- |
| marketing | Serienversand (POST /dispatches/serial, /dispatches/serial-merge) mit advertising=true | Kontakt wird übersprungen und gezählt (consent.marketing_skipped) | Ereignis dispatch.marketing_skipped mit Grund marketing_consent_missing |
| email_delivery | Zustellung eines Dokuments per E-Mail im Dispatch | Zustellweg fällt auf post zurück, außer Mandantenregel consent_or_contract | Ereignis dispatch.channel_fallback mit Grund email_delivery_consent_missing, Zähler consent.email_fallback_to_post |
| portal_terms | Portalaktivierung (POST /portal/invitations/accept) und jeder Portalzugriff | Bei veröffentlichter Fassung keine Aktivierung und kein Zugang, Fehler MHVP-CONT-0020 | consent mit source portal_terms_version=<Fassung>, Ereignis consent.granted |
| data_sharing | Weitergabe von Kontaktdaten an Dienstleister | Prüfung consent_rules.data_sharing_decision verneint mit Grund data_sharing_consent_missing; vertragliche Notwendigkeit zählt nur bei Mandantenregel consent_or_contract | Grund im Ergebnis der Prüfung |

Pflichtkommunikation (Abrechnungen, Mahnungen, Einladungen) wird nicht an marketing geprüft (A-AC06-02).

## Schalter je Mandant

GET und PUT /api/v1/consent-policy (lesen contacts:read, setzen contacts:approve, Ereignis consent_policy.updated), gespeichert in tenant_settings.sources.consent_policy:

- email_delivery: consent_only (Standard) oder consent_or_contract
- data_sharing: consent_only (Standard) oder consent_or_contract
- portal_terms_version: leer (Standard, keine Nutzungsbedingungen veröffentlicht) oder Fassung

Die Standardwerte sind die restriktive Variante. Eine Erweiterung ist eine Entscheidung des Betreibers nach Klärung von AC06-01 bzw. AC06-02.

## Weitergabestellen data_sharing (AD03)

| Stelle | Prüfung | Ohne Erlaubnis | Protokoll |
| --- | --- | --- | --- |
| Auftrag an Dienstleister (tickets, Portal GET /portal/work-orders) | Kontakt des Tickets (Feld contact_id, sonst Ersteller) wird nur mit gültiger data_sharing-Einwilligung weitergegeben; vertragliche Notwendigkeit zählt bei Mandantenregel consent_or_contract. Die Prüfung läuft bei jedem Lesen, ein Widerruf wirkt sofort | Auftrag ohne personenbezogene Felder (resident_contact.contact leer, shared false mit Grund) | Ereignis work_order.contact_data_withheld bzw. work_order.contact_data_shared beim Anlegen, Antwortfeld contact_share |
| Webhook contact.updated (automation, beim Einreihen in den Ausgang) | Prüfung des betroffenen Kontakts, ausschließlich Einwilligung (keine vertragliche Notwendigkeit) | Nutzlast ohne event.payload und entity, Kennzeichen personal_data_withheld | Ereignis automation.webhook_data_withheld mit Grund data_sharing_consent_missing |

Nur zu contact.updated wird geprüft; andere Ereignisarten behalten ihre Nutzlast (Offen AD03-02).

## Portal Nutzungsbedingungen (AD03)

- Nach der Anmeldung leitet das Portal bei veröffentlichter Fassung ohne Annahme auf /nutzungsbedingungen weiter (Abfrage GET /portal/terms, BFF-Pfade portal/terms und portal/terms/accept). Die Annahme ruft POST /portal/terms/accept mit accept_terms und terms_version.
- Bei der Aktivierung der Einladung erscheint nach der Antwort MHVP-CONT-0020 die Annahmebox mit der Fassung aus der Fehlermeldung, der nächste Versuch sendet accept_terms und terms_version.
- Der Text der Nutzungsbedingungen wird nicht von der Plattform erzeugt (AC06-03).

## Offen

- data_sharing: Einordnung der Weitergabe an Dienstleister (AC06-02); weitere Weitergabestellen (Export an Dritte, andere Webhook-Ereignisse mit Kontaktbezug) sind nicht geprüft (AD03-02).
- portal_terms: Text und Fassung der Nutzungsbedingungen (AC06-03). Die Fassung vor der Aktivierung liefert seit AE34 der öffentliche Abruf `GET /portal/public/terms`; die Fehlermeldung MHVP-CONT-0020 bleibt als Rückfall.

## Änderungsgrund

Befund GA02-06 (Lückenliste 01.10.2026): die Arten wurden erfasst, aber nur whatsapp ausgewertet. AD03: Einbau an den Weitergabestellen und Portal-Annahmemaske.

## Rechtsgrundlage je Verarbeitung (AE34)

Die Rechtsgrundlage je Verarbeitung (Einwilligung, Vertrag, berechtigtes Interesse), der Widerspruch bei berechtigtem Interesse, der öffentliche Abruf der veröffentlichten Fassung und der Nachweis der Annahme in Textform (Zeit, Fassung, Hash der Client-Adresse) stehen in der Regel [AE34-01](AE34-01.md). Die Standardwerte dieser Regel bleiben die restriktive Variante.

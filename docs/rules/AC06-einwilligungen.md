# AC06-einwilligungen: Einwilligungen steuern die Verarbeitung

- ID: AC06-einwilligungen (Befund GA02-06)
- Geltungsbereich: alle Mandanten; Module contacts (consent, consent_rules), communication (Dispatch, Serienversand), portal (Aktivierung, Zugang).
- Spezifikation: 6.1 consent (kind data_sharing, portal_terms, email_delivery, marketing), 7.11 S06 (Pflichtverarbeitung nicht ausschließlich auf widerrufliche Einwilligung stützen).
- Quellenstatus (Anhang C): keine Rechtsquelle im Register für die Einordnung je Zweck. Anforderungstyp Fachliche Umsetzung; die rechtliche Einordnung ist Offene Entscheidung (AC06-01 bis AC06-03). Es werden keine Rechtstexte erstellt.
- Abnahmefall: kein eigener Fall in Anhang D; Tests in apps/api/tests/integration/test_ac06_consents.py und apps/web-crm/src/components/contacts/SerialDispatchForm.test.tsx.

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

## Offen

- data_sharing: Einbau der Prüfung an den Weitergabestellen in tickets (Auftrag) und automation (Webhook contact.updated) steht aus (AC06-02).
- portal_terms: Anzeige und Annahmemaske im Portal (apps/web-portal) sowie Text der Nutzungsbedingungen (AC06-03).

## Änderungsgrund

Befund GA02-06 (Lückenliste 01.10.2026): die Arten wurden erfasst, aber nur whatsapp ausgewertet.

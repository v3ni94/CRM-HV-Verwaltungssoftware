# Portal: Freigabe je Unterlagenklasse, Sprachwahl, Formularelemente (AA14)

| Field | Content |
| --- | --- |
| ID | AA14 (GA03-05, GA11-01, GA11-02, GA11-04, GA11-05) |
| Title | Zugriffsmatrix mit Bereich document_class, Zugriffspfadprotokoll, Sprachwahl, 20 Formularelementtypen, Rahmenverträge und Verfügbarkeit |
| Scope | Portalzugänge aller Rollen (Mieter, Eigentümer, Beirat, Dienstleister); Dokumentzugriff über API, Direkt-Download, Sammel-Download, Suche, Export und KI-Abruf |
| Source status | 6.9.6 (access_grant scope_type document_class) und Abschnitt 14 (Zugriffsvorgaben, mehrsprachig, Dienstleister Phase 4) der Spezifikation. Die Zuordnung einer Unterlagenklasse zu einer Rolle ist eine Entscheidung der Verwaltung, keine abgeleitete Rechtsregel; die Aufbewahrungsklasse (Anhang C, V17) bleibt unverändert und entscheidet nichts über Einsichtsrechte |
| Acceptance case | keiner in Anhang D; `tests/integration/test_aa14_access_paths.py` (Pfadprotokoll vor und nach der Freigabe, abgelaufene Freigabe, 403, 404 anderer Mandant, 422), `tests/unit/test_p13_portal_forms.py`, `apps/web-portal/src/lib/locale.test.ts` |
| Rule | Eine Freigabe `document_class` (Migration 0316) nennt Rechtsträger (`scope_id`) und Klasse (`document_class`). Sichtbar ist ein Dokument nur, wenn es mit dem Rechtsträger verknüpft ist, seine Klasse (Aufbewahrungsprofil des Dokuments, sonst der Kategorie) der Freigabe entspricht und `visibility` die Rolle der Freigabe enthält. Die Freigabe ist additiv zu den übrigen Freigaben, überlebt die Neuableitung der Vertragsfreigaben und endet mit `valid_to`. Alle Pfade nutzen `portal.access.visible_documents` bzw. `document_scope_for_user`; Export und CRM-Schnittstellen sind für Portalnutzer durch fehlende Berechtigungen gesperrt (403) |
| Sprache | Cookie `mhvp_locale`, sonst Accept-Language, sonst Deutsch; weitere Sprache nur durch Datei `messages/<code>.json` und Eintrag in `src/lib/locale.ts` (Test prüft Schlüsselgleichheit gegen Deutsch) |
| Formularelemente | 20 Typen: 12 Eingabetypen der Vorversion, fünf neue Eingabetypen (address, location, signature, consent, amount) und drei Anzeigetypen (heading, info, divider). Die Typenliste ist aus den Portalfunktionen des Abschnitts 14 abgeleitet (A-AA14-01) |
| Change reason | Lückenliste 01.10.2026, Befunde GA03-05, GA11-01, GA11-02, GA11-04, GA11-05 |

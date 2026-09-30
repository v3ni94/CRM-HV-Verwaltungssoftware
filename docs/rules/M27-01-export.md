# M27-01 Vollständiger Mandantenexport als Hintergrundjob

| Field | Content |
| --- | --- |
| ID | `M27-01-EXPORT` |
| Title | Export aller Mandantendaten (JSON Lines) und der Dokumentoriginale als ZIP, als Celery-Job nach Vier-Augen-Freigabe |
| Scope | `mhvp.platform.export_job` (Task `mhvp.platform.tenant_export`), `POST /platform/tenants/{id}/export-requests/{rid}/run`, Download über `.../download`, Spalten `job_*` an `tenant_export_request` (Migration 0264) |
| Source status | Produktschutz und Fachliche Umsetzung (5.3, Datenportabilität). Rechtsgrundlage und Vollständigkeit der Auskunft sind Betreiberprüfung (M27-03-01), kein Rechtsurteil |
| Acceptance case | keine in Anhang D; Test `apps/api/tests/integration/test_p15_platform.py::test_export_job_writes_archive_with_documents` |
| Implementation | Lesen nur im Mandantenkontext (RLS). Entitäten: Rechtsträger, Objekte, Einheiten, Kontakte, Verträge, Buchungssätze und Buchungszeilen, Rechnungen mit Zeilen, Tickets mit Kommentaren, Dokumentmetadaten. Originale nur aus dem Objektspeicher (`minio`), Fehler je Dokument im Manifest, externe Speicher werden gezählt und nicht exportiert. Felder mit Geheimnis-Kennzeichen entfallen. ZIP liegt unter `tenants/<id>/exports/<request>.zip`, Prüfsumme SHA-256 im Antrag |
| Change reason | Lückenliste 30.09.2026, M27-01 |

## Regeln

- Nur ein freigegebener Antrag startet den Job; ein laufender oder fertiger Job startet nicht doppelt, ein fehlgeschlagener darf wiederholt werden.
- Der Download liefert erst bei Status `ready`; ohne Job bleibt der synchrone kleine Export bestehen.
- Der Export ist ein Entwurf. Vor Herausgabe an Betroffene sind Daten Dritter zu prüfen (Schwärzung ist eine Rechtsfrage, P10-05).

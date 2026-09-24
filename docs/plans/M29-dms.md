# M29 DMS: Objektübernahme (objektakte) an das CRM anbinden

Stand 25.09.2026. Quelle: Repository v3ni94/objekt-bernahme_automatisieren. (Kurzname objektakte),
läuft bereits auf dem Betreiberserver als Container-Stack objektakte-* (Django, HTMX, Celery,
MariaDB, Redis), Zieldomain uebernahme.muellerhv.de, Ablage in Google Drive (ablage@muellerhv.de).
Bestand laut Architektur: 67 Objekte, 869 Einheiten. Funktionen: Sechs-Ordner-Struktur je Objekt,
Upload, OCR, dreistufige Klassifikation (Regeln, lokales Modell, externe KI mit Maskierung),
Review Center, Eigentümer- und Mieterlisten, Vollständigkeitsprüfung, Nachforderungsschreiben.

## Entscheidung: nicht in dieses Repository kopieren

objektakte ist ein eigener Django-Monolith mit eigener Datenbank, eigenen Rollen, eigener
Verschlüsselung (Drive-Token, IBAN) und laufender fachlicher Entwicklung. Ein Kopieren des Codes
in das CRM (FastAPI, PostgreSQL) hieße Neuschreiben. Die Anbindung erfolgt als Dienst:
das CRM bekommt den Reiter DMS, objektakte bleibt das System für Übernahme und Aktenablage.

## Stufen

1. **Reiter DMS im CRM** (ohne Änderung an objektakte): Absprung zu uebernahme.muellerhv.de je
   Objekt (Objektnummer NNN ist in beiden Systemen der Schlüssel), Erklärung der
   Ordnerstruktur, Link auf die Drive-Objektakte, sobald die Drive-Ordner-ID bekannt ist.
2. **Zentrale Anmeldung**: objektakte nutzt django-allauth; der Plattform-OIDC-Provider (ADR 0006
   Nr. 7) wird dort als Provider "openid_connect" konfiguriert. Konfiguration, kein Code.
   Benutzer werden weiterhin im CRM gepflegt.
3. **Lesende Schnittstelle in objektakte** (neuer Baustein im anderen Repository, Token mit
   Scopes): je Objekt Übernahmestatus, offene Review-Fälle, Vollständigkeitsprüfung,
   Dokumentliste (Titel, Klasse, Ordner, drive_file_id, sha256), Eigentümer- und Mieterliste.
   Ausgehender Webhook "Dokument abgelegt" und "Objekt übernommen" mit HMAC wie beim vorhandenen
   Paperless-Webhook. Keine direkte Datenbankkopplung (Datenschutz, IBAN-Schutz).
4. **CRM-Seite DMS mit Daten**: Kacheln je Objekt (Status, offene Fälle, fehlende Unterlagen),
   Dokumentliste mit Absprung in Drive, Verknüpfung der Dokumente als CRM-Dokumente (M6) über
   drive_file_id und sha256, Übernahme der Eigentümer- und Mieterlisten als Importvorschlag
   (M8-Muster, Testlauf, Abgleich, Freigabe).
5. **Später**: gemeinsame Objektnummernvergabe und Stammdatenführung nur im CRM; objektakte liest
   Objekte und Einheiten aus dem CRM.

## Voraussetzungen

- Entscheidung des Betreibers zu Stufe 3 (Auftrag für die Schnittstelle im objektakte-Repository;
  Schreibzugriff auf dieses Repository in einer eigenen Sitzung).
- Drive-Ordner-IDs je Objekt für den Absprung (liefert objektakte aus drive_nodes).
- Datenschutz: Zugriff des CRM nur auf maskierte Felder; keine IBAN im Klartext.

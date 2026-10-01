# Datenschutz (`mhvp.privacy`)

Abschnitt 16 und 7.11 S06 des Master-Prompts. Regeln: `docs/rules/S16-P17-privacy.md`
(Löschprofile, Löschantrag, Register) und `docs/rules/S711-10.md` (Verzeichnis, Anbieter aus der
Konfiguration). Handbuch: `docs/handbuch/datenschutz.md`.

- `models.py`: `privacy_register_entry` (Auftragsverarbeiter, Unterauftragnehmer,
  Verarbeitungstätigkeiten, Verantwortlichkeiten), `privacy_deletion_profile`,
  `privacy_erasure_request`. Migration 0266, Pflegefelder Migration 0388.
- `erasure.py`: Sperrprüfung, Vier-Augen-Freigabe und Anonymisierung eines Kontakts.
- `config_sources.py` (AE32): erkennt aus den Plattformeinstellungen (`Settings`) und den
  Konnektortabellen des Mandanten (unter RLS) die tatsächlich genutzten externen Dienste: Gmail,
  Google Kalender, IMAP/SMTP-Hosts, Google Drive, Paperless-ngx, finAPI, GoCardless,
  KI-Anbieter, Postversand (LetterXpress), WhatsApp, SMS-Gateway, Telefonanlage, Lexware Office,
  Objektspeicher, objektakte, Tracing. Ausgegeben werden nur technische Angaben (Host, Modus,
  Anzahl, aktiv), nie Zugangsdaten oder Postfachadressen. `sync` legt fehlende Dienste als
  Unterauftragnehmer an (AVV `none`, Drittland `open`, Prüfung `open`, `source_key`) und
  aktualisiert bei bestehenden Einträgen nur `source_detail`. Weitere Konnektoren werden in
  `DETECTORS` ergänzt.
- `register_doc.py`: baut das Verzeichnis als Blockstruktur und druckt sie als Markdown
  (`render`) und PDF (`render_pdf`, reportlab). Rollen von GdWE, Verwalter und Betreiber je
  Tätigkeit, Rechtsgrundlage und Drittland erscheinen wie eingetragen, leer als "offen"; offene
  Punkte werden gesammelt. Der Prüfhinweis V13 ist fester Bestandteil.
- `routers.py`: `/api/v1/privacy/*` mit `privacy:read`, `privacy:manage`, `privacy:approve`.
  Neu (AE32): `GET /privacy/register/config-sources`, `POST
  /privacy/register/config-sources/sync`, `GET /privacy/processing-records/pdf`; Registereinträge
  mit `third_country_status`, `third_country_countries`, `legal_basis`, `responsibilities`,
  `responsibility_note`, `processor_ids`.

Keine Rechtsaussage im Code: die Plattform belegt weder Rollen noch Rechtsgrundlagen noch
Drittlandangaben vor. Die operative Rechtsgrundlage für Einwilligungsprüfungen liegt im Register
`/consent-legal-basis` (AE34); `legal_basis` im Verzeichnis ist eine Dokumentationsangabe.

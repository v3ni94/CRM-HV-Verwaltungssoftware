# S16-P17 Datenschutz: Löschprofile, Löschantrag, Register, Dokumentspiegel

| Field | Content |
| --- | --- |
| ID | `S16-P17` |
| Title | Löschprofile je Datenart, Löschantrag nach Art. 17 DSGVO mit Sperrprüfung und Vier-Augen-Freigabe (Anonymisierung), Register der Auftragsverarbeiter und Verarbeitungstätigkeiten mit generiertem Entwurf des Verarbeitungsverzeichnisses, Metadatenabgleich der Dokumentspiegel |
| Scope | `mhvp.privacy` (`erasure`, `register_doc`, `routers`), Tabellen `privacy_deletion_profile`, `privacy_erasure_request`, `privacy_register_entry`, Spalten `document_category.paperless_tag`, `document_mirror.meta_dirty`; alle Mandanten |
| Source status | Keine Rechtsquelle im Quellenregister (Anhang C) für Fristen der Anonymisierung oder Inhalte des Verzeichnisses. Löschfristen sind Betreibereingaben je Mandant und wirken erst nach Freigabe durch eine zweite Person. Der Inhalt des Verarbeitungsverzeichnisses und des Registers ist durch einen Rechtsanwalt zu prüfen (V13); der Entwurf trägt diesen Hinweis. Die Antwortfrist zum Antrag ist zu verifizieren und wird nicht berechnet |
| Sperrprüfung | Jede Bedingung sperrt: Löschprofil Kontakt fehlt oder nicht freigegeben, kein Aufbewahrungsprofil am Kontakt, `delete_after` nicht erreicht, Verknüpfung in einer Tabelle außerhalb der Kontaktunterobjekte, verknüpfte Dokumente mit Sperre oder laufender Frist. Prüfung bei Erfassung, Freigabe und Ausführung |
| Vier Augen | Die antragstellende Person gibt nicht frei oder lehnt nicht ab; die Freigabe eines Löschprofils erfolgt nicht durch die Person, die es zuletzt geändert hat |
| Wirkung | Ausführung anonymisiert den Kontakt (Namen, Anschriften, Telefon, E-Mail, Kennungen, Daten, Bankkonten, Notizen), behält Zeile, Einwilligungsnachweise und Ereignisprotokoll, berührt keine Buchungen. Kein automatischer Löschlauf (Betreiberentscheidung 26.09.2026) |
| Acceptance case | keine in Anhang D; Test `apps/api/tests/integration/test_p17_privacy.py` |
| Implementation | Migration `0266_privacy_documents`; `/api/v1/privacy/*`; Berechtigungen `privacy:read`, `privacy:manage`, `privacy:approve`; `DocumentStore.update_meta` (Paperless inkl. Custom Fields `entity_type`, `entity_id`; Drive über appProperties) |
| Change reason | Lückenliste 30.09.2026, Befunde M6-06, M6-07, M6-09, S711-08, S16-05, S16-04, S711-10 (Paket P17) |

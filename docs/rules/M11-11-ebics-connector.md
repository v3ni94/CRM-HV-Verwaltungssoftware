# M11-11 EBICS-Konnektor (Grundgerüst): Schlüssel verschlüsselt, Bankschlüssel mit Vier Augen, nur Abruf C53

| Field | Content |
| --- | --- |
| ID | `M11-11` |
| Title | EBICS-Teilnehmer mit Mandantenschalter, Schlüsselablage verschlüsselt mit Rotationsprotokoll, Initialisierung INI/HIA, Freischaltung, Bankschlüssel HPB mit Prüfung durch eine zweite Person, Abruf von Kontoauszügen nur mit Auftragsart C53; keine Zahlungseinreichung |
| Scope | Domäne `banking`, Tabellen `ebics_tenant_setting`, `ebics_subscriber`, `ebics_key`, `ebics_order`; alle Mandanten; Konnektor `ebics` |
| Source status | Fachliche Umsetzung und Produktschutz. Belegte Quellen (frei abrufbar auf ebics.de, geprüft 01.10.2026): DK Krypto LifeCycle EBICS V1.4 vom 09.07.2025 (RSA mindestens 2.048 Bit, läuft 11/2027 aus, ab 11/2027 mindestens 4.096 Bit; TLS ab 1.2; EBICS 2.4 ausgelaufen), DFÜ-Abkommen Anlage 3 V26.11 vom 09.04.2026 Kapitel 9.2.1 und 9.2.2, Seiten 808 bis 810 (C53 = BTF `EOP/DE//camt.053/ZIP`, ZIP mit allen camt.053 des Kunden, Dateinamen `JJJJ-MM-TT_C53_<Konto>_<WWW>_<ID>.xml`), Seiten 697 und 698 (eine camt-Nachricht je Konto, Teilung über Seitennummer), DK EBICS Sicherheitsempfehlungen für Kunden, Stand 04.05.2026, Kapitel 3.1 und 3.2 (Signaturschlüssel beim Teilnehmer, Chipkarte empfohlen; Authentifikations- und Verschlüsselungsschlüssel bei Portal-Lösungen beim Betreiber; Sperre mit SPR; gemeinschaftliche Zeichnung empfohlen). Nicht belegt, weil die EBICS-Spezifikation 3.0.2 nur nach Zustimmung zu den Nutzungsbedingungen abrufbar ist: Nachrichtenaufbau, Hash-Wert der INI-/HIA-Briefe und der Bankschlüssel, Zeitraumparameter, Quittung, Schlüsselwechselaufträge, SPR-Ablauf (offene Fragen AE23-01 bis AE23-04) |
| Acceptance case | Keiner in Anhang D; Tests `apps/api/tests/unit/test_ae23_ebics.py`, `apps/api/tests/integration/test_ae23_ebics.py`, `apps/web-crm/src/components/banking/EbicsSubscribers.test.tsx`; Abnahme mit Bank-Testsystem offen (V2, M15-03) |
| Implementation | `mhvp.banking.ebics_models`, `mhvp.banking.ebics_keys`, `mhvp.banking.ebics_transport`, `mhvp.banking.ebics_connector`, `mhvp.banking.ebics_routers`, Migration 0379, Fehlercodes MHVP-BANK-0050 bis 0056, `docs/integrations/ebics.md`, `docs/runbooks/ebics-setup.md` |
| Change reason | Prioritätenliste des Betreibers vom 01.10.2026, Punkt 23 (M11-01), Welle 16 Paket AE23; S16-03-02 (Schlüsselablage) bleibt offen |

## Regeln

- Schalter je Mandant `ebics_tenant_setting.enabled`, Standard aus. Ohne Schalter läuft
  keine EBICS-Aktion (`MHVP-BANK-0051`); Lesen und die lokale Sperre bleiben möglich.
- Variante des Signaturschlüssels je Mandant, Standard `external`: Die Plattform speichert
  nur den öffentlichen Signaturschlüssel oder einen Vermerk, dass INI außerhalb der
  Plattform erledigt wurde. Variante `server` (Plattform erzeugt und speichert den
  Signaturschlüssel verschlüsselt) ist vorbereitet, weicht aber von der Empfehlung der DK
  ab und bleibt Betreiberentscheidung S16-03-02. Die Variante wird beim Anlegen des
  Teilnehmers festgeschrieben.
- Private Schlüssel liegen nur als `EncryptedText` (AES-256-GCM, Mandantenschlüssel aus
  `MHVP_MASTER_KEY`), werden nie ausgegeben oder protokolliert und von der
  Masterschlüsselrotation (`mhvp.core.key_rotation`) automatisch erfasst.
- Schlüsselwechsel schreibt nie über: die alte Zeile erhält `retired_at`, `retired_by` und
  Grund, ihr privater Schlüssel wird gelöscht, die neue Zeile wird eingefügt. Ein Wechsel
  setzt die Initialisierung zurück (INI, HIA, Freischaltung, HPB und Prüfung erneut). Eine
  Sperre ist endgültig und löscht die verbleibenden privaten Schlüssel.
- Schlüssellänge nach Krypto LifeCycle: 2.048, 3.072 oder 4.096 Bit, Standard 4.096; ab
  01.11.2027 werden kürzere Schlüssel abgelehnt, Schlüssel unter 4.096 Bit zeigen den
  Auslauftermin.
- Reihenfolge: Schlüssel, INI und HIA, Freischaltung mit Datum (nicht in der Zukunft), HPB,
  Prüfung der Hash-Werte gegen den Bankbrief. Die prüfende Person ist nicht die Person, die
  HPB ausgeführt hat (`MHVP-BANK-0054`); eine Abweichung wird protokolliert und sperrt
  (`MHVP-BANK-0053`). Ohne Hash-Wert der Übertragung keine Prüfung (`MHVP-BANK-0055`).
- Abruf nur im Zustand `ready` und nur mit C53. Jede XML-Datei des ZIP wird als camt.053
  gelesen; das Konto kommt aus der Datei (IBAN), nicht aus dem Dateinamen. Dateien für
  unbekannte Konten und Nicht-XML-Dateien werden übersprungen und gemeldet. Der Import
  nutzt `services.import_file` (Bankreferenz je Konto, D05, B08), die Rohdatei wird nach
  M11-07 abgelegt. Ein Fehler hinterlässt keinen Teilimport, nur den fehlgeschlagenen
  Auftrag im Protokoll.
- Jede Bankaktion läuft über `EbicsTransport`; ohne installierte, gegen die Spezifikation
  geprüfte Implementierung antwortet die Plattform mit `MHVP-BANK-0050`. Der Testdoppel
  (`apps/api/tests/ebics_fake.py`) ist kein Produktionsweg.
- Keine Zahlung: der Einreichungsweg `ebics` bleibt gesperrt (`EbicsSubmitter`,
  `MHVP-BANK-0017`), Freigabetor G2 geschlossen.

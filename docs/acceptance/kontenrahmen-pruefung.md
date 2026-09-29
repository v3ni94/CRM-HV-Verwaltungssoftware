# Kontenrahmen-Prüfung (Anhang A.1, Stand der Umsetzung)

**Zweck:** Prüfunterlage des Betreibers für die Freigabe des Kontenrahmens mit der Steuerberatung (Entscheidung V8, Öffnungsliste M12-09 Nr. 1, Voraussetzung der Freigabestufe G1). Das Dokument bildet den Kontenrahmen so ab, wie ihn die Software heute als Entwurf anlegt. Es enthält keine steuerliche oder rechtliche Einordnung; jede Zeile ist ein Vorschlag der Produktkonvention aus Kapitel 7.2 des Master-Prompts, keine Rechtsnorm.

**Quelle im Code:** `apps/api/src/mhvp/accounting/defaults.py` (`A1_ACCOUNTS`, `PROPOSED_ACCOUNTS`, `TEMPLATE_ACCOUNTS`), Anlage der Vorlage in `apps/api/src/mhvp/accounting/services.py::default_template`, Übernahme in den Buchungskreis in `services.create_ledger`, Freigabeworkflow in `apps/api/src/mhvp/accounting/chart_release.py`. Stand: Arbeitsstand 1.45.0, 29.09.2026.

**Ergebnis:** 44 Konten in der Vorlage `a1` Version 1, davon 38 aus Anhang A.1 (Nummern nicht erfunden, Kategorie und Typ nach den Bereichen in 7.2, Annahme A-023) und 6 Erlöskonten der Mietverwaltung als Vorschlag (M10-01, Betreiberauftrag 26.09.2026). Die Kostenkonten tragen die Vorbelegung nach der Betriebskostenverordnung als Entwurf (M10-02). Kein Konto trägt eine Umsatzsteueroption, eine Vorsteuerregel, das Kennzeichen § 35a oder Buchungstexte; diese Attribute werden je Buchungskreis am Konto gesetzt, nicht in der Vorlage (siehe Abschnitt 3).

## 1. Lesehilfe

| Spalte | Bedeutung | Werte |
| --- | --- | --- |
| Typ | Bilanz- oder Erfolgsseite (`type`) | Aktiv, Passiv, Ertrag, Aufwand |
| Kategorie | Fachliche Kontoklasse (`category`) | Bank, Kasse, Rücklage, Darlehen, technisch, Erlös, Kosten, Debitor, Kreditor, Durchlauf, Steuer, Anfangsbestand |
| Umlagekategorie | Vorbelegung der Umlagefähigkeit (`allocation_category`, M10-02) | keine Einordnung, umlagefähig Heizung, umlagefähig Wasser, umlagefähig sonstige, nicht umlagefähig Heizung, nicht umlagefähig Wasser, nicht umlagefähig sonstige |
| Abrechnungsart | Zuordnung in Abrechnungen (`statement_kind`) | keine, Hausgeld, Rücklage, Betriebskosten |
| USt-Option | `vat_option` am Konto | keine, voll, ermäßigt; in der Vorlage überall keine |
| Vorsteuerregel | `deductible_vat_rule` am Konto des Buchungskreises | keine, fester Prozentsatz (`deductible_vat_percent`), Gewerbeanteil; in der Vorlage nicht enthalten, Standard keine |
| § 35a | `section_35a_eligible` am Konto des Buchungskreises | ja, nein; Standard nein |
| Buchungstexte | `booking_texts`, bis zu drei Texte je Konto für Vorschläge der Bankbuchung | Standard leer |
| Gilt für | Rechtsträgerarten, für die das Konto beim Anlegen eines Buchungskreises übernommen wird (`applies_to`) | WEG, Miete, SEV, Verwalter |
| Prüfstatus | `review_status` und `review_note` der Vorlagenzeile | ohne Vermerk; Entwurf, Freigabe Steuerberatung offen |
| Vorgesehene Verwendung | Verwendung nach Kapitel 7 und den Regeln M10-01, M10-02, M13; Hinweis auf den Anhang-D-Fall | Freitext |
| Freigabe | Ankreuzfeld für die Freigabe je Konto durch Betreiber und Steuerberatung | [ ] offen, [x] freigegeben |

Debitorenkonten (090000 bis 099999, je Vertrag) und Kreditorenkonten entstehen je Buchungskreis aus Verträgen und Kontakten (`services.sync_debtor_accounts`) und sind nicht Teil der Vorlage.

## 2. Konten der Vorlage `a1` Version 1

| Konto | Bezeichnung | Typ | Kategorie | Umlagekategorie | Abrechnungsart | USt-Option | Vorsteuerregel | § 35a | Buchungstexte | Gilt für | Prüfstatus | Vorgesehene Verwendung | Freigabe |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 001200 | WEG-Konto | Aktiv | Bank | keine Einordnung | keine | keine | keine | nein | keine | WEG | ohne Vermerk | Girokonto der Gemeinschaft; Bankbuchungen aus dem Import, Liquiditätsbericht | [ ] |
| 001201 | Rücklagenkonto | Aktiv | Bank | keine Einordnung | keine | keine | keine | nein | keine | WEG | ohne Vermerk | Bankkonto der Erhaltungsrücklage (Anlage); getrennt vom Girokonto, Bestand nach D03 und D19 | [ ] |
| 001300 | Kasse | Aktiv | Kasse | keine Einordnung | keine | keine | keine | nein | keine | WEG, Miete, SEV, Verwalter | ohne Vermerk | Barkasse je Rechtsträger | [ ] |
| 001400 | Überzahlungen aus Vorjahren | Passiv | technisch | keine Einordnung | keine | keine | keine | nein | keine | WEG, Miete, SEV, Verwalter | ohne Vermerk | Guthaben aus Überzahlungen der Vorjahre (Verbindlichkeit gegenüber dem Zahler, D07) | [ ] |
| 008000 | Erhaltungsrücklage | Passiv | Rücklage | keine Einordnung | Rücklage | keine | keine | nein | keine | WEG | ohne Vermerk | Passivkonto Erhaltungsrücklage (Soll-Bestand); Zuführung und Entnahme nur über 030000 und 029100 | [ ] |
| 008500 | Darlehen | Passiv | Darlehen | keine Einordnung | keine | keine | keine | nein | keine | WEG, Miete, SEV, Verwalter | ohne Vermerk | Darlehensverbindlichkeiten des Rechtsträgers | [ ] |
| 008600 | Hypotheken | Passiv | Darlehen | keine Einordnung | keine | keine | keine | nein | keine | WEG, Miete, SEV, Verwalter | ohne Vermerk | Grundpfandrechtlich gesicherte Darlehen | [ ] |
| 009000 | Anfangsbestandskonto | Passiv | Anfangsbestand | keine Einordnung | keine | keine | keine | nein | keine | WEG, Miete, SEV, Verwalter | ohne Vermerk | Gegenkonto der Anfangsbestände bei der Datenübernahme (D11); keine laufende Buchung | [ ] |
| 009999 | Durchlaufposten WEG | Aktiv | Durchlauf | keine Einordnung | keine | keine | keine | nein | keine | WEG | ohne Vermerk | Durchlaufposten der Gemeinschaft (Geldtransit bei Umbuchungen, D04) | [ ] |
| 026000 | Vorsteuerrückerstattungen | Ertrag | Steuer | keine Einordnung | keine | keine | keine | nein | keine | WEG, Miete, SEV, Verwalter | ohne Vermerk | Erstattete Vorsteuer, nur bei Rechtsträgern mit Umsatzsteueroption (Freigabe V21 offen) | [ ] |
| 027000 | Durchlaufposten Skonti | Aktiv | Durchlauf | keine Einordnung | keine | keine | keine | nein | keine | WEG, Miete, SEV, Verwalter | ohne Vermerk | Durchlaufposten für Skonti aus Zahlungen an Kreditoren | [ ] |
| 028100 | Zinseinnahmen WEG-Konto | Ertrag | Erlös | keine Einordnung | keine | keine | keine | nein | keine | WEG | ohne Vermerk | Zinsen des Girokontos der Gemeinschaft | [ ] |
| 028101 | Zinseinnahmen Erhaltungsrücklage | Ertrag | Erlös | keine Einordnung | Rücklage | keine | keine | nein | keine | WEG | ohne Vermerk | Zinsen der Rücklagenanlage, der Rücklage zugeordnet (D03) | [ ] |
| 029100 | Entnahme Erhaltungsrücklage | Ertrag | technisch | keine Einordnung | Rücklage | keine | keine | nein | keine | WEG | ohne Vermerk | Entnahme aus der Erhaltungsrücklage für finanzierte Maßnahmen (D03) | [ ] |
| 030000 | Zuführung Erhaltungsrücklage | Aufwand | technisch | keine Einordnung | Rücklage | keine | keine | nein | keine | WEG | ohne Vermerk | Zuführung zur Erhaltungsrücklage laut Wirtschaftsplan (D19) | [ ] |
| 040100 | Hausmeisterkosten | Aufwand | Kosten | umlagefähig sonstige | Betriebskosten | keine | keine | nein | keine | WEG, Miete, SEV, Verwalter | Entwurf, Freigabe Steuerberatung offen | Kostenkonto; BetrKV-Bezug § 2 Nr. 14 Hauswart; Schlüssel WFL | [ ] |
| 040200 | Hausmeistergehalt | Aufwand | Kosten | umlagefähig sonstige | Betriebskosten | keine | keine | nein | keine | WEG, Miete, SEV, Verwalter | Entwurf, Freigabe Steuerberatung offen | Kostenkonto; BetrKV-Bezug § 2 Nr. 14 Hauswart; Schlüssel WFL | [ ] |
| 040300 | Reinigungskosten | Aufwand | Kosten | umlagefähig sonstige | Betriebskosten | keine | keine | nein | keine | WEG, Miete, SEV, Verwalter | Entwurf, Freigabe Steuerberatung offen | Kostenkonto; BetrKV-Bezug § 2 Nr. 9 Gebäudereinigung; Schlüssel WFL | [ ] |
| 040400 | Gartenarbeiten und Pflege Außenanlagen | Aufwand | Kosten | umlagefähig sonstige | Betriebskosten | keine | keine | nein | keine | WEG, Miete, SEV, Verwalter | Entwurf, Freigabe Steuerberatung offen | Kostenkonto; BetrKV-Bezug § 2 Nr. 10 Gartenpflege; Schlüssel WFL | [ ] |
| 040500 | Winterdienst | Aufwand | Kosten | umlagefähig sonstige | Betriebskosten | keine | keine | nein | keine | WEG, Miete, SEV, Verwalter | Entwurf, Freigabe Steuerberatung offen | Kostenkonto; BetrKV-Bezug § 2 Nr. 8 Straßenreinigung; Schlüssel WFL | [ ] |
| 041000 | Brennstoffkosten | Aufwand | Kosten | umlagefähig Heizung | Betriebskosten | keine | keine | nein | keine | WEG, Miete, SEV, Verwalter | Entwurf, Freigabe Steuerberatung offen | Kostenkonto; BetrKV-Bezug § 2 Nr. 4 Heizung; Schlüssel V_HEIZ | [ ] |
| 041100 | Schornsteinfeger | Aufwand | Kosten | umlagefähig Heizung | Betriebskosten | keine | keine | nein | keine | WEG, Miete, SEV, Verwalter | Entwurf, Freigabe Steuerberatung offen | Kostenkonto; BetrKV-Bezug § 2 Nr. 4 Heizung bei Zentralheizung, sonst Nr. 12 (zu prüfen); Schlüssel V_HEIZ | [ ] |
| 041200 | Emissionsmessung | Aufwand | Kosten | umlagefähig Heizung | Betriebskosten | keine | keine | nein | keine | WEG, Miete, SEV, Verwalter | Entwurf, Freigabe Steuerberatung offen | Kostenkonto; BetrKV-Bezug § 2 Nr. 4 Heizung; Schlüssel V_HEIZ | [ ] |
| 041300 | Wartung Heizung | Aufwand | Kosten | umlagefähig Heizung | Betriebskosten | keine | keine | nein | keine | WEG, Miete, SEV, Verwalter | Entwurf, Freigabe Steuerberatung offen | Kostenkonto; BetrKV-Bezug § 2 Nr. 4 Heizung; Schlüssel V_HEIZ | [ ] |
| 041400 | Heizungsreparaturen | Aufwand | Kosten | nicht umlagefähig Heizung | keine | keine | keine | nein | keine | WEG, Miete, SEV, Verwalter | Entwurf, Freigabe Steuerberatung offen | Kostenkonto; BetrKV-Bezug Instandsetzung, keine Betriebskosten | [ ] |
| 041500 | Miete Heizungszähler | Aufwand | Kosten | umlagefähig Heizung | Betriebskosten | keine | keine | nein | keine | WEG, Miete, SEV, Verwalter | Entwurf, Freigabe Steuerberatung offen | Kostenkonto; BetrKV-Bezug § 2 Nr. 4 Heizung; Schlüssel V_HEIZ | [ ] |
| 041600 | Miete Kaltwasserzähler | Aufwand | Kosten | umlagefähig Wasser | Betriebskosten | keine | keine | nein | keine | WEG, Miete, SEV, Verwalter | Entwurf, Freigabe Steuerberatung offen | Kostenkonto; BetrKV-Bezug § 2 Nr. 2 Wasser; Schlüssel V_KW | [ ] |
| 041700 | Miete Warmwasserzähler | Aufwand | Kosten | umlagefähig Heizung | Betriebskosten | keine | keine | nein | keine | WEG, Miete, SEV, Verwalter | Entwurf, Freigabe Steuerberatung offen | Kostenkonto; BetrKV-Bezug § 2 Nr. 5 Warmwasser; Schlüssel V_WW | [ ] |
| 041800 | Servicekosten Heizkostenabrechnung | Aufwand | Kosten | umlagefähig Heizung | Betriebskosten | keine | keine | nein | keine | WEG, Miete, SEV, Verwalter | Entwurf, Freigabe Steuerberatung offen | Kostenkonto; BetrKV-Bezug § 2 Nr. 4 Heizung; Schlüssel V_HEIZ | [ ] |
| 041801 | Servicekosten Wasserabrechnung | Aufwand | Kosten | umlagefähig Wasser | Betriebskosten | keine | keine | nein | keine | WEG, Miete, SEV, Verwalter | Entwurf, Freigabe Steuerberatung offen | Kostenkonto; BetrKV-Bezug § 2 Nr. 2 Wasser; Schlüssel V_KW | [ ] |
| 041805 | Rauchwarnmelder | Aufwand | Kosten | keine Einordnung | keine | keine | keine | nein | keine | WEG, Miete, SEV, Verwalter | ohne Vermerk | Kostenkonto; BetrKV-Bezug Einordnung zu prüfen (Miete/Wartung) | [ ] |
| 042000 | Wasser allgemein | Aufwand | Kosten | umlagefähig Wasser | Betriebskosten | keine | keine | nein | keine | WEG, Miete, SEV, Verwalter | Entwurf, Freigabe Steuerberatung offen | Kostenkonto; BetrKV-Bezug § 2 Nr. 2 Wasser; Schlüssel V_KW | [ ] |
| 042100 | Trinkwasser | Aufwand | Kosten | umlagefähig Wasser | Betriebskosten | keine | keine | nein | keine | WEG, Miete, SEV, Verwalter | Entwurf, Freigabe Steuerberatung offen | Kostenkonto; BetrKV-Bezug § 2 Nr. 2 Wasser; Schlüssel V_KW | [ ] |
| 042200 | Abwasser | Aufwand | Kosten | umlagefähig Wasser | Betriebskosten | keine | keine | nein | keine | WEG, Miete, SEV, Verwalter | Entwurf, Freigabe Steuerberatung offen | Kostenkonto; BetrKV-Bezug § 2 Nr. 3 Entwässerung; Schlüssel V_KW | [ ] |
| 042300 | Niederschlagswasser | Aufwand | Kosten | umlagefähig Wasser | Betriebskosten | keine | keine | nein | keine | WEG, Miete, SEV, Verwalter | Entwurf, Freigabe Steuerberatung offen | Kostenkonto; BetrKV-Bezug § 2 Nr. 3 Entwässerung; Schlüssel WFL | [ ] |
| 043000 | Allgemeinstrom | Aufwand | Kosten | umlagefähig sonstige | Betriebskosten | keine | keine | nein | keine | WEG, Miete, SEV, Verwalter | Entwurf, Freigabe Steuerberatung offen | Kostenkonto; BetrKV-Bezug § 2 Nr. 11 Beleuchtung; Schlüssel WFL | [ ] |
| 060100 | Hausgeld | Ertrag | Erlös | keine Einordnung | Hausgeld | keine | keine | nein | keine | WEG | ohne Vermerk | Sollstellung Hausgeld laut Wirtschaftsplan (M13) | [ ] |
| 060200 | Erhaltungsrücklage (Sollstellung) | Ertrag | Erlös | keine Einordnung | Rücklage | keine | keine | nein | keine | WEG | ohne Vermerk | Sollstellung Rücklagenbeitrag laut Wirtschaftsplan (M13) | [ ] |
| 060300 | Miete | Ertrag | Erlös | keine Einordnung | keine | keine | keine | nein | keine | Miete, SEV | Entwurf, Freigabe Steuerberatung offen | Sollstellung Nettokaltmiete (M13); Vorschlag M10-01 | [ ] |
| 060400 | Betriebskostenvorauszahlung | Ertrag | Erlös | keine Einordnung | keine | keine | keine | nein | keine | Miete, SEV | Entwurf, Freigabe Steuerberatung offen | Sollstellung Betriebskostenvorauszahlung (M13, M17); Vorschlag M10-01 | [ ] |
| 060500 | Heizkostenvorauszahlung | Ertrag | Erlös | keine Einordnung | keine | keine | keine | nein | keine | Miete, SEV | Entwurf, Freigabe Steuerberatung offen | Sollstellung Heizkostenvorauszahlung (M13, M17); Vorschlag M10-01 | [ ] |
| 060600 | Garagenmiete | Ertrag | Erlös | keine Einordnung | keine | keine | keine | nein | keine | Miete, SEV | Entwurf, Freigabe Steuerberatung offen | Sollstellung Garagenmiete; Vorschlag M10-01 | [ ] |
| 060700 | Stellplatzmiete | Ertrag | Erlös | keine Einordnung | keine | keine | keine | nein | keine | Miete, SEV | Entwurf, Freigabe Steuerberatung offen | Sollstellung Stellplatzmiete; Vorschlag M10-01 | [ ] |
| 060800 | Sonstige Erlöse | Ertrag | Erlös | keine Einordnung | keine | keine | keine | nein | keine | Miete, SEV | Entwurf, Freigabe Steuerberatung offen | Sonstige Erlöse der Mietverwaltung; Vorschlag M10-01 | [ ] |

Schlüsselkürzel der Spalte Vorgesehene Verwendung (Anhang A.2, Vorschlag M10-02): `WFL` Wohnfläche, `V_HEIZ` Verbrauch Heizung, `V_WW` Verbrauch Warmwasser, `V_KW` Verbrauch Kaltwasser. Der Schlüssel je Objekt bleibt eine Objektentscheidung; die Vorbelegung wird nicht auf Buchungskreise angewendet, sondern nur zur Prüfung mitgeführt (`allocation_key_code`, `betrkv_reference`).

BetrKV-Kostenarten ohne Konto in Anhang A.1 (keine Nummern erfunden, M10-02): Nr. 1 Grundsteuer, Nr. 6 verbundene Heizungs- und Warmwasseranlagen, Nr. 7 Aufzug, Nr. 13 Sach- und Haftpflichtversicherung, Nr. 15 Gemeinschaftsantenne und Breitband (Wortlaut zu prüfen), Nr. 16 Wäschepflege, Nr. 17 sonstige Betriebskosten. Sie brauchen eine Festlegung durch den Betreiber mit der Steuerberatung (Abschnitt 4).

## 3. Attribute, die je Buchungskreis am Konto gesetzt werden

Die Vorlage überträgt beim Anlegen eines Buchungskreises (`POST /api/v1/accounting/ledgers`) Nummer, Bezeichnung, Kategorie, Typ, Abrechnungsart, Umlagekategorie, USt-Option, Liquiditätsrelevanz, Prüfstatus und Vermerk. Die folgenden Attribute sind nur am Konto des Buchungskreises vorhanden:

| Attribut | Setzen über | Wirkung in der Software |
| --- | --- | --- |
| `vat_option` (USt-Option) | `POST /api/v1/accounting/ledgers/{ledger_id}/accounts` beim Anlegen eines Kontos; Vorlagenwert bei Übernahme | Konten mit Option sperren die Automatik (Verifier M12-05, Sperrkriterium) und die automatische Vorsteuerbuchung (M14-02, D45); Buchungskreise mit `vat_mode = option` buchen Rechnungen mit Steuer nicht automatisch |
| `deductible_vat_rule`, `deductible_vat_percent` (Vorsteuerregel) | Datenmodell `ledger_account`; kein Endpunkt setzt die Regel derzeit, Standard keine | Sperrkriterium des Verifiers; Vorsteueraufteilung ist fachlich nicht freigegeben (M14-02, V21) |
| `section_35a_eligible` (§ 35a) | `POST .../accounts` beim Anlegen | Kennzeichen für die Ausweisung haushaltsnaher Dienstleistungen; Beträge aus KI-Schätzung werden nie als Nachweis gezeigt (D44); Sperrkriterium des Verifiers |
| `booking_texts` (Buchungstexte) | `POST .../accounts` und `PATCH .../accounts/{account_id}` | Bis zu drei Texte je Konto; Treffer im Verwendungszweck erzeugen einen Vorschlag der Art `account_text` (M12-04, Stufe 1), nie eine Buchung |
| `operating_cost_type` (Betriebskostenart) | Abrechnung, Umlagefähigkeit je Konto und Objekt (M17-01) | Pflicht vor der Abrechnungsfreigabe (Sperre A02) |

Eine nachträgliche Änderung von Umlagekategorie, Abrechnungsart oder USt-Option an bestehenden Konten je Buchungskreis ist über die Schnittstelle noch nicht möglich (offener Punkt M10-02); bis dahin wird das Konto neu angelegt oder die Einordnung in der Vorlage vor der Übernahme gesetzt.

## 4. Offene Fragen an den Betreiber und die Steuerberatung

Jede Frage ist vor der Freigabe zu beantworten oder ausdrücklich zurückzustellen. Ohne Antwort bleibt der betroffene Funktionsteil gesperrt (Regel 0.1.3).

| Nr. | Frage | Bezug | Antwort (Datum, Name) |
| --- | --- | --- | --- |
| F1 | Wird die Umsatzsteueroption für einzelne Rechtsträger (Gewerbeeinheiten) ausgeübt? Wenn ja: welche Erlös- und Kostenkonten tragen die Option `full` oder `reduced`, welches Steuerkonto und welche Vorsteuerregel (fester Prozentsatz oder Gewerbeanteil) gelten je Buchungskreis? | V21, M13-03, M14-02 bis M14-04, D45; `vat_option`, `deductible_vat_rule` | |
| F2 | Welche Kostenkonten sind für die Ausweisung nach § 35a EStG vorgesehen (`section_35a_eligible`), und wer prüft den ausgewiesenen Anteil je Rechnung? | V21, D44, M14 | |
| F3 | Rücklagenkonten: Bleibt die Trennung in 001201 Rücklagenkonto (Bankanlage), 008000 Erhaltungsrücklage (Passivkonto), 030000 Zuführung, 029100 Entnahme, 028101 Zinsen und 060200 Sollstellung Rücklagenbeitrag so bestehen? Wie werden mehrere Rücklagen (Erhaltung, Sonderrücklagen, Sonderumlage) je Gemeinschaft abgebildet, ohne Nummern zu erfinden? | D03, D19, D20, Anhang A.1, Kapitel 7.2 | |
| F4 | Erlöskonten der Mietverwaltung 060300 bis 060800 (Vorschlag M10-01): Nummern und Bezeichnungen bestätigen oder ändern; Konto für Kautionen als Verbindlichkeit festlegen (kein Bereich in 7.2) | M10-01, D56 | |
| F5 | Umlagevorbelegung der Kostenkonten (M10-02): Zuordnung zu den BetrKV-Kostenarten, Schlüsselvorschlag und die Einordnung von 041100 Schornsteinfeger, 041805 Rauchwarnmelder und 042300 Niederschlagswasser bestätigen | M10-02, M17-01, D21, D22 | |
| F6 | Konten für die BetrKV-Kostenarten ohne Konto in A.1 (Grundsteuer, Aufzug, Versicherung, Antenne und Breitband, Wäschepflege, sonstige) festlegen | M10-02 | |
| F7 | DATEV-Zuordnung je Konto (Kontenrahmen SKR03 oder SKR04, Kontolänge) für den Export an die Steuerberatung | M18-01, M18-04 | |
| F8 | Sollen Buchungstexte je Konto (bis zu drei) vorbelegt werden, und welche? Sie erzeugen nur Vorschläge (M12-04) | M12-04 | |

## 5. Freigabe in der Software

Die Freigabe wird als Betreiberentscheidung protokolliert; die Software entscheidet sie nicht (V8).

Oberfläche: Einstellungen, Buchhaltung, Kontenrahmen (`/einstellungen/buchhaltung/kontenrahmen`). Die Seite zeigt je Version den Status Entwurf, zur Prüfung oder freigegeben mit Kontenzahl, den Versionsverlauf und den Export als CSV oder PDF für die Steuerberatung. Ablauf:

1. Entwurf nach Anhang A.1 anlegen (Schaltfläche, Recht Buchhaltung ändern), falls noch keine Vorlage besteht; ein zweiter Aufruf ergänzt nur fehlende Zeilen und überschreibt keine Änderungen.
2. Konten des Entwurfs prüfen und bei Bedarf ersetzen (`PUT /api/v1/accounting/templates/{id}/accounts`, Recht Buchhaltung ändern; Kontonummern müssen gefüllt und eindeutig sein).
3. Zur Prüfung geben (Schaltfläche, `POST /api/v1/accounting/templates/{id}/submit-review`): die Version ist eingefroren; zurück in den Entwurf ist möglich (`POST .../back-to-draft`).
4. CSV oder PDF exportieren (`GET /api/v1/accounting/templates/{id}/export?format=csv|pdf`) und mit diesem Dokument an die Steuerberatung geben.
5. Freigeben (Schaltfläche Freigeben, Recht Buchhaltung freigeben, `POST /api/v1/accounting/templates/{id}/release`): im Dialog werden der Kommentar zur Freigabe und optional die Dokument-ID des Prüfschreibens der Steuerberatung erfasst; Datum und Freigeber werden gespeichert, das Ereignis `chart_template.released` wird protokolliert. Eine freigegebene Version wird nie mehr geändert; ein zweiter Aufruf ändert nichts.
6. Änderungen nach der Freigabe: Neue Version anlegen (`POST .../versions`), die als Entwurf beginnt und eine eigene Freigabe braucht (`supersedes_id` verweist auf die Vorgängerin).

Wirkung: Die Genehmigung eines G1-Antrags prüft `chart_release.ensure_released_template` und lehnt ohne freigegebene Version mit `MHVP-GATE-0004` ab. Die Seite Einstellungen, Buchhaltung, G1 Öffnung zeigt den Stand des Kontenrahmens als ersten Prüfpunkt.

## 6. Bestätigung

| Feld | Eintrag |
| --- | --- |
| Geprüfte Vorlage (Code, Version) | |
| Softwarestand (Commit, Version) | |
| Prüfung durch Steuerberatung (Name, Datum, Schreiben) | |
| Freigabe durch Betreiber (Name, Datum) | |
| Vorbehalte oder zurückgestellte Fragen (Nr. aus Abschnitt 4) | |
| Unterschrift Betreiber | |

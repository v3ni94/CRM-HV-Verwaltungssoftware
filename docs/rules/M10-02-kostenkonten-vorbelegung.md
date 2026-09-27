# M10-02 Kostenkonten der Vorlage: Vorbelegung von Umlagefähigkeit und Schlüssel als Entwurf nach BetrKV

| Field | Content |
| --- | --- |
| ID | `M10-02` |
| Title | Kostenkonten der Kontenrahmen-Vorlage werden als Entwurf nach der Betriebskostenverordnung vorbelegt (umlagefähig mit üblichem Schlüssel, sonst nicht umlagefähig, Umsatzsteueroption bleibt offen), je Zeile mit `review_status = "entwurf"` und Vermerk "Freigabe durch Steuerberatung offen" |
| Scope | `mhvp.accounting.defaults` (`BETRKV_TYPES`, `COSTS`, `BETRKV_TYPES_WITHOUT_ACCOUNT`, `fill_unset`), `mhvp.accounting.services.default_template` und `create_ledger`, `POST /api/v1/accounting/templates/default`, `GET /api/v1/accounting/templates`, `GET /api/v1/accounting/ledgers/{id}/accounts`. Alle Mandanten; Kostenkonten gelten für alle Rechtsträgerarten |
| Source status | Offene Entscheidung mit der Steuerberatung. Rechtsgrundlage nur als Orientierung: Betriebskostenverordnung (BetrKV, Quellenregister R07) für den Katalog der Betriebskostenarten und § 556a BGB für den Verteilungsmaßstab. Die Zuordnung der A.1-Konten zu den Katalognummern ist eine Vorbelegung auf Betreiberauftrag vom 26.09.2026, keine rechtliche Einordnung des Einzelfalls. Der Wortlaut der Katalognummer 15 (Gemeinschaftsantenne, Breitband) ist zu prüfen. Freigabe: Steuerberatung mit Betreiber (V8, M10-02) |
| Acceptance case | keine in Anhang D; A02, A03 und D22 bleiben durch die Abrechnungssperre gewahrt (M17-01). Tests `apps/api/tests/integration/test_m10_02_cost_presets.py` (Zuordnungstabelle vollständig, Vorbelegung nach Betreiberentscheidung, `fill_unset` füllt nur unbesetzte Felder und erhält Bearbeitungen, Seed idempotent, Mandantentrennung, Prüfkennzeichen in der Kontenausgabe des Buchungskreises) |
| Implementation | Vorbelegung je Kostenkonto aus Anhang A.1 (siehe Tabelle). Umsatzsteueroption bleibt `none`. Umlagefähige Konten erhalten `statement_kind = "operating_costs"`. Der vorgeschlagene Schlüssel steht als `allocation_key_code` (Code der Standardliste A.2) und der Katalogbezug als `betrkv_reference` nur auf der Vorlagenzeile; beides wird nicht auf Buchungskreise übertragen. Seed füllt auf bestehenden Vorlagenzeilen nur Felder, die noch `none` oder leer sind, und setzt dabei das Prüfkennzeichen, falls die Zeile noch keines trägt; vorhandene Werte bleiben unverändert. Bestehende Buchungskreise werden nicht verändert |
| Change reason | Betreiberentscheidung 26.09.2026 zu M10-02: die Abrechnungssperre (M17-01) verlangt eine Einordnung je Konto; ohne Vorbelegung müsste jedes Kostenkonto einzeln eingeordnet werden. Die Vorbelegung ersetzt weder die Prüfung durch die Steuerberatung noch die Einordnung je Objekt |

## Zuordnungstabelle (Entwurf, Prüfung Steuerberatung offen)

Katalog der Betriebskostenarten nach BetrKV, Bezeichnungen wie üblich aufgeführt, Nummern nur
als Prüfbezug:

| Nr. | Betriebskostenart | Konto in Anhang A.1 | Vorbelegung | Schlüssel |
| --- | --- | --- | --- | --- |
| 1 | Laufende öffentliche Lasten des Grundstücks (Grundsteuer) | kein Konto in A.1 | offen | |
| 2 | Wasserversorgung | 041600 Miete Kaltwasserzähler, 041801 Servicekosten Wasserabrechnung, 042000 Wasser allgemein, 042100 Trinkwasser | umlagefähig Wasser | Verbrauch Kaltwasser (V_KW), ohne Zähler Personen oder Fläche je Objekt |
| 3 | Entwässerung | 042200 Abwasser, 042300 Niederschlagswasser | umlagefähig Wasser | Abwasser Verbrauch Kaltwasser (V_KW), Niederschlagswasser Wohnfläche (WFL) |
| 4 | Heizung | 041000 Brennstoffkosten, 041100 Schornsteinfeger (bei Zentralheizung, sonst Nr. 12, zu prüfen), 041200 Emissionsmessung, 041300 Wartung Heizung, 041500 Miete Heizungszähler, 041800 Servicekosten Heizkostenabrechnung | umlagefähig Heizung/Warmwasser | Verbrauch Heizung (V_HEIZ) |
| 5 | Warmwasserversorgung | 041700 Miete Warmwasserzähler | umlagefähig Heizung/Warmwasser | Verbrauch Warmwasser (V_WW) |
| 6 | Verbundene Heizungs- und Warmwasserversorgungsanlagen | kein eigenes Konto in A.1 | offen | |
| 7 | Aufzug | kein Konto in A.1 | offen | |
| 8 | Straßenreinigung und Müllbeseitigung | 040500 Winterdienst | umlagefähig Sonstige | Wohnfläche (WFL) |
| 9 | Gebäudereinigung und Ungezieferbekämpfung | 040300 Reinigungskosten | umlagefähig Sonstige | Wohnfläche (WFL) |
| 10 | Gartenpflege | 040400 Gartenarbeiten und Pflege Außenanlagen | umlagefähig Sonstige | Wohnfläche (WFL) |
| 11 | Beleuchtung | 043000 Allgemeinstrom | umlagefähig Sonstige | Wohnfläche (WFL) |
| 12 | Schornsteinreinigung | siehe Nr. 4 (041100) | | |
| 13 | Sach- und Haftpflichtversicherung | kein Konto in A.1 | offen | |
| 14 | Hauswart | 040100 Hausmeisterkosten, 040200 Hausmeistergehalt (Anteile für Verwaltung und Instandsetzung sind nicht umlagefähig und müssen getrennt gebucht werden) | umlagefähig Sonstige | Wohnfläche (WFL) |
| 15 | Gemeinschaftsantenne, Breitbandnetz (Wortlaut zu prüfen) | kein Konto in A.1 | offen | |
| 16 | Einrichtungen für die Wäschepflege | kein Konto in A.1 | offen | |
| 17 | Sonstige Betriebskosten | kein Konto in A.1 | offen | |

Nicht umlagefähig vorbelegt: 041400 Heizungsreparaturen (Instandsetzung,
`non_allocable_heating`). Ohne Vorbelegung (`none`, Abrechnungssperre bleibt aktiv):
041805 Rauchwarnmelder, weil das Konto Miete und Wartung mischt und die Einordnung je Objekt
und Vertrag mit der Steuerberatung zu klären ist.

## Regeln

- Die Vorbelegung ist ein Vorschlag mit Prüfkennzeichen, keine Sperre und keine Freigabe.
  Die Abrechnungssperre (M17-01, A02, D22) prüft weiterhin je Position die Einordnung des
  Kontos im Buchungskreis; ein Konto mit `allocation_category = "none"` erreicht keine
  Abrechnung. G1 und G3 bleiben geschlossen.
- Die Umsatzsteueroption bleibt auf allen Kostenkonten `none` (Entscheidung offen, M13-03).
- `POST /accounting/templates/default` ist idempotent: auf bestehenden Zeilen werden nur
  `allocation_category`, `statement_kind` und `allocation_key_code` gefüllt, wenn sie noch
  `none` oder leer sind; `betrkv_reference` wird als Prüfinformation ergänzt, ohne allein das
  Kennzeichen zu setzen. Vom Betreiber gesetzte Werte bleiben in jedem Fall bestehen.
  Fehlende Zeilen werden ergänzt (M10-01). Bereits angelegte Buchungskreise werden nicht
  verändert.
- Neue Buchungskreise übernehmen die Vorbelegung samt Kennzeichen auf die Konten
  (`GET /accounting/ledgers/{id}/accounts` zeigt `allocation_category`, `statement_kind`,
  `vat_option`, `review_status`, `review_note`). Der Schlüsselvorschlag wird nicht als
  Verteilung (`ledger_account_allocation`) angelegt, weil der Schlüssel je Objekt mit Quelle
  und Geltungsbeginn zu erfassen ist (A03, § 556a Abs. 3 BGB bei vermietetem
  Wohnungseigentum).
- Abweichung je Objekt: der Buchungskreis ist je Rechtsträger, also je Objekt, angelegt;
  eine Abweichung ist damit je Buchungskreis möglich. Über die Schnittstelle sind auf
  bestehenden Konten derzeit nur Name, Sichtbarkeit, Aktivität und Buchungstexte änderbar
  (`AccountPatch`); `allocation_category`, `statement_kind` und `vat_option` lassen sich nur
  beim Anlegen eines Kontos setzen. Eine Änderung der Einordnung an bestehenden Konten ist
  in dieser Aufgabe nicht gebaut (OPEN_QUESTIONS M10-02).
- Für Betriebskostenarten ohne Konto in Anhang A.1 werden keine Nummern erfunden; sie
  werden mit der Steuerberatung festgelegt (OPEN_QUESTIONS M10-02).

## Nachtrag 27.09.2026: Freigabe der Vorbelegung

- Die Vorbelegung der Kostenkonten (Umlagefähigkeit, Abrechnungsart, Umsatzsteueroption)
  wird zusammen mit dem Kontenrahmen freigegeben (Freigabeworkflow, Nachtrag in M10-01).
  Bis zur Freigabe bleibt sie Entwurf; der Export als CSV/PDF für die Steuerberatung
  (`GET /accounting/templates/{id}/export`) enthält je Konto Kategorie, Typ,
  Abrechnungsart, Umlagefähigkeit, Umsatzsteueroption, Prüfstatus und Vermerk.
- Eine Änderung der Vorbelegung nach Freigabe erfolgt nur in einer neuen Version der
  Vorlage. Bestehende Buchungskreise werden dadurch nicht verändert (7.2).

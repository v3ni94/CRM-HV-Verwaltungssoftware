# AK06: Auskunftsanträge und erweiterter Auskunftsumfang

- ID: AK06-auskunftsantraege
- Geltungsbereich: Eingang und Überwachung von Auskunftsanträgen nach Art. 15 DSGVO, Eintrag ins Fristenregister, Auskunftsumfang Portalkonto, Zahlungs- und Vertragsdaten
- Abschnitte: 16, 0.1.3; Befunde GAI-506, GAI-507 (Rest AJ13)
- Quellenstatus (Anhang C): Art. 15 DSGVO als Norm genannt; Länge der Antwortfrist (AJ13-01) und Umfang der Auskunft (AC07-01) sind offen. Keine Regel legt hier eine Frist oder einen Umfang fest.
- Status: implemented, not accepted

## Regeln

1. Eingang: Ein Auskunftsantrag wird mit Kontakt, Eingangsdatum (nicht in der Zukunft) und Eingangsweg erfasst (Tabelle `privacy_access_request`, Migration 0448). Statusfolge: eingegangen, in Bearbeitung, dann beantwortet, abgelehnt oder zurückgenommen. Erledigte Anträge werden nicht wieder geöffnet und nicht gelöscht.
2. Frist: Die Fälligkeit ergibt sich nur aus `privacy_request_deadlines.access_days` (kein Standardwert, AJ13-01) und ist Orientierung, zu prüfen. Ohne Wert gibt es keine Fälligkeit und keinen Eintrag ins Fristenregister.
3. Fristenregister: Mit hinterlegter Frist erscheint ein offener Antrag als Art `privacy_access_request` in der Fristenliste (sofort und im nächtlichen Abgleich); mit Erledigung wird der Eintrag erledigt. Lese- und Pflegerecht: `privacy:read`, `privacy:manage`.
4. Auskunftsumfang: Portalkonto mit Anmeldeereignissen und Sitzungen, Zahlungsdaten (Forderungen und Zahlungsstand der Verträge) und Vertragsdaten sind je Mandantenschalter zuschaltbar, Standard aus; ausgeschaltet erscheinen sie nur als Anzahl. Token, Codes und Hashes werden nie ausgegeben. Es zählen nur Werte bis zum Zeitpunkt der Vorbereitung.
5. Das Schließen eines Antrags ist keine rechtliche Erklärung; die Auskunft geht über den geprüften Auskunftsexport.

## Abnahmefall

Anhang D: keiner benannt; Testfälle `apps/api/tests/integration/test_ak06_privacy_access_requests.py`.

## Änderungsgrund

Reste der Welle 21 (AJ13-03, GAI-506, GAI-507), Welle 22.

# M17-04 Abrechnungsfrist (Orientierung)

- ID: M17-04 (Welle 16, AE18)
- Geltungsbereich: Betriebskostenabrechnung Miete, je Mietvertrag
- Quellenstatus: Anhang C R06 (§ 556 Abs. 3 BGB), Fristende nur als Orientierung, im Einzelfall zu verifizieren; Ausnahmegründe offen (OPEN_QUESTIONS M17-04)
- Regel: Fristende = Ende des zwölften Monats nach Periodenende. Maßgeblich ist der Zugang, nicht die Erstellung. Der Zugangsvorschlag aus dem Versand wird erst durch eine Person mit Nachweis übernommen. Verhalten nach Ablauf per Mandantenschalter `policy`: `block_claims` (Standard, Nachforderung ohne wirksame Ausnahme gesperrt) oder `notice` (nur Hinweis). Die Warnung (Beat) ist Standard aus und sendet nichts extern.
- Abnahmefall: Periodenende 31.12.2025 ergibt Fristorientierung 31.12.2026; 29.02.2024 ergibt 28.02.2025; Nachforderung mit Zugang 10.01.2027 wird bei `block_claims` abgelehnt, bei `notice` nicht.
- Änderungsgrund: Punkt 18 der Prioritätenliste vom 01.10.2026. Gate G3 bleibt geschlossen.

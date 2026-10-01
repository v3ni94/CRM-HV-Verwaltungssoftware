# R03: Objektübernahme, Aufgaben, Eigentümeransicht und Onboarding-Anlage

- ID: R03 (ergänzt M7-01, M7-02)
- Geltungsbereich: Objekt-Onboarding (Masterprompt 10.2 Schritte 4 bis 6), je Mandant; Eigentümerportal lesend
- Quellenstatus (Anhang C): Fachliche Umsetzung und Produktschutz, keine Rechtsgrundlage
- Abnahmefall: Aus offenen Punkten der Checkliste entstehen per Knopf Tickets, ein zweiter Aufruf legt keine weiteren an. Ein Eigentümer sieht den Stand der Checkliste seines Objekts ohne Notizen. Beim Übernehmen eines Objektvorschlags entstehen Bankkonten, Umlageschlüssel aller vier Arten mit Einheitenwerten, Debitorenkonten und Dokumentverknüpfungen in einer Transaktion; die Rücknahme entfernt sie wieder, solange nichts darauf gebucht oder zugeordnet wurde. Die Vorschau des Personenabgleichs zeigt je Person die Entscheidung als Tabelle.
- Änderungsgrund: Reste von M7-01 und M7-02 aus der Lückenliste 30.09.2026 (Paket R03)
- Regeln:
  - Tickets aus der Checkliste entstehen nur für Punkte mit Status offen oder angefordert und ohne Ticket (`property_takeover_item.ticket_id`, Migration 0285). Sie sind intern, nicht für Portalnutzer freigegeben. Nötig sind Objekt ändern und Tickets anlegen.
  - Das Eigentümerportal zeigt je eigenem Objekt nur Bezeichnung, Status und Fälligkeit je Punkt, nie Notizen, Dokumente oder Tickets der Verwaltung. Es gibt keine Schreibfunktion.
  - Bankkonten, Umlageschlüssel und Werte stammen nie aus dem KI-Vorschlag, sondern aus der Eingabe in der Bestätigung. Ein vorhandener Schlüsselcode erhält nur Werte, ein neuer braucht Name, Einheit und Art. Verbrauchsschlüssel erhalten keine Einheitenwerte. Vorhandene Werte werden nicht überschrieben.
  - Ein Bankkonto wird nur angelegt, wenn genau ein passender Rechtsträger des Objekts besteht (Anhang 6.9.1, D56); sonst Hinweis, keine Zuordnung geraten. Kautionskonten sind nie Standardkonto.
  - Debitorenkonten: Ein vorhandener Buchungskreis übernimmt die reservierten Nummern, fehlt er, wird er aus der Kontenvorlage (Entwurf) angelegt. Gebucht wird nichts, Buchungen bleiben hinter G1.
  - Quelldokumente werden dem Objekt als Original verknüpft, weitere gewählte Dokumente als Anlage. Die Rücknahme löst nur die Verknüpfung, Originale bleiben (D46).
  - Die Vorschau des Personenabgleichs (`POST /onboarding/person-match-batch`) schreibt nichts und nutzt die Schwellwerte des Mandanten.

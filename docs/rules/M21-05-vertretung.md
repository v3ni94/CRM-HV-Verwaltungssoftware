# M21-05 Vertretung im Portal (Vertreter, Bevollmächtigter)

- **ID:** M21-05 (Teil Vertretung; die Datei M21-05.md behandelt einen anderen Gegenstand).
- **Geltungsbereich:** Portalkonten mit einer Vollmacht (`portal_representation`), Abschnitt 14 Eigentümer.
- **Quellenstatus (Anhang C):** Fachliche Umsetzung und Produktschutz, keine Rechtsgrundlage. Ob eine Vollmacht rechtswirksam ist, prüft die Geschäftsführung anhand des Dokuments, das System bewertet das nicht.
- **Regel:**
  1. Die Vollmacht verlangt ein Vertretungsnachweis-Dokument, Beginn und optional Ende. Der Zugriff ist lesend und auf den Zeitraum begrenzt (Grants mit `legal_basis=representation`, `valid_from`, `valid_to`).
  2. Der Zugriff wird im Zugriffspfad (`access.grants`) tagesgenau geprüft: nach Ablauf von `valid_to` oder nach Widerruf besteht kein Zugriff, ohne dass ein Job laufen muss.
  3. `/portal/me` liefert die Rolle `representative` nur bei einer aktuell gültigen Vollmacht. Verträge, die nur über die Vollmacht erreichbar sind, machen das Konto nicht zum Eigentümer (`owner`).
  4. `GET /portal/representations` zeigt die eigenen Vollmachten mit Zustand (active, pending, expired, revoked), Name des Vertretenen, Zeitraum und Resttagen. Das Dokument und weitere Daten des Vertretenen werden nicht ausgegeben.
- **Abnahmefall:** `tests/integration/test_p13_portal.py::test_representative_sees_owner_view_only_within_period` und `::test_expired_representation_loses_access`.
- **Änderungsgrund:** Lückenliste 30.09.2026, M21-05 Rest (Vertreterrolle sichtbar, Ablauf, Zugriffsverlust).

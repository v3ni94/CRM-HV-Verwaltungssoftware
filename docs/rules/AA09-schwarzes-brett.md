# AA09 Schwarzes Brett nach 6.2: Kategorie, Hinweisstufe, Zielgruppenliste, Mehrfachanhänge, Lesebestätigung

| Field | Content |
| --- | --- |
| ID | `AA09` (Befund GA02-02) |
| Title | Aushänge tragen Kategorie, Hinweisstufe und eine Liste von Zielgruppen, mehrere Anlagen und eine Lesebestätigung je Portalkonto; das CRM zeigt die Lesequote |
| Scope | `mhvp.portal.notices` (`PropertyNotice`, `NoticeBoardRead`), `mhvp.portal.notice_routers`, Migration 0311, CRM `PropertyNotices`, Portal `NoticeList` |
| Source status | Fachliche Umsetzung nach 6.2 `notice_board_post`. Die Lesebestätigung ist ein Indiz für die Kenntnisnahme im Portal, keine Zustellung und kein rechtlich bewerteter Zugang (wie A53, M21-06 Regel 5). Keine Rechtsaussage |
| Acceptance case | Tests `apps/api/tests/integration/test_ga02_02_notice_board.py`, `test_m21_notices.py`; Web: `PropertyNotices.test.tsx`, `NoticeList.test.tsx` |
| Implementation | Migration 0311 |
| Change reason | GA02-02: Kategorie, Stufe, Mehrfachzielgruppe, Mehrfachanhänge und Lesebestätigung fehlten |

## Regel

1. **Hinweisstufe.** `type` ist `neutral`, `info`, `warning` oder `danger` (CHECK-Constraint,
   Standard `neutral`). Das Portal zeigt die Stufe farblich und mit Text.
2. **Kategorie.** `category` ist ein Code des Katalogs `notice_category`; ein unbekannter
   Code wird mit 422 abgewiesen.
3. **Zielgruppen.** `audiences` ist eine Liste aus `tenant`, `owner`, `provider` (mindestens
   ein Eintrag). Der alte Einzelwert `audience` wird weiter akzeptiert (`all` bedeutet Mieter
   und Eigentümer) und in der Antwort als Altwert mitgeliefert. Dienstleister sehen einen
   Aushang für ein Objekt, an dem sie einen Auftrag haben.
4. **Anlagen.** `document_ids` nimmt mehrere Dokumente des Mandanten. Jedes Dokument muss für
   jede gewählte Zielgruppe freigegeben sein (Sichtbarkeit 6.9.6), sonst 422. Der Download läuft
   über den Aushang und folgt dessen Sichtbarkeit; eine fremde Dokument-ID ergibt 404.
5. **Lesebestätigung.** `POST /portal/notices/{id}/read` schreibt je Aushang und Portalkonto
   höchstens eine Zeile `notice_board_read` (idempotent) und nur für sichtbare Aushänge (sonst
   404). Das Lesen der Liste schreibt nichts. Das CRM zeigt je Aushang `read_count` und
   `recipient_count` (adressierte Konten mit aktiver Freigabe, Dienstleister mit Auftrag) und
   die Einzelbestätigungen unter `GET /notices/{id}/reads` (Recht Objekte lesen).
6. Nichts davon löst eine Frist aus oder gilt als Zustellung.

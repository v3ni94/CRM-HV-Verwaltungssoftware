# M20-02 Eigenes Schema des Antwortentwurfs mit pflegbaren Stilregeln

| Field | Content |
| --- | --- |
| ID | `M20-02` |
| Title | Eigenes Schema des Antwortentwurfs mit pflegbaren Stilregeln |
| Scope | Domäne `communication` (Mailvorschlag), Postfachstil `mailbox.reply_style`, alle Mandanten |
| Source status | Keine Rechtsnorm im Quellenregister (annex C); Produktschutz, Abschnitt 9.2 draft_reply |
| Acceptance case | Tests `apps/api/tests/unit/test_q14_letter_images.py::test_draft_reply_schema_checks_placeholders_and_keeps_style`, Vitest `MailboxSettings.test.tsx` |
| Implementation | `mhvp.communication.suggest.MailDraftReply`, `draft_reply_payload`, `reply_style_text`; CRM `MailboxSettings` (Tonfall und Stilregeln) |
| Change reason | Lückenliste 30.09.2026 M20-02: Stilregeln waren nur per API pflegbar, der Entwurf hatte kein eigenes Schema |

## Regeln

- Der Vorschlag einer Mail trägt neben den Klassifikationsfeldern ein eigenes Objekt `draft_reply` mit
  Text, Tonfall der Antwort, verwendeten Platzhaltern, unbekannten Platzhaltern (geschweifte Klammern, die keine
  Vorlage füllt) und dem Postfachstil, unter dem der Entwurf entstand.
- Der Postfachstil (Tonfall und freie Regeln bis 2000 Zeichen) wird im CRM unter den Postfacheinstellungen
  gepflegt. Fehlt er, gilt der Tonfall sachlich. Die Regeln gehen als Text in den Auftrag an den Anbieter.
- Der Entwurf ist ein Vorschlag. Er wird nie selbstständig versendet, Freigabe und Vier-Augen-Regel des
  Mailversands gelten unverändert. Die Regeln ersetzen keine rechtliche Prüfung des Textes.

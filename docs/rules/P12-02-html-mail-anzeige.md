# P12-02 HTML-Mails im Sandbox-Rahmen ohne externe Ressourcen

| Field | Content |
| --- | --- |
| ID | `P12-02` |
| Title | HTML-Mails im Sandbox-Rahmen ohne externe Ressourcen |
| Scope | Domäne `communication`, CRM Ticket-Mailverlauf (`MailHtmlFrame`) |
| Source status | Produktschutz (Datenschutz, Zählpixel); keine Rechtsnorm zitiert. Entscheidung des Eigentümers in OPEN_QUESTIONS P12-02 bleibt zu bestätigen |
| Acceptance case | Vitest `LettingW3.test.tsx` (MailHtmlFrame), `TicketMailThread.test.tsx` |
| Implementation | `apps/web-crm/src/components/mail/MailHtmlFrame.tsx` |
| Change reason | Lückenliste 30.09.2026 P12-02: bereinigtes HTML wurde direkt eingebettet, externe Bilder luden sofort |

## Regeln

- HTML-Mails erscheinen in einem iframe mit sandbox ohne Skripte. Die Content Security Policy des Dokuments
  verbietet Skripte, Rahmen, Schriften und jede Netzwerkanfrage, erlaubt sind nur eingebettete Bilder (data, cid).
- Bilder mit Webadresse werden erst nach Klick auf "Bilder laden" zugelassen. Der Hinweis erscheint nur, wenn
  die Mail solche Bilder enthält. Der Referrer wird nicht gesendet.
- Die serverseitige Bereinigung bleibt als zweite Schicht bestehen.

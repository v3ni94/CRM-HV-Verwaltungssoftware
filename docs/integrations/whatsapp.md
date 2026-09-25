# WhatsApp Business Platform (Meta Cloud API, M21-05)

Setup-Anleitung für den WhatsApp-Eskalationskanal (`mhvp.sla.whatsapp`,
`docs/rules/M21-05.md`). Keine Preise: diese sind aus dem eigenen Meta-Geschäftskonto zu lesen
(Business-Tarife, Vorlagenkategorien und Länderpreise ändern sich unabhängig von diesem
Dokument).

## 1. Voraussetzungen bei Meta

1. Meta-Geschäftskonto (Business Manager) anlegen oder ein bestehendes verwenden;
   Geschäftsverifizierung ("Business Verification") durchlaufen (Handelsregisterauszug/
   Gewerbenachweis der handelnden Gesellschaft, siehe CLAUDE.md Abschnitt Gesellschaften).
2. WhatsApp Business Account (WABA) im Business Manager anlegen.
3. Telefonnummer registrieren, die noch nicht in einer normalen WhatsApp- oder
   WhatsApp-Business-App verwendet wird (Portierung aus der App ist möglich, aber
   destruktiv für die App-Nutzung). Verifizierung per SMS oder Anruf.
4. Meta-App im Meta for Developers Portal anlegen, Produkt "WhatsApp" hinzufügen; daraus
   ergeben sich `phone_number_id` und `whatsapp_business_account_id` (in der App-Konsole
   unter WhatsApp → API Setup sichtbar).
5. Dauerhaftes System-User-Zugriffstoken erzeugen (Business-Einstellungen → Systembenutzer),
   Berechtigung `whatsapp_business_messaging` und `whatsapp_business_management`; ein
   temporäres 24-Stunden-Token aus der Schnellstart-Ansicht reicht nur zum Testen.
6. Nachrichtenvorlagen anlegen und zur Prüfung einreichen (WhatsApp Manager →
   Nachrichenvorlagen). MHVP versendet ausschließlich Vorlagen, nie Freitext (rule
   `docs/rules/M21-05.md`): pro Alarmtyp wird eine Vorlage benötigt, z. B.
   - `sla_eskalation_de` (Kategorie "Utility"): Textkörper mit drei Parametern
     (Ticketnummer, Eskalationsstufe, Titel), Sprache Deutsch.
   - `notfall_de` (Kategorie "Utility"): analog für den Notfallalarm (Stufe 0).
   - `test_de` (Kategorie "Utility"): ein Parameter (Testtext) für die Testnachricht-Funktion.

   Namen und Wortlaut sind frei wählbar; die Zuordnung zum Alarmtyp geschieht im CRM
   (Reiter SLA → WhatsApp, Feld "Vorlagennamen je Alarmtyp"). Freigabe durch Meta kann
   Stunden bis Tage dauern; abgelehnte Vorlagen liefern beim Versand einen Fehlertext.

## 2. Webhook einrichten

1. Im Meta for Developers Portal unter WhatsApp → Konfiguration die Webhook-URL eintragen:
   `https://<MHVP_API_PUBLIC_URL>/api/v1/whatsapp/webhook`.
2. Verifizierungstoken frei wählen (beliebige Zeichenfolge) und identisch in
   `MHVP_WHATSAPP_VERIFY_TOKEN` hinterlegen; Meta ruft beim Speichern `GET` mit
   `hub.mode=subscribe`, `hub.verify_token`, `hub.challenge` auf
   (`mhvp.sla.whatsapp_webhook.verify`), das Token muss übereinstimmen.
3. Feld "messages" (bzw. den Statuswebhook-Typ) abonnieren, damit Zustellstatus
   (`sent`/`delivered`/`read`/`failed`) an `sla_whatsapp_delivery` zurückgemeldet wird.
4. App-Secret der Meta-App (Einstellungen → Grundlegendes) in `MHVP_WHATSAPP_APP_SECRET`
   hinterlegen; jede eingehende Statusmeldung wird per `X-Hub-Signature-256`
   (HMAC-SHA256 über den rohen Anfragetext) geprüft, eine falsche oder fehlende Signatur
   wird stillschweigend verworfen (`mhvp.sla.whatsapp.verify_webhook_signature`).

## 3. Konfiguration im CRM (je Mandant)

Unter Einstellungen → SLA → Reiter "WhatsApp" (nur mit Recht `sla:update`):

| Feld | Inhalt |
| --- | --- |
| Aktiv | Schalter, Standard aus; ohne Aktivierung wird nichts versendet |
| Telefonnummer-ID | `phone_number_id` aus Schritt 1.4 |
| WhatsApp-Business-Account-ID | `whatsapp_business_account_id` aus Schritt 1.4 |
| Zugriffstoken | Systembenutzer-Token aus Schritt 1.5; verschlüsselt gespeichert, nie ausgelesen |
| Vorlagennamen je Alarmtyp | Meta-Vorlagenname je Alarmtyp (`sla_escalation`, `emergency`, `test`) |
| Sprache der Vorlagen | Sprachcode wie bei Meta hinterlegt (Standard `de`) |
| SMS als Rückfall verwenden | Bei Fehlschlag automatisch über das bestehende SMS-Gateway senden (Standard an) |

Eine "Testnachricht senden" verschickt die unter Alarmtyp `test` hinterlegte Vorlage an eine
Mitarbeiter-Mobilnummer.

## 4. Umgebungsvariablen (App-Ebene, `.env.prod` bzw. Deployment-Secrets)

| Variable | Inhalt |
| --- | --- |
| `MHVP_WHATSAPP_VERIFY_TOKEN` | Beliebiges, geheim zu haltendes Token für die Webhook-Verifizierung (Schritt 2.2) |
| `MHVP_WHATSAPP_APP_SECRET` | App-Secret der Meta-App (Schritt 2.4), niemals im Code oder in Logs |
| `MHVP_WHATSAPP_API_BASE_URL` | Optional, Standard `https://graph.facebook.com/v21.0`; nur bei Versionswechsel der Cloud API ändern |

Mandantenspezifische Werte (Telefonnummer-ID, WABA-ID, Zugriffstoken, Vorlagennamen) gehören
nicht in Umgebungsvariablen, sondern in die Mandantenkonfiguration (Abschnitt 3).

## 5. Grenzen (rule 0.1.3, docs/rules/M21-05.md)

- Kein Freitext: nur bei Meta freigegebene Vorlagen werden gesendet.
- Kein automatischer Versand an Mieter oder Eigentümer ohne erfasste Einwilligung
  (`ConsentKind.WHATSAPP`); die SLA-Eskalation benachrichtigt ohnehin nur Mitarbeiter und
  Bereitschaft (Annahme A-040, `docs/ASSUMPTIONS.md`).
- Preise für gesendete Vorlagennachrichten (Conversation-based Pricing) sind aus dem
  Meta-Geschäftskonto (Zahlungseinstellungen → Preisübersicht) zu entnehmen und hier nicht
  hinterlegt.

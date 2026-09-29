# M30-08 Übergabeprotokoll: Vorschaubilder als abgeleitete Ansicht (Produktschutz)

| Field | Content |
| --- | --- |
| ID | `M30-08` |
| Title | Vorschaubilder der Protokollfotos werden bei jedem Abruf aus dem gespeicherten Bild erzeugt, nie gespeichert und nie im Browser zwischengespeichert |
| Scope | Domäne `handover`; CRM Pfad `GET /handover/protocols/{id}/documents/{doc}/thumbnail` (Recht `contracts:read`), Portal Pfad `GET /portal/handover/{id}/documents/{doc}/thumbnail` (Grant `handover` auf genau dieses Protokoll); Proxy `apps/web-crm/src/app/api/handover-files` |
| Source status | Keine Rechtsnorm im Quellenregister (annex C) einschlägig; interner Produktschutz (Datenschutz: keine zusätzliche Kopie personenbezogener Bilder, Beweis: nur das Original trägt die Prüfsumme). Aufbewahrungsklasse der Protokollfotos bleibt offen (V17, M6-04) |
| Acceptance case | keine in annex D; Tests `apps/api/tests/integration/test_m30_handover.py::test_wp2_steps_hint_codes_thumbnail_and_date_filter`, `apps/api/tests/unit/test_m30_handover_images.py::test_thumbnail_is_small_jpeg_for_jpeg_and_png`, `apps/web-crm/src/app/api/handover-files/[...path]/route.test.ts` |
| Implementation | `mhvp.handover.images.thumbnail`, `mhvp.handover.routers.document_thumbnail`, `mhvp.handover.portal.document_thumbnail`, `mhvp.handover.services.documents_of` (`thumbnail_url`), CRM `PhotoStrip.tsx`, `PhotoGallery.tsx` |
| Change reason | M31 WP2 (Bedienung auf Handy und Tablet), 29.09.2026: 96 px Kacheln mit dem vollen Bild waren am Handy zu langsam |

## Regeln

- Das Vorschaubild ist eine abgeleitete Ansicht (S03 sinngemäß): längste Kante 320 px,
  JPEG, erzeugt aus dem bereinigten Serverbild (M30-04) beim Abruf. Es wird nicht als
  Dokument, nicht als Blob und nicht in einem Zwischenspeicher des Servers abgelegt.
- Zugriffsprüfung wie beim Original: das Dokument muss über `documents_of` mit dem
  angefragten Protokoll verknüpft sein, sonst 404 (auch für Dokumente desselben
  Mandanten an einem anderen Protokoll). Fremde Mandanten erhalten 404 über RLS. Im Portal
  gilt zusätzlich der Grant auf das Protokoll.
- Nur Fotos von Teildatensätzen und Bildanhänge (JPEG, PNG, WEBP) liefern ein
  Vorschaubild; Unterschriften (Beweisbild) und das PDF antworten 404, `thumbnail_url`
  ist dort `null`.
- Antwort mit `Cache-Control: private, no-store`, `X-Content-Type-Options: nosniff`; der
  CRM Proxy setzt no-store auf allen Dateipfaden. Ein Browser Cache für Vorschaubilder ist
  eine offene Betreiberfrage (Plan M31, Frage 6), bis dahin kein Cache.
- Keine Zugriffsprotokollierung für Vorschaubilder (offene Betreiberfrage, Plan M31 Frage
  10); der Originalabruf bleibt wie bisher.
- Löschsemantik unverändert (M30-01): Entfernen eines Fotos löst die Verknüpfungen dieser
  Fassung; ist das Foto in keiner anderen Fassung verknüpft, wird die Datei endgültig
  gelöscht. Die Oberfläche fragt mit genau diesem Text.
- Clientseitige Verkleinerung vor dem Upload (`apps/web-crm/src/lib/image-downscale.ts`)
  ist Transport, keine Ablage: der Server bleibt der einzige Weg in den Speicher und die
  Prüfsumme gilt für das bereinigte Serverbild (Ergänzung in M30-01).

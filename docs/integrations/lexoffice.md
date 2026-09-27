# lexoffice Integration (M13-lexoffice)

Binding interface document for `apps/api/src/mhvp/integrations/lexoffice.py`
(`mhvp.integrations.lexoffice.LexofficeClient`). The client calls only the endpoints listed
here as verified (master prompt section 3, rule 0.1.3, section 13.3).

## Quelle

Retrieved 27.09.2026 via WebFetch from `https://developers.lexoffice.io/docs/`, which 301s to
`https://developers.lexware.io/docs/` (lexoffice's public API moved under the Lexware brand).
Base URL `https://api.lexware.io`, header `Authorization: Bearer {accessToken}`, keys issued at
`https://app.lexware.de/addons/public-api`. Rate limit per the documentation: 2 requests/second,
HTTP 429 on excess (`MHVP-LEXO-0004`, not retried automatically).

## Verifizierte Endpunkte (Stand 27.09.2026)

| Endpoint | Verwendung hier |
| --- | --- |
| `GET /v1/profile` | Verbindungstest ("Verbindung testen") |
| `POST /v1/contacts` | Kontaktexport, Payload-Passthrough |
| `GET/PUT /v1/contacts/{id}` | vorgesehen, noch nicht angebunden |
| `POST /v1/vouchers` | Beleg-/Rechnungsexport (Voucher), Payload-Passthrough |
| `GET /v1/vouchers/{id}` | Belegdetails lesen (Import) |
| `GET /v1/voucherlist` | Belegliste (Paging `page`, Filter `updatedAtFrom`, `voucherType`) |
| `POST /v1/files` | Dateianhang hochladen, vorgesehen, noch nicht angebunden |
| `POST /v1/invoices[?finalize=true]` | Ausgangsrechnung anlegen, Payload-Passthrough |

Ein Endpunkt, der hier nicht aufgeführt ist, wird nicht aufgerufen.

## Offene Punkte (rule 0.1.3: Unsicherheit ist keine Rechtsgrundlage)

Die per WebFetch erreichbare Dokumentation lieferte nur für Sales-Voucher (Ausgangsrechnungen,
Gutschriften, Lieferscheine, Angebote, Auftragsbestätigungen) Feldbeispiele
(`voucherDate`, `address`, `lineItems`, `totalPrice`, `taxConditions`); für **Eingangsrechnungen
(Purchase Invoice Voucher)** und für die genaue **Kontakt-JSON-Struktur** konnte keine
vollständige Feldliste bestätigt werden. Deshalb baut `LexofficeClient` und der Router
(`mhvp.integrations.routers`) das Anfrage-JSON für `create_voucher`/`create_contact`/
`create_invoice` **nicht selbst**; der Aufrufer liefert ein fertiges, geprüftes Payload je
Position (`LexofficeExportInvoiceItem.payload` / `LexofficeExportContactItem.payload`). Vor
produktiver Nutzung muss die vollständige Feldreferenz (lexoffice-Kochbücher/Support,
siehe docs/OPEN_QUESTIONS.md M13-lexoffice-01) durch den Betreiber bzw. Steuerberater
bestätigt werden, insbesondere Steuertyp/-satz-Zuordnung.

Die Verknüpfung eines Vouchers mit seiner PDF-Datei (`files`/`fileId` innerhalb der
Voucher-Antwort) ist ebenfalls nicht bestätigt. Der Import legt deshalb zunächst die rohe
lexoffice-Beleg-JSON als Dokument ab (`mime_type application/json`), nicht die eigentliche
PDF; siehe docs/OPEN_QUESTIONS.md M13-lexoffice-02.

## Anbindung je Mandant

- `PUT /api/v1/integrations/lexoffice/config` (Berechtigung `tenant_settings:update`):
  API-Schlüssel (feldverschlüsselt, `LexofficeTenantConfig.api_key`), `base_url` (Standard
  `https://api.lexware.io`) und `enabled` (Feature-Flag, Standard **aus**, rule 0.1.1).
- `POST /api/v1/integrations/lexoffice/test`: ruft `GET /v1/profile` auf, protokolliert das
  Ergebnis (`LexofficeSyncRun`, Art `test`) und aktualisiert `last_tested_at`/`last_test_ok`/
  `last_test_message` auf der Konfiguration.
- `GET /api/v1/integrations/lexoffice/runs`: letzte 50 Läufe mit Status und Fehlern
  ("Abgleichsseite", Einstellungen, Schnittstellen).

## Export (explizit, protokolliert, Gate G1)

- `POST /api/v1/integrations/lexoffice/export/invoices` und `.../export/contacts`
  (Berechtigung `accounting:create`, zusätzlich Freigabestufe G1 offen für den Mandanten,
  `mhvp.core.release_gates`). Kein Automatismus: der Aufruf listet explizit die Rechnungs-
  bzw. Kontakt-IDs samt geprüftem lexoffice-Payload; jede Position wird einzeln protokolliert
  (`LexofficeSyncRun`) und, bei Erfolg, in `LexofficeExportLink` (Dublettenschutz: dieselbe
  Entität wird ohne `force: true` nicht zweimal exportiert) vermerkt.
- Ausgangsrechnungen: Zum Zeitpunkt dieser Anbindung gibt es im Kern (`mhvp.accounting`) noch
  kein eigenes Modell für Ausgangsrechnungen der Hausverwaltung (nur `Invoice` als
  Eingangsrechnung, 7.9.1); der Export-Endpunkt für Rechnungen bedient deshalb zunächst
  bestehende `Invoice`-Datensätze (Eingangsrechnungen/Belege) und ist technisch bereits so
  gebaut, dass er ein beliebiges, geprüftes Voucher-Payload entgegennimmt. Sobald ein
  Ausgangsrechnungsmodell existiert (Rechnungsstellung der HVM an WEG/Vermieter, siehe V7),
  kann derselbe Endpunkt ohne Schemaänderung mitgenutzt werden; siehe
  docs/OPEN_QUESTIONS.md M13-lexoffice-03.

## Import (Belegentwurf, kein Automatismus)

- `POST /api/v1/integrations/lexoffice/import/receipts` (Berechtigung `accounting:create`,
  kein G1 nötig: es entsteht nur ein `ReceiptDraft`, keine Buchung). Ruft `GET /v1/voucherlist`
  auf (Filter `voucherType=purchaseinvoice`, optional `updatedAtFrom`), liest je gefundenem
  Beleg die rohe JSON und legt sie als `Document` (`source_system="lexoffice"`,
  `source_id=<lexoffice-Beleg-ID>`) sowie einen `ReceiptDraft`
  (`source=ReceiptDraftSource.LEXOFFICE`, Status `proposed`) ab. Dublettenschutz: die
  eindeutige Kombination `tenant_id, source_system, source_id` auf `Document` (Migration 0011)
  verhindert einen zweiten Import desselben Belegs; ein zweiter Aufruf liefert den bereits
  vorhandenen `ReceiptDraft` zurück (`duplicate: true`).
- Die Felder im Entwurf sind unbereinigte Rohdaten aus lexoffice (`fields.lexoffice_raw`,
  `source: "local"`) plus, wenn vorhanden, eine unverifizierte Zuordnung von
  `voucherNumber`/`voucherDate`/`totalGrossAmount`; eine Warnung im Entwurf macht das
  ausdrücklich kenntlich. Die Sachbearbeitung prüft und ergänzt die Felder wie bei jedem
  anderen Belegentwurf (`mhvp.receipts`).

## Fehlercodes

`MHVP-LEXO-0001` nicht eingerichtet/Flag aus, `-0002` nicht erreichbar, `-0003`
Zugangsdaten abgelehnt (401/403), `-0004` Anfragelimit (429), `-0005` Gate G1 geschlossen.

## smart-einzug

Für smart-einzug (Masterprompt 13.3) gibt es keine öffentlich dokumentierte REST-API (Stand
27.09.2026, WebFetch-Recherche ohne Treffer auf eine Entwicklerdokumentation). Es wird daher
keine Anbindung erstellt und kein Endpunkt erfunden; siehe die Betreiberentscheidung in
docs/OPEN_QUESTIONS.md M13-lexoffice-04.

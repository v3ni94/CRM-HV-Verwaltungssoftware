# AJ10: Uploads und Webhook-Körper begrenzen

- ID: AJ10-UPLOAD-LIMITS
- Geltungsbereich: alle Upload-Endpunkte (UploadFile) und alle Webhooks (Rohkörper).
- Quellenstatus Anhang C: Produktschutz, keine Rechtsregel.
- Regel: Uploads werden vor dem Lesen begrenzt (Blocklesen, Abbruch mit 413 MHVP-DOC-0010).
  Webhook-Körper werden vor der HMAC Prüfung begrenzt (WhatsApp 256 KiB, MHVP-HOOK-0004).
  Dump-Importe (U-Protokoll, objektakte) werden nach Endung, Inhaltstyp und Signatur geprüft.
  Primärschlüssel neuer Fachzeilen (Schadenstool, Messdaten-Import) sind UUID v7.
- Abnahmefall: `tests/unit/test_aj10_uploads.py`.
- Änderungsgrund: Lückenanalyse GAI-313, GAI-314, GAI-315, GAI-106 (Welle 21).

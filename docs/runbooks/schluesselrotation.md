# Schlüsselrotation der verschlüsselten Felder (S16-03)

Werkzeug: `python -m mhvp.core.key_rotation` (Modul `apps/api/src/mhvp/core/key_rotation.py`).
Offene Punkte: `docs/OPEN_QUESTIONS.md` Q13-02.

## Wirkung

- Alle Spalten vom Typ `EncryptedText` werden aus dem Datenmodell ermittelt, keine Liste von
  Hand. Die Mandantenschlüssel werden per HKDF aus dem Master-Schlüssel abgeleitet; ein neuer
  Master-Schlüssel erneuert damit alle Mandantenschlüssel und den Plattformbereich.
- Je Mandant eine eigene Transaktion mit Mandantenbindung (RLS), je Tabelle ein Sicherungspunkt.
  Der Inhalt ändert sich nicht, `updated_at` bleibt erhalten.
- Schlüsselgebundene Fingerabdrücke (`<spalte>_fingerprint`) werden neu berechnet, wenn sie
  zum alten Schlüssel passen; passt ein Wert nicht, wird die Zeile nicht geschrieben und im
  Protokoll als `mismatch` gezählt.
- Chiffrate, die schon mit dem neuen Schlüssel lesbar sind, zählen als `already_rotated`. Ein
  abgebrochener Lauf wird einfach wiederholt.
- Fingerabdruckspalten ohne verschlüsselte Partnerspalte und Chiffrate in JSON (`secret_enc`)
  sperren das Schreiben (Protokoll `blockers`), der Lauf bleibt dann ein Dry-Run.

## Ablauf

1. Datensicherung prüfen (`docs/runbooks/backup.md`).
2. Neuen Schlüssel erzeugen: `openssl rand -base64 32`.
3. Schlüssel nur über die Umgebung übergeben, nie auf der Kommandozeile:
   `MHVP_OLD_MASTER_KEY` (bisheriger Schlüssel), `MHVP_NEW_MASTER_KEY` (neuer Schlüssel).
4. Probelauf: `python -m mhvp.core.key_rotation --dry-run --protocol rotation-dry.json`.
   Das Protokoll enthält Zählungen je Tabelle, Spalte und Status sowie gekürzte Hashwerte der
   Schlüssel, nie Klartext oder Schlüssel.
5. Bei `blockers` oder `errors` abbrechen und klären.
6. Wartungsfenster: API und Worker anhalten, dann
   `python -m mhvp.core.key_rotation --protocol rotation.json`. Rückgabewert 0 heißt vollständig.
7. `MHVP_MASTER_KEY` auf den neuen Schlüssel setzen, API und Worker starten, Stichprobe
   (Kontakt mit IBAN öffnen, Bankkonto-Abgleich).
8. Alten Schlüssel verwahren, bis die Sicherungen mit alten Chiffraten abgelaufen sind.
   Protokolle zur Akte nehmen.

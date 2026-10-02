# ADR 0030: Mandantenbranding und Portal-White-Label

- Status: Accepted
- Date: 2026-10-02

## Context

Dokumente, CRM und Portal sollen je Mandant (und je Portal-Domain) mit eigenem Erscheinungsbild auftreten. Ein Beschluss zur Datenhaltung und zur Grenze des Brandings war nicht dokumentiert (Befund GAI-516 Umfeld, Nachtrag zu GAI-608).

## Decision

1. Das Branding liegt je Mandant als validiertes JSON im Mandantenstamm (`platform/schemas.py:46`, Klasse `Branding`, `extra="forbid"`): Farben (Hex), Schriftfamilie, Logo-Dokumente hell und dunkel (Dokument-IDs), Briefkopf-Farbband (`letter_band`, höchstens 8 Segmente) und `portal_name` (höchstens 80 Zeichen). Leer bedeutet neutral, nichts wird erfunden (Kommentar B26/M21-04).
2. Änderung nur über die Mandanteneinstellungen (`platform/routers.py`, ab Zeile 483). Logos werden als PNG oder JPEG über `/tenant/branding/logo/{variant}` ausgeliefert.
3. Das Portal bestimmt den Mandanten über die Portal-Domain (Header `X-Portal-Host`, sonst Host). Der öffentliche Pfad liefert ausschließlich Branding (Farben, Logo, rechtliche Links), nie Mandantendaten (`platform/routers.py:923-926`). Im Portal sind nur die Pfade `/api/branding-logo/` und die Rechtsseiten ohne Anmeldung erreichbar (`apps/web-portal/src/middleware.ts:22`).
4. Rechtliche Pflichtangaben und Briefkopf der Gesellschaften bleiben Sache der jeweiligen CI-Skills und der Mandantenstammdaten, nicht des freien Brandings.

## Consequences

- Neue Brandingfelder erfordern eine Schemaänderung im Modell `Branding` und Tests für Validierung und Mandantentrennung.
- Branding ersetzt keine Rechtstexte; Impressum und Datenschutz sind getrennt freizugeben.
- Logos sind Dokumente und unterliegen der Dokumentenablage und Virenprüfung.

## Alternatives considered

- Eigene Tabelle je Brandingfeld: mehr Schema, kein Vorteil bei kleinem, geschlossenem Feldsatz.
- Branding nur im Frontend: Dokumente (PDF) und Portal könnten es nicht einheitlich nutzen.

## References

- `docs/MASTER-PROMPT.md` Abschnitt 3.3 (Portal-Domains)

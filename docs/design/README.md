# Gestaltung der Web-CRM

Bausteine und Entscheidungen zur Oberfläche. Farb- und Abstandswerte stehen in
[tokens.md](tokens.md).

## Befehlspalette (Vorschlag 1, Betreiberentscheidung 27.09.2026)

`apps/web-crm/src/components/shell/CommandPalette.tsx` ersetzt die frühere Suche. Ein Eingabefeld,
geöffnet mit Strg+K, Cmd+K oder der Schaltfläche in der Kopfzeile, liefert in Gruppen: Zuletzt
geöffnet (localStorage je Benutzer), Aktionen (`palette-actions.ts`, je Aktion eine
Berechtigung), Navigation (alle Einträge der Seitenleiste, vom Layout übergeben) und Treffer
aus `GET /workspace/search`. Rollen `dialog`, `combobox`, `listbox` und `option`, Fokusfalle,
Escape schließt. Neue Aktionen werden in `palette-actions.ts` mit Berechtigung und i18n-Schlüssel
unter `Shell.action` eingetragen.

## Statuschip (Vorschlag 7)

`apps/web-crm/src/components/ui/StatusChip.tsx` zeigt einen Status als Symbol plus Klartext;
Farbe ist nur zweiter Bedeutungsträger. Die Zuordnung Status zu Text, Ton, Symbol und
Erklärung steht je Fachbereich in `apps/web-crm/src/lib/status-labels.ts` (Tickets, Mail,
Mahnläufe, Lastschriftläufe, Freigabestufen, Zählerzuordnungen). Eine Erklärung öffnet sich
als Popover (`role="tooltip"`, `aria-describedby`), zum Beispiel "Wartet auf Freigabe, G2
geschlossen: Freigabe durch zweite Person nötig". Übersetzte Beschriftungen aus den
Katalogen können per `label` übergeben werden. `StatusPill` bleibt für rein dekorative Fälle
bestehen; neue Statusanzeigen verwenden den Chip.

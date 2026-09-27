# M19-01 SLA-Zeiten je Kategorie und Priorität: Entwurf bis zur Freigabe durch die Geschäftsführung

| Field | Content |
| --- | --- |
| ID | `M19-01` |
| Title | SLA-Regeln (Reaktions- und Lösungszeit) je Priorität und optional je Ticketkategorie sind Vorschlagswerte im Status Entwurf; nur von der Geschäftsführung freigegebene Werte steuern Uhren und Eskalationsstufen, sonst gilt "keine SLA" mit Hinweis |
| Scope | Alle Mandanten, Modul `mhvp.sla` (`sla_rule.category`, `approval_status`, `approved_at`, `approved_by`, Migration 0203), Uhrenstart in `mhvp.sla.service.start_clock` (Hooks Tickets, Mail, Portal, Nachlauf), Eskalation `mhvp.sla.escalation`, CRM Einstellungen SLA (`apps/web-crm/src/components/sla/SlaSettings.tsx`) |
| Source status | Produktschutz (0.2). Keine Rechtsnorm des Quellenregisters (Anhang C) gibt Reaktions- oder Lösungszeiten für Verwaltungsvorgänge vor; die Zeiten sind eine unternehmerische Festlegung des Betreibers. Offene Entscheidung M19-01 (Wertetabelle je Kategorie), Eigentümer Betreiber, kein Gate betroffen (kein Geldbezug) |
| Acceptance case | Keiner in Anhang D. Tests `apps/api/tests/integration/test_m19_sla_approval.py` (Entwurf ohne Fristen, Freigabe nur mit `tenant_settings:update` und Bestätigung, Änderung setzt zurück, Kategorie vor allgemeiner Regel, Presets als Entwurf), `test_m21_sla.py`, `test_cov_sla_tasks.py`; `apps/web-crm/src/components/sla/SlaSettings.test.tsx` (Freigabedialog, keine Freigabefelder im PATCH) |
| Implementation | Version nach 1.34.3 (Migration 0203). Bestehende Regeln werden mit der Migration auf Entwurf gesetzt und müssen einmalig freigegeben werden |
| Change reason | Betreiberauftrag 27.09.2026: SLA je Ticketkategorie, Freigabestatus mit Datum, Eskalation nur auf freigegebenen Werten |

## Regel

1. **Regel je Priorität und Kategorie.** `sla_rule` trägt optional `category` (Code der
   Ticketkategorie, leer = alle Kategorien). Eindeutig je Mandant, Priorität und Kategorie
   (`coalesce(category, '')`). Auflösung beim Uhrenstart: freigegebene Regel der Kategorie,
   sonst freigegebene Regel ohne Kategorie, sonst keine.
2. **Entwurf ist nicht wirksam.** Neue Regeln, Presets (`POST /sla/rules/presets`) und
   geänderte Zeiten (`PATCH`, Felder Priorität, Kategorie, Reaktion, Lösung, Uhrtyp) stehen
   auf `approval_status = draft`. Aktiv/Inaktiv und Kanalwahl je Stufe berühren die Freigabe
   nicht.
3. **Freigabe durch die Geschäftsführung.** `POST /sla/rules/{id}/approve` mit
   `confirm = true` verlangt `tenant_settings:update` (Mandantenverwaltung; das Recht
   `sla:update` der Sachbearbeitung genügt nicht). Datum, Benutzer und optionaler Vermerk
   werden gespeichert und als Ereignis `sla.rule_approved` protokolliert.
   `POST /sla/rules/{id}/revoke-approval` setzt zurück auf Entwurf.
4. **Ohne freigegebene Regel: keine SLA.** Die Uhr startet ohne `due_response_at` und
   `due_resolution_at`, das Protokoll (`sla_clock_log`) trägt den Hinweis
   "keine SLA: keine freigegebene Regel für Priorität und Kategorie". Ampel bleibt grün,
   Eskalationsstufen und Bereitschaftsalarm greifen nicht. Die früheren eingebauten
   Standardwerte (`DEFAULT_RULES`) sind nur noch Vorschlag zur Anzeige.
5. **Wirkung nur für neue Uhren.** Eine Freigabe oder Rücknahme ändert laufende Uhren nicht;
   sie werden bei Anlage berechnet und bleiben nachvollziehbar.

## Offene Punkte

- Wertetabelle je Kategorie (Betreiberentscheidung M19-01) bleibt offen; das System liefert
  nur Vorschläge je Priorität.
- Ob "Geschäftsführung" als eigene Rolle statt über `tenant_settings:update` abgebildet wird,
  entscheidet der Betreiber (M2, Rollenmodell).

<?php

declare(strict_types=1);

/**
 * Globale Hilfsfunktionen: Escaping, URLs, Formatierung, Wertelisten.
 */

function e(?string $value): string
{
    return htmlspecialchars($value ?? '', ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function url(string $path = '/'): string
{
    $base = rtrim(dirname($_SERVER['SCRIPT_NAME'] ?? ''), '/');
    return $base . '/' . ltrim($path, '/');
}

/** Datum TT.MM.JJJJ */
function fmt_date(?string $date): string
{
    if (!$date || $date === '0000-00-00') {
        return '';
    }
    $ts = strtotime($date);
    return $ts ? date('d.m.Y', $ts) : '';
}

function fmt_datetime(?string $dt): string
{
    if (!$dt) {
        return '';
    }
    $ts = strtotime($dt);
    return $ts ? date('d.m.Y H:i', $ts) . ' Uhr' : '';
}

function fmt_time(?string $t): string
{
    if (!$t) {
        return '';
    }
    $ts = strtotime($t);
    return $ts ? date('H:i', $ts) . ' Uhr' : '';
}

/** Betrag 1.234,56 EUR */
function fmt_amount(null|string|float $amount): string
{
    if ($amount === null || $amount === '') {
        return '';
    }
    return number_format((float) $amount, 2, ',', '.') . ' EUR';
}

/** Altformat-Fallback (Protokolle vor Umstellung auf UP-JJJJMMTT-NNN) */
function protocol_number(int $id): string
{
    return 'UP-' . str_pad((string) $id, 6, '0', STR_PAD_LEFT);
}

/** Formale IBAN-Prüfung (Mod-97). Leere Eingabe ist zulässig. */
function iban_is_valid(string $iban): bool
{
    $iban = strtoupper(str_replace(' ', '', $iban));
    if (!preg_match('/^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$/', $iban)) {
        return false;
    }
    $rearranged = substr($iban, 4) . substr($iban, 0, 4);
    $numeric = '';
    foreach (str_split($rearranged) as $char) {
        $numeric .= ctype_alpha($char) ? (string) (ord($char) - 55) : $char;
    }
    // Mod 97 stückweise, da die Zahl zu groß für int ist
    $remainder = 0;
    foreach (str_split($numeric, 7) as $chunk) {
        $remainder = (int) (($remainder . $chunk) % 97);
    }
    return $remainder === 1;
}

// ---------------------------------------------------------------------------
// Wertelisten (Beschriftungen in der UI und im PDF)
// ---------------------------------------------------------------------------

function protocol_types(): array
{
    return [
        'rental'  => 'Wohnungsübergabe (Vermietung)',
        'sale'    => 'Wohnungsübergabe (Verkauf)',
        'general' => 'Allgemeines Übergabeprotokoll',
    ];
}

function protocol_statuses(): array
{
    return [
        'draft'             => 'Entwurf',
        'in_progress'       => 'In Bearbeitung',
        'signature_pending' => 'Unterschrift ausstehend',
        'completed'         => 'Abgeschlossen',
        'sent'              => 'Versendet',
        'archived'          => 'Archiviert',
        'cancelled'         => 'Storniert',
        'rework'            => 'Nachbearbeitung erforderlich',
    ];
}

/** Hauptrollen je Protokolltyp: [rolle_ausziehend, rolle_einziehend, Label aus, Label ein] */
function party_roles(string $type): array
{
    return match ($type) {
        'sale'    => ['seller', 'buyer', 'Verkaufender Eigentümer', 'Kaufender Eigentümer'],
        'general' => ['handing_over', 'taking_over', 'Übergebende Partei', 'Übernehmende Partei'],
        default   => ['moving_out', 'moving_in', 'Ausziehender Mieter', 'Einziehender Mieter'],
    };
}

function participant_role_label(string $role, string $type = 'rental'): string
{
    [$outRole, $inRole, $outLabel, $inLabel] = party_roles($type);
    $extra = [
        'management' => 'Verwaltung', 'broker' => 'Makler', 'caretaker' => 'Hausmeister',
        'proxy' => 'Bevollmächtigter', 'witness' => 'Zeuge', 'relative' => 'Angehöriger',
        'expert' => 'Sachverständiger', 'craftsman' => 'Handwerker', 'other' => 'Sonstige Person',
    ];
    if ($role === $outRole || in_array($role, ['moving_out', 'seller', 'handing_over'], true)) {
        return $outLabel;
    }
    if ($role === $inRole || in_array($role, ['moving_in', 'buyer', 'taking_over'], true)) {
        return $inLabel;
    }
    return $extra[$role] ?? $role;
}

function extra_roles(): array
{
    return [
        'management' => 'Verwaltung', 'broker' => 'Makler', 'caretaker' => 'Hausmeister',
        'proxy' => 'Bevollmächtigter', 'witness' => 'Zeuge', 'relative' => 'Angehöriger',
        'expert' => 'Sachverständiger', 'craftsman' => 'Handwerker', 'other' => 'Sonstige Person',
    ];
}

function meter_types(): array
{
    return [
        'electricity' => 'Strom', 'gas' => 'Gas', 'water' => 'Wasser',
        'cold_water' => 'Kaltwasser', 'hot_water' => 'Warmwasser',
        'heating' => 'Heizungszähler', 'heat_quantity' => 'Wärmemengenzähler',
        'common_electricity' => 'Allgemeinstrom', 'sub_meter' => 'Zwischenzähler',
        'photovoltaic' => 'Photovoltaik', 'other' => 'Sonstiger Zähler',
    ];
}

function meter_units(): array
{
    return ['kWh', 'm³', 'MWh', 'Liter', 'Einheiten'];
}

function room_types(): array
{
    return [
        'Flur', 'Diele', 'Wohnzimmer', 'Schlafzimmer', 'Kinderzimmer', 'Arbeitszimmer',
        'Küche', 'Badezimmer', 'Gäste-WC', 'Abstellraum', 'Keller', 'Balkon', 'Terrasse',
        'Garten', 'Garage', 'Stellplatz', 'Dachboden', 'Hauswirtschaftsraum', 'Sonstiger Raum',
    ];
}

function room_conditions(): array
{
    return [
        'ok'             => 'Mängelfrei',
        'defective'      => 'Mängel vorhanden',
        'not_checked'    => 'Nicht geprüft',
        'not_accessible' => 'Nicht zugänglich',
        'not_included'   => 'Nicht Bestandteil der Übergabe',
    ];
}

function defect_categories(): array
{
    return [
        'Wand', 'Decke', 'Boden', 'Tür', 'Fenster', 'Rollladen', 'Heizung', 'Sanitär',
        'Elektrik', 'Einbauküche', 'Möbel', 'Feuchtigkeit', 'Schimmel', 'Beschädigung',
        'Verschmutzung', 'Sonstiger Mangel',
    ];
}

function defect_priorities(): array
{
    return ['info' => 'Hinweis', 'low' => 'Gering', 'medium' => 'Mittel', 'high' => 'Hoch', 'urgent' => 'Dringend'];
}

function defect_statuses(): array
{
    return [
        'pre_existing' => 'Bereits vorhanden', 'new' => 'Neu festgestellt',
        'acknowledged' => 'Vom Übergebenden anerkannt', 'rejected' => 'Anerkennung abgelehnt',
        'unclear' => 'Ungeklärt',
    ];
}

function key_types(): array
{
    return [
        'Haustürschlüssel', 'Wohnungstürschlüssel', 'Briefkastenschlüssel', 'Kellerschlüssel',
        'Garagenschlüssel', 'Stellplatzschlüssel', 'Gartenschlüssel', 'Hoftorschlüssel',
        'Nebeneingangsschlüssel', 'Sicherheitsschlüssel', 'Transponder', 'Chip',
        'Fernbedienung', 'Zugangskarte', 'Sonstiger Schlüssel',
    ];
}

function key_statuses(): array
{
    return ['handed_over' => 'Übergeben', 'not_handed_over' => 'Nicht übergeben', 'to_follow' => 'Nachzureichen'];
}

function item_types(): array
{
    return [
        'Fernbedienung', 'Zugangskarte', 'Bedienungsanleitung', 'Unterlagen', 'Energieausweis',
        'Wartungsunterlagen', 'Müllkarte', 'Parkausweis', 'Gerät', 'Möbel', 'Sonstiger Gegenstand',
    ];
}

function note_categories(): array
{
    return [
        'agreement' => 'Vereinbarung', 'hint' => 'Hinweis', 'defect' => 'Mangel',
        'open_task' => 'Offene Aufgabe', 'follow_up' => 'Nachreichung',
        'payment' => 'Zahlungsangelegenheit', 'other' => 'Sonstiger Punkt',
    ];
}

function attachment_categories(): array
{
    return [
        'misc_photo' => 'Sonstiges Foto', 'power_of_attorney' => 'Vollmacht',
        'rental_contract' => 'Mietvertrag', 'purchase_contract' => 'Kaufvertrag',
        'key_receipt' => 'Schlüsselbeleg', 'invoice' => 'Rechnung',
        'damage_proof' => 'Schadennachweis', 'other' => 'Sonstiges Dokument',
    ];
}

/** Signaturrollen je Protokolltyp */
function signature_roles(string $type): array
{
    [$outRole, $inRole, $outLabel, $inLabel] = party_roles($type);
    return [
        $outRole => $outLabel, $inRole => $inLabel,
        'management' => 'Verwaltung', 'broker' => 'Makler',
        'witness' => 'Zeuge', 'other' => 'Sonstige Person',
    ];
}

/** Wizard-Schritte in Reihenfolge: key => Label */
function wizard_steps(): array
{
    return [
        'type'         => 'Art',
        'object'       => 'Objekt',
        'participants' => 'Beteiligte',
        'deposit'      => 'Kaution',
        'ticket'       => 'Intern',
        'meters'       => 'Zähler',
        'rooms'        => 'Räume',
        'keys'         => 'Schlüssel',
        'items'        => 'Gegenstände',
        'notes'        => 'Bemerkungen',
        'attachments'  => 'Anhänge',
        'summary'      => 'Prüfung',
        'signatures'   => 'Unterschrift',
    ];
}

/**
 * Für den angemeldeten Benutzer sichtbare Wizard-Schritte. Gehilfen sehen
 * den internen Schritt nicht.
 */
function visible_wizard_steps(): array
{
    $steps = wizard_steps();
    if (\App\Core\Auth::isHelper()) {
        unset($steps['type'], $steps['ticket']);
    }
    return $steps;
}

/** Benutzerrollen der Anwendung: key => Bezeichnung */
function user_roles(): array
{
    return [
        'admin'     => 'Administrator',
        'employee'  => 'Mitarbeiter',
        'caretaker' => 'Objektbetreuer',
        'readonly'  => 'Nur Lesen',
        'helper'    => 'Gehilfe (externer Zugang)',
    ];
}

function user_role_label(?string $role): string
{
    return user_roles()[$role ?? ''] ?? 'Unbekannt';
}

/** Arten von Gehilfenzugängen: key => Bezeichnung */
function helper_types(): array
{
    return [
        'tenant' => 'Mieter',
        'owner'  => 'Eigentümer',
        'helper' => 'Beauftragter',
    ];
}

function helper_type_label(?string $type): string
{
    return helper_types()[$type ?? ''] ?? 'Gehilfe';
}

/** Rückfrage vor dem endgültigen Abschluss durch einen Gehilfen. */
function helper_completion_confirm_text(): string
{
    return 'Sind Sie sicher, dass Sie mit der Übergabe komplett fertig sind? '
        . 'Das Protokoll wird unwiderruflich geschlossen und festgeschrieben. '
        . 'Sie erhalten sofort eine Durchschrift per E-Mail und können das PDF hier herunterladen. '
        . 'Danach sind keine Änderungen mehr möglich.';
}

/**
 * Tatsächlich abgeschlossen: Abschluss wurde vollzogen und nicht storniert.
 * Ein vor dem Abschluss archiviertes oder ein storniertes Protokoll ist zwar
 * gesperrt, aber kein wirksames Übergabeprotokoll.
 */
function protocol_is_finalized(array $protocol): bool
{
    return !empty($protocol['completed_at']) && ($protocol['status'] ?? '') !== 'cancelled';
}

/**
 * Einheitliche Standardtexte für E-Mails. Werden von den Einstellungen
 * überschrieben und dienen als Vorbelegung in der Administration sowie als
 * Fallback im Code (identisch zu den Inserts der Migrationen).
 */
function mail_text_defaults(): array
{
    return [
        'email.default_subject'    => 'Übergabeprotokoll {{PROTOCOL_NUMBER}}, {{OBJECT_ADDRESS}}',
        'email.helper_subject'     => 'Ihr Zugang zum Übergabeprotokoll {{PROTOCOL_NUMBER}}',
        'email.helper_intro'       => 'Sie führen die Übergabe des Objektes {{OBJECT_ADDRESS}} eigenständig durch. Über den folgenden Zugang können Sie das Übergabeprotokoll digital ausfüllen, unterschreiben und abschließen.',
        'email.helper_privacy'     => 'Hinweis zum Datenschutz: Ihre Angaben werden ausschließlich zur Durchführung und Dokumentation der Übergabe verarbeitet und für die Dauer der gesetzlichen Aufbewahrungsfristen gespeichert. Verantwortlich ist die Hausverwaltung Müller GmbH. Ihr Zugang wird nach Abschluss der Übergabe zeitlich begrenzt.',
        'email.completion_subject' => 'Übergabeprotokoll {{PROTOCOL_NUMBER}}, {{OBJECT_ADDRESS}}',
        'email.completion_body'    => "Guten Tag,\n\nanbei erhalten Sie das abgeschlossene Übergabeprotokoll zum Objekt {{OBJECT_ADDRESS}} vom {{HANDOVER_DATE}} als PDF.\n\nMit freundlichen Grüßen\n\nHausverwaltung Müller GmbH",
    ];
}

/**
 * Text einer E-Mail-Einstellung mit einheitlichem Fallback. Bei $emptyAllowed
 * gilt ein bewusst leer gespeicherter Wert als "kein Text" (z. B. optionaler
 * Datenschutzhinweis), sonst greift bei leerem Wert der Standardtext.
 */
function mail_text(string $key, bool $emptyAllowed = false): string
{
    if ($emptyAllowed) {
        $row = \App\Core\Database::fetch('SELECT setting_value FROM settings WHERE setting_key = ?', [$key]);
        return $row === null ? (mail_text_defaults()[$key] ?? '') : (string) ($row['setting_value'] ?? '');
    }
    $value = \App\Core\Config::setting($key);
    return ($value !== null && trim($value) !== '') ? $value : (mail_text_defaults()[$key] ?? '');
}

/** Kontaktzeile der Hausverwaltung aus den Einstellungen (Telefon, E-Mail), leer wenn nichts gepflegt. */
function company_contact_line(): string
{
    $parts = [];
    $phone = trim((string) \App\Core\Config::setting('company.phone', ''));
    $mail = trim((string) \App\Core\Config::setting('company.email', ''));
    if ($phone !== '') {
        $parts[] = 'Telefon ' . $phone;
    }
    if ($mail !== '') {
        $parts[] = 'E-Mail ' . $mail;
    }
    return implode(', ', $parts);
}

/** Protokollfelder, die Gehilfen nicht verändern dürfen (von der Verwaltung vorbereitet oder intern). */
function helper_locked_protocol_fields(): array
{
    return [
        'protocol_type', 'branch_id', 'case_number', 'internal_contact', 'internal_note',
        'internal_object_number', 'management_number', 'rental_contract_number',
    ];
}

/**
 * Abschlussprüfung: Hinweise (keine Pflichtfelder!) für die Zusammenfassung
 * und den Abschluss-Dialog. Erwartet das Ergebnis von ProtocolRepository::loadFull().
 */
function completion_hints(array $full): array
{
    $hints = [];
    if (protocol_address($full['protocol']) === '') {
        $hints[] = 'Für dieses Protokoll wurde keine Objektadresse angegeben.';
    }
    if ($full['participants'] === []) {
        $hints[] = 'Es wurden keine beteiligten Personen erfasst.';
    }
    if ($full['meters'] === []) {
        $hints[] = 'Es wurden keine Zählerstände erfasst.';
    }
    if ($full['rooms'] === []) {
        $hints[] = 'Es wurden keine Räume erfasst.';
    }
    if ($full['keys'] === []) {
        $hints[] = 'Es wurden keine Schlüssel erfasst.';
    }
    if ($full['signatures'] === []) {
        $hints[] = 'Es liegt keine Unterschrift vor.';
    }
    return $hints;
}

/** Deutsche Beschriftungen für Audit-Aktionen (Änderungshistorie). */
function audit_action_label(string $action): string
{
    return [
        'protocol_created'   => 'Protokoll erstellt',
        'protocol_opened'    => 'Protokoll geöffnet',
        'fields_changed'     => 'Felder geändert',
        'protocol_completed' => 'Protokoll abgeschlossen',
        'protocol_cancelled' => 'Protokoll storniert',
        'protocol_archived'  => 'Protokoll archiviert',
        'protocol_unarchived'=> 'Aus dem Archiv zurückgeholt',
        'protocol_duplicated'=> 'Protokoll dupliziert',
        'version_created'    => 'Neue Version erstellt',
        'pdf_generated'      => 'PDF erzeugt',
        'file_uploaded'      => 'Datei hochgeladen',
        'file_deleted'       => 'Datei gelöscht',
        'signature_created'  => 'Unterschrift erfasst',
        'signature_deleted'  => 'Unterschrift gelöscht',
        'helper_created'          => 'Gehilfenzugang angelegt',
        'helper_access_granted'   => 'Gehilfe für Protokoll freigeschaltet',
        'helper_access_revoked'   => 'Zugang des Gehilfen entzogen',
        'helper_password_reset'   => 'Passwort des Gehilfen neu gesetzt',
        'helper_access_notice'    => 'Gehilfe über weitere Freischaltung informiert',
        'helper_access_expiry'    => 'Gültigkeitsende des Gehilfenzugangs gesetzt',
        'staff_notified'          => 'Hausverwaltung über Abschluss benachrichtigt',
        'password_changed'        => 'Eigenes Passwort geändert',
        'completion_dispatch_failed' => 'Automatischer Versand nach Abschluss fehlgeschlagen',
        'email_sent'         => 'E-Mail versendet',
        'email_failed'       => 'E-Mail-Versand fehlgeschlagen',
        'participant_added'  => 'Beteiligter hinzugefügt',
        'participant_updated'=> 'Beteiligter geändert',
        'participant_deleted'=> 'Beteiligter entfernt',
        'room_added'         => 'Raum hinzugefügt',
        'room_updated'       => 'Raum geändert',
        'room_deleted'       => 'Raum entfernt',
        'defect_added'       => 'Mangel hinzugefügt',
        'defect_updated'     => 'Mangel geändert',
        'defect_deleted'     => 'Mangel entfernt',
        'meter_added'        => 'Zähler hinzugefügt',
        'meter_updated'      => 'Zähler geändert',
        'meter_deleted'      => 'Zähler entfernt',
        'key_added'          => 'Schlüssel hinzugefügt',
        'key_updated'        => 'Schlüssel geändert',
        'key_deleted'        => 'Schlüssel entfernt',
        'item_added'         => 'Gegenstand hinzugefügt',
        'item_updated'       => 'Gegenstand geändert',
        'item_deleted'       => 'Gegenstand entfernt',
        'note_added'         => 'Bemerkung hinzugefügt',
        'note_updated'       => 'Bemerkung geändert',
        'note_deleted'       => 'Bemerkung entfernt',
        'bank_added'         => 'Kautionsdaten erfasst',
        'bank_updated'       => 'Kautionsdaten geändert',
        'bank_deleted'       => 'Kautionsdaten entfernt',
    ][$action] ?? $action;
}

/**
 * Kleines Footer-Feature: "Wussten Sie schon? Heute ist ..."
 * Bekannte Welt- und Aktionstage je Kalendertag plus bewegliche Tage
 * (Ostern-basiert). Gibt es für den Tag keinen Eintrag, wird ein neutraler
 * Kalenderfakt angezeigt, damit immer etwas erscheint.
 */
function special_day_note(): string
{
    $md = date('m-d');

    // Bewegliche Tage (Osterrechnung, Muttertag, Advent)
    if (function_exists('easter_days')) {
        $year = (int) date('Y');
        $easter = strtotime("$year-03-21 + " . easter_days($year) . ' days');
        $movable = [
            date('m-d', strtotime('-47 days', $easter)) => 'Rosenmontag',
            date('m-d', strtotime('-46 days', $easter)) => 'Aschermittwoch',
            date('m-d', strtotime('-2 days', $easter))  => 'Karfreitag',
            date('m-d', $easter)                         => 'Ostersonntag',
            date('m-d', strtotime('+1 day', $easter))   => 'Ostermontag',
            date('m-d', strtotime('+39 days', $easter)) => 'Christi Himmelfahrt',
            date('m-d', strtotime('+49 days', $easter)) => 'Pfingstsonntag',
            date('m-d', strtotime('second sunday of may ' . $year)) => 'Muttertag',
        ];
        if (isset($movable[$md])) {
            return 'Wussten Sie schon? Heute ist ' . $movable[$md] . '.';
        }
    }

    $days = [
        '01-01' => 'Neujahr',
        '01-21' => 'der Weltknuddeltag',
        '01-27' => 'der Tag des Gedenkens an die Opfer des Nationalsozialismus',
        '02-02' => 'der Murmeltiertag',
        '02-04' => 'der Weltkrebstag',
        '02-11' => 'der Europäische Tag des Notrufs 112',
        '02-14' => 'Valentinstag',
        '03-03' => 'der Welttag des Artenschutzes',
        '03-08' => 'der Internationale Frauentag',
        '03-15' => 'der Weltverbrauchertag',
        '03-20' => 'der Weltglückstag',
        '03-21' => 'der Internationale Tag des Waldes',
        '03-22' => 'der Weltwassertag',
        '04-07' => 'der Weltgesundheitstag',
        '04-22' => 'der Tag der Erde',
        '04-23' => 'der Welttag des Buches',
        '04-26' => 'der Welttag des geistigen Eigentums',
        '04-28' => 'der Welttag für Sicherheit und Gesundheit am Arbeitsplatz',
        '05-01' => 'der Tag der Arbeit',
        '05-03' => 'der Internationale Tag der Pressefreiheit',
        '05-04' => 'der Star-Wars-Tag (May the 4th)',
        '05-08' => 'der Weltrotkreuztag',
        '05-15' => 'der Internationale Tag der Familie',
        '05-20' => 'der Weltbienentag',
        '05-23' => 'der Tag des Grundgesetzes',
        '06-01' => 'der Internationale Kindertag',
        '06-05' => 'der Weltumwelttag',
        '06-08' => 'der Welttag der Ozeane',
        '06-14' => 'der Weltblutspendetag',
        '06-21' => 'der Internationale Tag des Yoga',
        '07-07' => 'der Tag der Schokolade',
        '07-17' => 'der Welt-Emoji-Tag',
        '07-20' => 'der Jahrestag der ersten Mondlandung (1969)',
        '07-30' => 'der Internationale Tag der Freundschaft',
        '08-08' => 'der Internationale Tag der Katze',
        '08-12' => 'der Internationale Tag der Jugend',
        '08-13' => 'der Internationale Linkshändertag',
        '08-19' => 'der Welttag der humanitären Hilfe',
        '08-26' => 'der Tag des Hundes (International Dog Day)',
        '08-29' => 'der Internationale Tag gegen Nuklearversuche',
        '09-13' => 'der Tag des positiven Denkens',
        '09-19' => 'der Sprich-wie-ein-Pirat-Tag',
        '09-21' => 'der Internationale Tag des Friedens',
        '09-22' => 'der Autofreie Tag',
        '09-27' => 'der Welttourismustag',
        '09-29' => 'der Weltherztag',
        '10-01' => 'der Internationale Tag des Kaffees',
        '10-03' => 'der Tag der Deutschen Einheit',
        '10-04' => 'der Welttierschutztag',
        '10-05' => 'der Weltlehrertag',
        '10-10' => 'der Welthundetag',
        '10-16' => 'der Welternährungstag',
        '10-31' => 'der Weltspartag (und Halloween)',
        '11-09' => 'der Jahrestag des Mauerfalls (1989)',
        '11-11' => 'der Beginn der Karnevalssession (11.11., 11:11 Uhr)',
        '11-13' => 'der Welttag der Freundlichkeit',
        '11-19' => 'der Weltmännertag',
        '11-21' => 'der Welttag des Fernsehens',
        '12-04' => 'der Tag der Barbara (Barbarazweige)',
        '12-05' => 'der Internationale Tag des Ehrenamtes',
        '12-06' => 'Nikolaus',
        '12-10' => 'der Tag der Menschenrechte',
        '12-24' => 'Heiligabend',
        '12-25' => 'der erste Weihnachtsfeiertag',
        '12-26' => 'der zweite Weihnachtsfeiertag',
        '12-31' => 'Silvester',
    ];

    if (isset($days[$md])) {
        return 'Wussten Sie schon? Heute ist ' . $days[$md] . '.';
    }
    // Neutraler Kalenderfakt als Ersatz, damit täglich etwas angezeigt wird
    return 'Wussten Sie schon? Heute ist der ' . (date('z') + 1) . '. Tag des Jahres, KW ' . date('W') . '.';
}

/** Bestätigungstext über den Unterschriften (administrativ änderbar). */
function signature_consent_text(): string
{
    return (string) \App\Core\Config::setting(
        'pdf.signature_consent',
        'Mit ihrer Unterschrift bestätigen die Unterzeichnenden die Richtigkeit und Vollständigkeit der in diesem Protokoll festgehaltenen Angaben. Sie erklären sich zugleich damit einverstanden, dass dieses Protokoll einschließlich der zugehörigen Fotos und Unterlagen elektronisch verarbeitet und in digitaler Form für die Dauer der gesetzlichen Aufbewahrungs- und Verjährungsfristen gespeichert wird.'
    );
}

function status_badge(string $status): string
{
    $labels = protocol_statuses();
    return '<span class="badge badge-' . e($status) . '">' . e($labels[$status] ?? $status) . '</span>';
}

/** Objektadresse einzeilig */
function protocol_address(array $p): string
{
    $line1 = trim(($p['street'] ?? '') . ' ' . ($p['house_number'] ?? '') . ($p['house_suffix'] ?? ''));
    $line2 = trim(($p['postal_code'] ?? '') . ' ' . ($p['city'] ?? ''));
    return trim($line1 . ($line1 && $line2 ? ', ' : '') . $line2);
}

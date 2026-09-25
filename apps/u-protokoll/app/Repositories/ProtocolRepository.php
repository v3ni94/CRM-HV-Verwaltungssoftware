<?php

declare(strict_types=1);

namespace App\Repositories;

use App\Core\Audit;
use App\Core\Auth;
use App\Core\Database;

/**
 * Zugriff auf Protokolle und alle Teilentitäten.
 * Feld-Whitelists verhindern Massenzuweisung beliebiger Spalten.
 */
final class ProtocolRepository
{
    /** Editierbare Protokollfelder (Wizard/Autosave). */
    public const PROTOCOL_FIELDS = [
        'protocol_type', 'ticket_number', 'case_number', 'branch_id',
        'street', 'house_number', 'house_suffix', 'postal_code', 'city',
        'object_label', 'building', 'floor', 'unit_number', 'unit_label', 'unit_position',
        'internal_object_number', 'rental_contract_number', 'management_number', 'reference_number',
        'handover_date', 'handover_start', 'handover_end', 'handover_location',
        'hide_time_information', 'internal_contact', 'internal_note', 'general_note', 'current_step',
    ];

    /** Teilentitäten: Tabelle und erlaubte Felder. */
    public const ENTITIES = [
        'participant' => ['table' => 'protocol_participants', 'fields' => ['role', 'salutation', 'first_name', 'last_name', 'company', 'street', 'house_number', 'postal_code', 'city', 'email', 'phone', 'mobile', 'comment', 'sort_order']],
        'bank'        => ['table' => 'protocol_bank_details', 'fields' => ['participant_id', 'deposit_amount', 'account_holder', 'iban', 'bic', 'bank_name', 'alt_payee', 'comment', 'iban_by_tenant', 'iban_verified', 'deposit_separate', 'no_bank_given']],
        'meter'       => ['table' => 'protocol_meters', 'fields' => ['meter_type', 'custom_type', 'meter_number', 'meter_value', 'unit', 'location', 'reading_date', 'reading_time', 'comment', 'sort_order']],
        'room'        => ['table' => 'protocol_rooms', 'fields' => ['room_type', 'room_name', 'condition_status', 'comment', 'sort_order']],
        'defect'      => ['table' => 'protocol_defects', 'fields' => ['room_id', 'category', 'title', 'description', 'location', 'priority', 'responsibility', 'defect_status', 'comment', 'sort_order']],
        'key'         => ['table' => 'protocol_keys', 'fields' => ['key_type', 'custom_name', 'quantity', 'key_number', 'status', 'comment', 'sort_order']],
        'item'        => ['table' => 'protocol_items', 'fields' => ['item_type', 'name', 'quantity', 'condition_status', 'comment', 'sort_order']],
        'note'        => ['table' => 'protocol_notes', 'fields' => ['category', 'text', 'responsible_party', 'due_date', 'status', 'comment', 'is_internal', 'sort_order']],
    ];

    public static function find(int $id): ?array
    {
        return Database::fetch('SELECT * FROM protocols WHERE id = ?', [$id]);
    }

    /**
     * Lädt ein Protokoll oder bricht mit 404 ab. Zusätzlich wird zentral
     * geprüft, ob der angemeldete Benutzer auf dieses Protokoll zugreifen
     * darf (Gehilfen nur auf zugewiesene Protokolle).
     */
    public static function findOrFail(int $id): array
    {
        // Zuerst die Berechtigung: Gehilfen erhalten für fremde wie für nicht
        // existierende Protokolle dieselbe Antwort (kein Aufzählen von IDs)
        Auth::requireProtocolAccess($id);
        $protocol = self::find($id);
        if ($protocol === null) {
            \App\Core\Response::html('<p>Protokoll nicht gefunden.</p>', 404);
        }
        return $protocol;
    }

    /** Abgeschlossene/archivierte/stornierte Protokolle sind schreibgeschützt. */
    public static function isLocked(array $protocol): bool
    {
        return in_array($protocol['status'], ['completed', 'sent', 'archived', 'cancelled'], true);
    }

    public static function create(string $type): array
    {
        $id = Database::insert('protocols', [
            'protocol_type' => in_array($type, ['rental', 'sale', 'general'], true) ? $type : 'rental',
            'status'        => 'draft',
            'current_step'  => 'object',
            'created_by'    => Auth::id(),
            'updated_by'    => Auth::id(),
            'branch_id'     => Auth::user()['branch_id'] ?? null,
        ]);
        // Nummer vergeben; bei seltener Kollision (gleichzeitige Anlage) neu versuchen
        for ($attempt = 0; $attempt < 5; $attempt++) {
            try {
                Database::update('protocols', ['protocol_number' => self::nextProtocolNumber()], 'id = ?', [$id]);
                break;
            } catch (\PDOException $e) {
                if ($attempt === 4 || !str_contains($e->getMessage(), 'Duplicate')) {
                    throw $e;
                }
            }
        }
        Audit::log('protocol_created', 'protocols', $id, $id, null, $type);
        return self::find($id);
    }

    /**
     * Protokollnummer im Format UP-JJJJMMTT-NNN, laufende Nummer je Tag
     * (UP-20260829-001, UP-20260829-002, ...).
     */
    public static function nextProtocolNumber(): string
    {
        $prefix = 'UP-' . date('Ymd') . '-';
        $row = Database::fetch(
            'SELECT MAX(CAST(SUBSTRING(protocol_number, ?) AS UNSIGNED)) AS n FROM protocols WHERE protocol_number LIKE ?',
            [strlen($prefix) + 1, $prefix . '%']
        );
        $next = (int) ($row['n'] ?? 0) + 1;
        return $prefix . str_pad((string) $next, 3, '0', STR_PAD_LEFT);
    }

    /** Aktualisiert Protokollfelder (nur Whitelist) und pflegt updated_by. */
    public static function updateFields(int $id, array $data): void
    {
        $clean = array_intersect_key($data, array_flip(self::PROTOCOL_FIELDS));
        // Gehilfen dürfen interne und von der Verwaltung vorbereitete Angaben nicht verändern
        if (Auth::isHelper()) {
            $clean = array_diff_key($clean, array_flip(helper_locked_protocol_fields()));
        }
        if ($clean === []) {
            return;
        }
        foreach ($clean as $k => $v) {
            if ($v === '') {
                $clean[$k] = null;
            }
        }
        $clean['updated_by'] = Auth::id();
        Database::update('protocols', $clean, 'id = ?', [$id]);
        // Entwurf wird mit erster inhaltlicher Änderung zu "In Bearbeitung"
        Database::execute("UPDATE protocols SET status = 'in_progress' WHERE id = ? AND status = 'draft'", [$id]);
    }

    /** Speichert (insert/update) eine Teilentität; liefert die Datensatz-ID. */
    public static function saveEntity(int $protocolId, string $entity, array $data, ?int $recordId = null): int
    {
        $def = self::ENTITIES[$entity] ?? null;
        if ($def === null) {
            throw new \InvalidArgumentException('Unbekannte Entität.');
        }
        $clean = array_intersect_key($data, array_flip($def['fields']));
        foreach ($clean as $k => $v) {
            if ($v === '') {
                $clean[$k] = null;
            }
        }
        // Gehilfen können weder die Kennzeichnung "intern" noch das Prüfkennzeichen der IBAN setzen
        if (Auth::isHelper()) {
            unset($clean['is_internal'], $clean['iban_verified']);
        }

        if ($recordId) {
            $existing = Database::fetch("SELECT * FROM `{$def['table']}` WHERE id = ? AND protocol_id = ?", [$recordId, $protocolId]);
            if ($existing === null) {
                throw new RecordNotFoundException('Datensatz nicht gefunden.');
            }
            // Interne Datensätze sind für Gehilfen unsichtbar und damit auch nicht änderbar
            if (Auth::isHelper() && !empty($existing['is_internal'])) {
                throw new RecordNotFoundException('Datensatz nicht gefunden.');
            }
            if ($clean !== []) {
                Database::update($def['table'], $clean, 'id = ?', [$recordId]);
            }
            Audit::log($entity . '_updated', $def['table'], $recordId, $protocolId);
            return $recordId;
        }

        $clean['protocol_id'] = $protocolId;
        $id = Database::insert($def['table'], $clean);
        Audit::log($entity . '_added', $def['table'], $id, $protocolId);
        return $id;
    }

    public static function deleteEntity(int $protocolId, string $entity, int $recordId): void
    {
        $def = self::ENTITIES[$entity] ?? null;
        if ($def === null) {
            throw new \InvalidArgumentException('Unbekannte Entität.');
        }
        if (Auth::isHelper() && in_array('is_internal', $def['fields'], true)) {
            $existing = Database::fetch("SELECT is_internal FROM `{$def['table']}` WHERE id = ? AND protocol_id = ?", [$recordId, $protocolId]);
            if ($existing !== null && !empty($existing['is_internal'])) {
                throw new RecordNotFoundException('Datensatz nicht gefunden.');
            }
        }
        Database::execute("DELETE FROM `{$def['table']}` WHERE id = ? AND protocol_id = ?", [$recordId, $protocolId]);
        Audit::log($entity . '_deleted', $def['table'], $recordId, $protocolId);
    }

    /** Alle Teildaten eines Protokolls für Zusammenfassung/PDF. */
    public static function loadFull(int $id): array
    {
        $protocol = self::findOrFail($id);
        $full = self::loadRaw($id, $protocol);

        // Gehilfen sehen keine internen Angaben der Hausverwaltung
        if (Auth::isHelper()) {
            $protocol['internal_note'] = null;
            $protocol['internal_contact'] = null;
            $full['protocol'] = $protocol;
            $full['notes'] = array_values(array_filter($full['notes'], static fn(array $n): bool => empty($n['is_internal'])));
            $full['files'] = array_values(array_filter($full['files'], static fn(array $f): bool => empty($f['is_internal'])));
            $full['emails'] = [];
        }
        return $full;
    }

    /**
     * Vollständige Daten ohne Rollenfilter. Wird für die PDF-Erzeugung beim
     * Abschluss genutzt, damit die gespeicherte Version unabhängig davon
     * identisch ist, wer den Abschluss ausgelöst hat.
     */
    public static function loadUnfiltered(int $id): array
    {
        return self::loadRaw($id, self::findOrFail($id));
    }

    /** Lädt alle Teildaten ohne Rollenfilter. */
    private static function loadRaw(int $id, array $protocol): array
    {
        return [
            'protocol'     => $protocol,
            'participants' => Database::fetchAll('SELECT * FROM protocol_participants WHERE protocol_id = ? ORDER BY sort_order, id', [$id]),
            'bank'         => Database::fetch('SELECT * FROM protocol_bank_details WHERE protocol_id = ? ORDER BY id LIMIT 1', [$id]),
            'meters'       => Database::fetchAll('SELECT * FROM protocol_meters WHERE protocol_id = ? ORDER BY sort_order, id', [$id]),
            'rooms'        => Database::fetchAll('SELECT * FROM protocol_rooms WHERE protocol_id = ? ORDER BY sort_order, id', [$id]),
            'defects'      => Database::fetchAll('SELECT * FROM protocol_defects WHERE protocol_id = ? ORDER BY sort_order, id', [$id]),
            'keys'         => Database::fetchAll('SELECT * FROM protocol_keys WHERE protocol_id = ? ORDER BY sort_order, id', [$id]),
            'items'        => Database::fetchAll('SELECT * FROM protocol_items WHERE protocol_id = ? ORDER BY sort_order, id', [$id]),
            'notes'        => Database::fetchAll('SELECT * FROM protocol_notes WHERE protocol_id = ? ORDER BY sort_order, id', [$id]),
            'files'        => Database::fetchAll('SELECT * FROM protocol_files WHERE protocol_id = ? ORDER BY sort_order, id', [$id]),
            'signatures'   => Database::fetchAll('SELECT s.*, f.storage_path AS sig_path FROM protocol_signatures s LEFT JOIN protocol_files f ON f.id = s.signature_file_id WHERE s.protocol_id = ? ORDER BY s.id', [$id]),
            'versions'     => Database::fetchAll('SELECT * FROM protocol_versions WHERE protocol_id = ? ORDER BY version_number', [$id]),
            'emails'       => Database::fetchAll('SELECT * FROM protocol_emails WHERE protocol_id = ? ORDER BY sent_at DESC', [$id]),
        ];
    }

    /**
     * Dupliziert ein Protokoll. Übernommen werden je nach Auswahl Objekt,
     * Räume, Zählertypen und Schlüsselarten – nie Zählerstände, Mängel,
     * Signaturen oder personenbezogene Daten.
     */
    public static function duplicate(array $source, array $options): array
    {
        $new = self::create($source['protocol_type']);
        $newId = (int) $new['id'];

        if (!empty($options['object'])) {
            $fields = ['street', 'house_number', 'house_suffix', 'postal_code', 'city', 'object_label',
                'building', 'floor', 'unit_number', 'unit_label', 'unit_position', 'internal_object_number',
                'management_number', 'branch_id'];
            $data = array_intersect_key($source, array_flip($fields));
            self::updateFields($newId, $data);
        }
        if (!empty($options['rooms'])) {
            foreach (Database::fetchAll('SELECT room_type, room_name, sort_order FROM protocol_rooms WHERE protocol_id = ? ORDER BY sort_order, id', [$source['id']]) as $room) {
                self::saveEntity($newId, 'room', $room);
            }
        }
        if (!empty($options['meters'])) {
            foreach (Database::fetchAll('SELECT meter_type, custom_type, meter_number, unit, location, sort_order FROM protocol_meters WHERE protocol_id = ? ORDER BY sort_order, id', [$source['id']]) as $meter) {
                self::saveEntity($newId, 'meter', $meter); // ohne meter_value / Ablesedaten
            }
        }
        if (!empty($options['keys'])) {
            foreach (Database::fetchAll('SELECT key_type, custom_name, key_number, sort_order FROM protocol_keys WHERE protocol_id = ? ORDER BY sort_order, id', [$source['id']]) as $key) {
                self::saveEntity($newId, 'key', $key); // ohne Anzahl/Status
            }
        }

        Audit::log('protocol_duplicated', 'protocols', $newId, $newId, $source['id']);
        return self::find($newId);
    }

    /**
     * Legt für ein abgeschlossenes Protokoll eine neue bearbeitbare Version an.
     * Alle Teildaten werden kopiert; das Original bleibt unverändert erhalten.
     */
    public static function createNewVersion(array $source, string $reason): array
    {
        $pdo = Database::get();
        $pdo->beginTransaction();
        try {
            // Nächste freie Versionsnummer über alle Versionen dieser Protokollnummer;
            // bei seltener Kollision (gleichzeitige Anlage) mit neuer Nummer wiederholen
            $newId = 0;
            for ($attempt = 0; $attempt < 5; $attempt++) {
                $maxVersion = (int) (Database::fetch(
                    'SELECT MAX(version) AS v FROM protocols WHERE protocol_number = ?',
                    [$source['protocol_number']]
                )['v'] ?? $source['version']);
                try {
                    $newId = Database::insert('protocols', array_merge(
                        array_intersect_key($source, array_flip(self::PROTOCOL_FIELDS)),
                        [
                            'protocol_number'    => $source['protocol_number'],
                            'version'            => $maxVersion + 1,
                            'parent_protocol_id' => (int) $source['id'],
                            'status'             => 'rework',
                            'change_reason'      => mb_substr($reason, 0, 255),
                            'created_by'         => Auth::id(),
                            'updated_by'         => Auth::id(),
                        ]
                    ));
                    break;
                } catch (\PDOException $e) {
                    if ($attempt === 4 || !str_contains($e->getMessage(), 'Duplicate')) {
                        throw $e;
                    }
                }
            }

            $copyTables = ['protocol_participants', 'protocol_bank_details', 'protocol_meters', 'protocol_rooms',
                'protocol_keys', 'protocol_items', 'protocol_notes'];
            $maps = ['protocol_rooms' => [], 'protocol_participants' => [], 'protocol_meters' => [], 'protocol_items' => [], 'protocol_notes' => []];
            foreach ($copyTables as $table) {
                foreach (Database::fetchAll("SELECT * FROM `$table` WHERE protocol_id = ?", [$source['id']]) as $row) {
                    $oldRowId = (int) $row['id'];
                    unset($row['id']);
                    $row['protocol_id'] = $newId;
                    if ($table === 'protocol_bank_details') {
                        // Verknüpfung auf den kopierten Beteiligten umbiegen
                        $row['participant_id'] = $row['participant_id'] !== null
                            ? ($maps['protocol_participants'][(int) $row['participant_id']] ?? null)
                            : null;
                    }
                    $newRowId = Database::insert($table, $row);
                    if (isset($maps[$table])) {
                        $maps[$table][$oldRowId] = $newRowId;
                    }
                }
            }
            $roomMap = $maps['protocol_rooms'];
            $participantMap = $maps['protocol_participants'];
            // Mängel mit neuer Raumzuordnung kopieren
            $defectMap = [];
            foreach (Database::fetchAll('SELECT * FROM protocol_defects WHERE protocol_id = ?', [$source['id']]) as $defect) {
                $oldDefectId = (int) $defect['id'];
                unset($defect['id']);
                $defect['protocol_id'] = $newId;
                $defect['room_id'] = $defect['room_id'] !== null ? ($roomMap[(int) $defect['room_id']] ?? null) : null;
                $defectMap[$oldDefectId] = Database::insert('protocol_defects', $defect);
            }
            // Dateien: Metadaten kopieren und Zuordnungen auf die kopierten
            // Datensätze umbiegen; die physische Datei bleibt dieselbe (unveränderlich)
            $remap = fn($oldId, array $map): ?int => $oldId !== null ? ($map[(int) $oldId] ?? null) : null;
            foreach (Database::fetchAll("SELECT * FROM protocol_files WHERE protocol_id = ? AND file_category NOT IN ('signature','pdf')", [$source['id']]) as $file) {
                unset($file['id']);
                $file['protocol_id'] = $newId;
                $file['room_id'] = $remap($file['room_id'], $roomMap);
                $file['defect_id'] = $remap($file['defect_id'], $defectMap);
                $file['meter_id'] = $remap($file['meter_id'], $maps['protocol_meters']);
                $file['note_id'] = $remap($file['note_id'], $maps['protocol_notes']);
                $file['item_id'] = $remap($file['item_id'], $maps['protocol_items']);
                Database::insert('protocol_files', $file);
            }

            // Unterschriften mitkopieren: Signaturbild wird referenziert (nicht dupliziert),
            // die Zuordnung zeigt auf die kopierten Beteiligten
            foreach (Database::fetchAll('SELECT * FROM protocol_signatures WHERE protocol_id = ?', [$source['id']]) as $sig) {
                $newFileId = null;
                if ($sig['signature_file_id'] !== null) {
                    $sigFile = Database::fetch('SELECT * FROM protocol_files WHERE id = ?', [$sig['signature_file_id']]);
                    if ($sigFile !== null) {
                        unset($sigFile['id']);
                        $sigFile['protocol_id'] = $newId;
                        $sigFile['room_id'] = null;
                        $sigFile['defect_id'] = null;
                        $sigFile['meter_id'] = null;
                        $sigFile['note_id'] = null;
                        $sigFile['item_id'] = null;
                        $newFileId = Database::insert('protocol_files', $sigFile);
                    }
                }
                unset($sig['id']);
                $sig['protocol_id'] = $newId;
                $sig['participant_id'] = $sig['participant_id'] !== null
                    ? ($participantMap[(int) $sig['participant_id']] ?? null)
                    : null;
                $sig['signature_file_id'] = $newFileId;
                Database::insert('protocol_signatures', $sig);
            }

            $pdo->commit();
        } catch (\Throwable $e) {
            $pdo->rollBack();
            throw $e;
        }

        $new = self::find($newId);
        Audit::log('version_created', 'protocols', $newId, (int) $source['id'], $source['version'], $new['version']);
        return $new;
    }
}

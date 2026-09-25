<?php

declare(strict_types=1);

namespace App\Controllers;

use App\Core\Auth;
use App\Core\Database;
use App\Core\Request;
use App\Core\Response;
use App\Core\View;

/**
 * Dashboard: Kennzahlen, Protokollübersicht mit kombinierbaren Filtern,
 * Sortierung und CSV-Export.
 */
final class DashboardController
{
    private const SORTABLE = [
        'id' => 'p.id', 'status' => 'p.status', 'type' => 'p.protocol_type',
        'ticket' => 'p.ticket_number', 'city' => 'p.city', 'date' => 'p.handover_date',
        'created' => 'p.created_at', 'updated' => 'p.updated_at', 'completed' => 'p.completed_at',
    ];

    /** @return array{sql:string, params:array} */
    private function buildQuery(): array
    {
        $where = ['1=1'];
        $params = [];

        $map = [
            'id'      => ['p.id = ?', 'int'],
            'ticket'  => ["p.ticket_number LIKE ?", 'like'],
            'street'  => ['p.street LIKE ?', 'like'],
            'houseno' => ['p.house_number LIKE ?', 'like'],
            'zip'     => ['p.postal_code LIKE ?', 'like'],
            'city'    => ['p.city LIKE ?', 'like'],
            'type'    => ['p.protocol_type = ?', 'exact'],
            'status'  => ['p.status = ?', 'exact'],
            'user'    => ['(u.username LIKE ? OR u.last_name LIKE ?)', 'like2'],
            'name'    => ['EXISTS (SELECT 1 FROM protocol_participants pp WHERE pp.protocol_id = p.id AND (pp.last_name LIKE ? OR pp.first_name LIKE ? OR pp.company LIKE ?))', 'like3'],
            'email'   => ['EXISTS (SELECT 1 FROM protocol_participants pe WHERE pe.protocol_id = p.id AND pe.email LIKE ?)', 'like'],
        ];
        foreach ($map as $key => [$clause, $mode]) {
            $value = Request::get($key);
            if ($value === null || $value === '') {
                continue;
            }
            $where[] = $clause;
            match ($mode) {
                'int'   => $params[] = (int) $value,
                'exact' => $params[] = $value,
                'like'  => $params[] = "%$value%",
                'like2' => array_push($params, "%$value%", "%$value%"),
                'like3' => array_push($params, "%$value%", "%$value%", "%$value%"),
            };
        }
        // Archivierte standardmäßig ausblenden; sichtbar über "Archivierte anzeigen"
        // oder wenn gezielt nach dem Status Archiviert gefiltert wird
        if (Request::get('show_archived') !== '1' && Request::get('status') !== 'archived') {
            $where[] = "p.status != 'archived'";
        }
        if ($from = Request::get('date_from')) {
            $where[] = 'p.handover_date >= ?';
            $params[] = $from;
        }
        if ($to = Request::get('date_to')) {
            $where[] = 'p.handover_date <= ?';
            $params[] = $to;
        }
        // Freitextsuche über alle wesentlichen Felder (Suchleiste)
        if ($q = Request::get('q')) {
            $where[] = "(p.protocol_number LIKE ? OR p.ticket_number LIKE ? OR p.case_number LIKE ?
                OR p.street LIKE ? OR p.house_number LIKE ? OR p.postal_code LIKE ? OR p.city LIKE ?
                OR p.object_label LIKE ? OR p.unit_number LIKE ?
                OR EXISTS (SELECT 1 FROM protocol_participants pq WHERE pq.protocol_id = p.id
                    AND (pq.last_name LIKE ? OR pq.first_name LIKE ? OR pq.company LIKE ? OR pq.email LIKE ?)))";
            for ($i = 0; $i < 13; $i++) {
                $params[] = "%$q%";
            }
        }

        $sortKey = Request::get('sort', 'id');
        $sortCol = self::SORTABLE[$sortKey] ?? 'p.id';
        $dir = Request::get('dir') === 'asc' ? 'ASC' : 'DESC';

        $sql = 'FROM protocols p LEFT JOIN users u ON u.id = p.created_by WHERE ' . implode(' AND ', $where)
            . " ORDER BY $sortCol $dir";
        return ['sql' => $sql, 'params' => $params];
    }

    private function fetchRows(string $baseSql, array $params, ?int $limit, int $offset = 0): array
    {
        $select = "SELECT p.*, u.username AS creator,
            (SELECT GROUP_CONCAT(DISTINCT pp.last_name SEPARATOR ', ') FROM protocol_participants pp
                WHERE pp.protocol_id = p.id AND pp.role IN ('moving_out','seller','handing_over')) AS party_out,
            (SELECT GROUP_CONCAT(DISTINCT pp.last_name SEPARATOR ', ') FROM protocol_participants pp
                WHERE pp.protocol_id = p.id AND pp.role IN ('moving_in','buyer','taking_over')) AS party_in,
            (SELECT COUNT(*) FROM protocol_participants c1 WHERE c1.protocol_id = p.id) AS cnt_participants,
            (SELECT COUNT(*) FROM protocol_meters c2 WHERE c2.protocol_id = p.id) AS cnt_meters,
            (SELECT COUNT(*) FROM protocol_rooms c3 WHERE c3.protocol_id = p.id) AS cnt_rooms,
            (SELECT COUNT(*) FROM protocol_keys c4 WHERE c4.protocol_id = p.id) AS cnt_keys,
            (SELECT COUNT(*) FROM protocol_signatures c5 WHERE c5.protocol_id = p.id) AS cnt_signatures ";
        $sql = $select . $baseSql;
        if ($limit !== null) {
            $sql .= ' LIMIT ' . $limit . ' OFFSET ' . $offset;
        }
        return Database::fetchAll($sql, $params);
    }

    /**
     * Ampelfarbe je Datenstand: blau = archiviert, grün = abgeschlossen,
     * gelb = weitgehend erfasst aber offen, rot = kaum oder keine Daten.
     */
    public static function rowColor(array $r): string
    {
        if ($r['status'] === 'archived') {
            return 'blue';
        }
        if ($r['status'] === 'cancelled') {
            return 'gray';
        }
        if (in_array($r['status'], ['completed', 'sent'], true)) {
            return 'green';
        }
        $filled = (int) (protocol_address($r) !== '')
            + (int) ((int) $r['cnt_participants'] > 0)
            + (int) ((int) $r['cnt_meters'] > 0)
            + (int) ((int) $r['cnt_rooms'] > 0)
            + (int) ((int) $r['cnt_keys'] > 0)
            + (int) ((int) $r['cnt_signatures'] > 0);
        return $filled >= 3 ? 'yellow' : 'red';
    }

    public function index(): void
    {
        // Gehilfen sehen ausschließlich die ihnen zugewiesenen Protokolle
        if (Auth::isHelper()) {
            (new HelperController())->home();
            return;
        }
        $query = $this->buildQuery();
        $page = max(1, (int) (Request::get('page', '1')));
        $perPage = 25;

        $total = (int) (Database::fetch('SELECT COUNT(*) AS c ' . preg_replace('/ORDER BY.*$/', '', $query['sql']), $query['params'])['c'] ?? 0);
        $rows = $this->fetchRows($query['sql'], $query['params'], $perPage, ($page - 1) * $perPage);

        $stats = [
            'total'     => (int) (Database::fetch('SELECT COUNT(*) AS c FROM protocols')['c'] ?? 0),
            'drafts'    => (int) (Database::fetch("SELECT COUNT(*) AS c FROM protocols WHERE status IN ('draft','in_progress','rework','signature_pending')")['c'] ?? 0),
            'today'     => (int) (Database::fetch('SELECT COUNT(*) AS c FROM protocols WHERE DATE(created_at) = CURDATE()')['c'] ?? 0),
            'month_done'=> (int) (Database::fetch("SELECT COUNT(*) AS c FROM protocols WHERE status IN ('completed','sent') AND completed_at >= DATE_FORMAT(NOW(), '%Y-%m-01')")['c'] ?? 0),
            'unsent'    => (int) (Database::fetch("SELECT COUNT(*) AS c FROM protocols WHERE status = 'completed'")['c'] ?? 0),
        ];

        View::page('dashboard/index', [
            'title'   => 'Dashboard',
            'rows'    => $rows,
            'total'   => $total,
            'page'    => $page,
            'perPage' => $perPage,
            'stats'   => $stats,
        ]);
    }

    public function exportCsv(): void
    {
        Auth::requireStaff();
        $query = $this->buildQuery();
        $rows = $this->fetchRows($query['sql'], $query['params'], null);

        $out = fopen('php://temp', 'w+');
        // BOM für Excel
        fwrite($out, "\xEF\xBB\xBF");
        fputcsv($out, ['ID', 'Protokollnummer', 'Version', 'Status', 'Typ', 'Ticket', 'Straße', 'Hausnummer', 'PLZ', 'Ort', 'Einheit', 'Ausziehend/Übergebend', 'Einziehend/Übernehmend', 'Übergabedatum', 'Gestartet am', 'Abgeschlossen am', 'Zuletzt geändert', 'Bearbeiter'], ';');
        $types = protocol_types();
        $statuses = protocol_statuses();
        foreach ($rows as $r) {
            fputcsv($out, [
                $r['id'], $r['protocol_number'], $r['version'], $statuses[$r['status']] ?? $r['status'],
                $types[$r['protocol_type']] ?? $r['protocol_type'], $r['ticket_number'],
                $r['street'], trim(($r['house_number'] ?? '') . ($r['house_suffix'] ?? '')),
                $r['postal_code'], $r['city'], $r['unit_number'],
                $r['party_out'], $r['party_in'],
                fmt_date($r['handover_date']), fmt_datetime($r['created_at']),
                fmt_datetime($r['completed_at']), fmt_datetime($r['updated_at']), $r['creator'],
            ], ';');
        }
        rewind($out);
        Response::download((string) stream_get_contents($out), 'u-protokoll-uebersicht_' . date('Y-m-d') . '.csv', 'text/csv; charset=utf-8');
    }
}

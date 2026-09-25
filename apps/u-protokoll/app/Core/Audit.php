<?php

declare(strict_types=1);

namespace App\Core;

/**
 * Audit-Log. Wird ausschließlich serverseitig geschrieben,
 * für normale Mitarbeiter nicht änderbar (kein UPDATE/DELETE im Code).
 */
final class Audit
{
    public static function log(
        string $action,
        ?string $entity = null,
        ?int $entityId = null,
        ?int $protocolId = null,
        mixed $oldValue = null,
        mixed $newValue = null
    ): void {
        try {
            $user = Auth::check() ? Auth::user() : null;
            Database::insert('audit_log', [
                'user_id'     => $user['id'] ?? null,
                'username'    => $user['username'] ?? null,
                'action'      => $action,
                'entity'      => $entity,
                'entity_id'   => $entityId,
                'protocol_id' => $protocolId,
                'old_value'   => self::stringify($oldValue),
                'new_value'   => self::stringify($newValue),
                'ip_address'  => Request::ip(),
            ]);
        } catch (\Throwable $e) {
            Logger::error('Audit-Log fehlgeschlagen: ' . $e->getMessage());
        }
    }

    private static function stringify(mixed $value): ?string
    {
        if ($value === null) {
            return null;
        }
        return is_scalar($value) ? (string) $value : json_encode($value, JSON_UNESCAPED_UNICODE);
    }
}

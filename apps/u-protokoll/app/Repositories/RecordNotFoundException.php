<?php

declare(strict_types=1);

namespace App\Repositories;

/**
 * Fachlicher Fehler: Teildatensatz existiert nicht oder gehört nicht zum
 * Protokoll (bzw. ist für die Rolle unsichtbar). Wird von den Controllern
 * als 404 beantwortet; technische Fehler laufen weiter in den Fehlerhandler.
 */
final class RecordNotFoundException extends \RuntimeException
{
}

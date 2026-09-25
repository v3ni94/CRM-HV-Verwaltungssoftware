<?php
/**
 * Bootstrap: Autoloader, Konfiguration, Fehlerbehandlung, Session.
 */

declare(strict_types=1);

// PSR-4-ähnlicher Autoloader für den App-Namespace, Composer-Autoloader falls vorhanden
spl_autoload_register(function (string $class): void {
    if (str_starts_with($class, 'App\\')) {
        $path = BASE_PATH . '/app/' . str_replace('\\', '/', substr($class, 4)) . '.php';
        if (is_file($path)) {
            require $path;
        }
    }
});
if (is_file(BASE_PATH . '/vendor/autoload.php')) {
    require BASE_PATH . '/vendor/autoload.php';
}

require BASE_PATH . '/app/Core/helpers.php';

\App\Core\Env::load(BASE_PATH . '/.env');
\App\Core\Config::init();

// Fehler nie öffentlich anzeigen, nur loggen
error_reporting(E_ALL);
ini_set('display_errors', \App\Core\Config::get('app.debug') ? '1' : '0');
ini_set('log_errors', '1');
ini_set('error_log', BASE_PATH . '/storage/logs/php-error.log');
// Stacktraces ohne Funktionsargumente, damit nie Passwörter oder Tokens im Log landen
ini_set('zend.exception_ignore_args', '1');

set_exception_handler(function (\Throwable $e): void {
    \App\Core\Logger::error($e->getMessage(), ['file' => $e->getFile(), 'line' => $e->getLine(), 'trace' => $e->getTraceAsString()]);
    http_response_code(500);
    if (\App\Core\Config::get('app.debug')) {
        header('Content-Type: text/plain; charset=utf-8');
        echo $e;
    } elseif (\App\Core\Request::wantsJson()) {
        header('Content-Type: application/json');
        echo json_encode(['ok' => false, 'error' => 'Es ist ein technischer Fehler aufgetreten.']);
    } else {
        echo '<!doctype html><meta charset="utf-8"><title>Fehler</title><p style="font-family:sans-serif;margin:3rem">Es ist ein technischer Fehler aufgetreten. Bitte versuchen Sie es erneut.</p>';
    }
    exit;
});

// Sichere Session
session_name('uprotokoll');
session_set_cookie_params([
    'lifetime' => 0,
    'path'     => '/',
    'secure'   => (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off'),
    'httponly' => true,
    'samesite' => 'Lax',
]);
session_start();

date_default_timezone_set(\App\Core\Config::get('app.timezone', 'Europe/Berlin'));

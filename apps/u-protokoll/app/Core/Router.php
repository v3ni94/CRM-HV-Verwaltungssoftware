<?php

declare(strict_types=1);

namespace App\Core;

/**
 * Einfacher Router mit Platzhaltern ({id}). Routen mit $auth = true
 * erfordern eine aktive Anmeldung; POST-Routen erzwingen CSRF-Prüfung.
 */
final class Router
{
    /** @var array<int, array{method:string, pattern:string, handler:array, auth:bool}> */
    private array $routes = [];

    public function get(string $path, array $handler, bool $auth = true): void
    {
        $this->routes[] = ['method' => 'GET', 'pattern' => $path, 'handler' => $handler, 'auth' => $auth];
    }

    public function post(string $path, array $handler, bool $auth = true): void
    {
        $this->routes[] = ['method' => 'POST', 'pattern' => $path, 'handler' => $handler, 'auth' => $auth];
    }

    public function dispatch(): void
    {
        $method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
        $uri = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';
        $base = rtrim(dirname($_SERVER['SCRIPT_NAME'] ?? ''), '/');
        if ($base !== '' && str_starts_with($uri, $base)) {
            $uri = substr($uri, strlen($base)) ?: '/';
        }

        foreach ($this->routes as $route) {
            if ($route['method'] !== $method) {
                continue;
            }
            $regex = '#^' . preg_replace('#\{(\w+)\}#', '(?P<$1>[^/]+)', $route['pattern']) . '$#';
            if (!preg_match($regex, $uri, $m)) {
                continue;
            }
            $params = array_filter($m, 'is_string', ARRAY_FILTER_USE_KEY);

            if ($route['auth'] && (!Auth::check() || Auth::user() === null)) {
                if (Request::wantsJson()) {
                    Response::json(['ok' => false, 'error' => 'Sitzung abgelaufen. Bitte erneut anmelden.'], 401);
                }
                Response::redirect('/login');
            }
            if ($method === 'POST' && !Csrf::validate()) {
                if (Request::wantsJson()) {
                    Response::json(['ok' => false, 'error' => 'Sicherheitstoken ungültig. Bitte Seite neu laden.'], 419);
                }
                http_response_code(419);
                echo 'Sicherheitstoken ungültig. Bitte Seite neu laden.';
                return;
            }

            [$class, $action] = $route['handler'];
            (new $class())->{$action}(...array_values(array_map('urldecode', $params)));
            return;
        }

        http_response_code(404);
        echo View::render('layout/404', ['title' => 'Nicht gefunden']);
    }
}

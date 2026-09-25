<?php

declare(strict_types=1);

namespace App\Core;

/**
 * Schlanke PHP-Template-Engine. Views liegen unter app/Views.
 * Ausgaben in den Templates immer über e() escapen.
 */
final class View
{
    public static function render(string $view, array $data = []): string
    {
        $file = BASE_PATH . '/app/Views/' . $view . '.php';
        if (!is_file($file)) {
            throw new \RuntimeException("View nicht gefunden: $view");
        }
        extract($data, EXTR_SKIP);
        ob_start();
        require $file;
        return (string) ob_get_clean();
    }

    /** Rendert eine Seite innerhalb des Hauptlayouts und gibt sie aus. */
    public static function page(string $view, array $data = []): never
    {
        $data['content'] = self::render($view, $data);
        Response::html(self::render('layout/main', $data));
    }
}

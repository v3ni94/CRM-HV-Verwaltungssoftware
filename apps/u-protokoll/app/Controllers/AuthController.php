<?php

declare(strict_types=1);

namespace App\Controllers;

use App\Core\Auth;
use App\Core\Csrf;
use App\Core\Request;
use App\Core\Response;
use App\Core\View;

final class AuthController
{
    public function showLogin(): void
    {
        if (Auth::check()) {
            Response::redirect('/');
        }
        Response::html(View::render('auth/login', ['error' => null]));
    }

    public function login(): void
    {
        // CSRF-Prüfung übernimmt der Router
        $result = Auth::attempt((string) Request::post('username', ''), (string) ($_POST['password'] ?? ''));
        if ($result === true) {
            Response::redirect('/');
        }
        $error = is_string($result) ? $result : 'Benutzername oder Passwort ist nicht korrekt.';
        Response::html(View::render('auth/login', ['error' => $error]), 401);
    }

    /** Eigenes Passwort ändern (alle Rollen, auch Gehilfen). */
    public function showPassword(): void
    {
        View::page('auth/password', ['title' => 'Passwort ändern', 'error' => null]);
    }

    public function changePassword(): void
    {
        $user = Auth::user();
        $current = (string) ($_POST['current_password'] ?? '');
        $new = (string) ($_POST['new_password'] ?? '');
        $repeat = (string) ($_POST['new_password_repeat'] ?? '');

        $error = null;
        if ($user === null || !password_verify($current, $user['password_hash'])) {
            $error = 'Das aktuelle Passwort ist nicht korrekt.';
        } elseif (mb_strlen($new) < 10) {
            $error = 'Das neue Passwort muss mindestens 10 Zeichen haben.';
        } elseif ($new !== $repeat) {
            $error = 'Die Wiederholung stimmt nicht mit dem neuen Passwort überein.';
        } elseif ($new === $current) {
            $error = 'Das neue Passwort muss sich vom aktuellen unterscheiden.';
        }
        if ($error !== null) {
            View::page('auth/password', ['title' => 'Passwort ändern', 'error' => $error]);
        }

        \App\Core\Database::update('users', ['password_hash' => password_hash($new, PASSWORD_DEFAULT)], 'id = ?', [(int) $user['id']]);
        \App\Core\Audit::log('password_changed', 'users', (int) $user['id']);
        $_SESSION['flash_success'] = 'Ihr Passwort wurde geändert.';
        Response::redirect(Auth::isHelper() ? '/meine-uebergabe' : '/');
    }

    public function logout(): void
    {
        \App\Core\Audit::log('logout');
        Auth::logout();
        Response::redirect('/login');
    }
}

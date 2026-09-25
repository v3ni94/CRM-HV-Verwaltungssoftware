<?php

declare(strict_types=1);

namespace App\Controllers;

use App\Core\Audit;
use App\Core\Database;
use App\Core\Response;
use App\Core\View;

/**
 * Einladung annehmen: Der eingeladene Mitarbeiter setzt Benutzername
 * und Passwort selbst. Der Link ist 7 Tage gültig und einmalig nutzbar.
 */
final class InviteController
{
    private function findInvitation(string $token): ?array
    {
        if (!preg_match('/^[a-f0-9]{64}$/', $token)) {
            return null;
        }
        return Database::fetch(
            'SELECT * FROM user_invitations WHERE token_hash = ? AND accepted_at IS NULL AND expires_at > NOW()',
            [hash('sha256', $token)]
        );
    }

    public function show(string $token): void
    {
        $invitation = $this->findInvitation($token);
        Response::html(View::render('auth/invite', [
            'invitation' => $invitation,
            'token'      => $token,
            'error'      => null,
        ]));
    }

    public function accept(string $token): void
    {
        $invitation = $this->findInvitation($token);
        if ($invitation === null) {
            Response::html(View::render('auth/invite', ['invitation' => null, 'token' => $token, 'error' => null]));
        }

        $username = trim((string) ($_POST['username'] ?? ''));
        $password = (string) ($_POST['password'] ?? '');
        $passwordRepeat = (string) ($_POST['password_repeat'] ?? '');

        $error = null;
        if ($username === '' || mb_strlen($username) < 3) {
            $error = 'Bitte einen Benutzernamen mit mindestens 3 Zeichen wählen.';
        } elseif (mb_strlen($password) < 10) {
            $error = 'Das Passwort muss mindestens 10 Zeichen haben.';
        } elseif ($password !== $passwordRepeat) {
            $error = 'Die Passwörter stimmen nicht überein.';
        } elseif (Database::fetch('SELECT id FROM users WHERE username = ? OR email = ?', [$username, $invitation['email']])) {
            $error = 'Benutzername oder E-Mail-Adresse ist bereits vergeben.';
        }
        if ($error !== null) {
            Response::html(View::render('auth/invite', ['invitation' => $invitation, 'token' => $token, 'error' => $error]), 422);
        }

        $userId = Database::insert('users', [
            'username'      => $username,
            'email'         => $invitation['email'],
            'password_hash' => password_hash($password, PASSWORD_DEFAULT),
            'first_name'    => trim((string) ($_POST['first_name'] ?? '')) ?: $invitation['first_name'],
            'last_name'     => trim((string) ($_POST['last_name'] ?? '')) ?: $invitation['last_name'],
            'role'          => $invitation['role'],
            'branch_id'     => $invitation['branch_id'],
            'is_active'     => 1,
        ]);
        Database::update('user_invitations', ['accepted_at' => date('Y-m-d H:i:s')], 'id = ?', [$invitation['id']]);
        Audit::log('invitation_accepted', 'users', $userId, null, null, $invitation['email']);

        $_SESSION['flash_success'] = 'Ihr Zugang wurde eingerichtet. Bitte melden Sie sich an.';
        Response::redirect('/login');
    }
}

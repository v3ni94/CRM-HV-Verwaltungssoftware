<?php
/**
 * U-Protokoll – Hausverwaltung Müller GmbH
 * Front Controller. Sämtliche Requests laufen über diese Datei.
 */

declare(strict_types=1);

define('BASE_PATH', dirname(__DIR__));

require BASE_PATH . '/app/Core/bootstrap.php';

use App\Core\Router;

$router = new Router();

// Authentifizierung
$router->get('/login', [\App\Controllers\AuthController::class, 'showLogin'], false);
$router->post('/login', [\App\Controllers\AuthController::class, 'login'], false);
$router->post('/logout', [\App\Controllers\AuthController::class, 'logout']);
$router->get('/passwort', [\App\Controllers\AuthController::class, 'showPassword']);
$router->post('/passwort', [\App\Controllers\AuthController::class, 'changePassword']);
$router->get('/invite/{token}', [\App\Controllers\InviteController::class, 'show'], false);
$router->post('/invite/{token}', [\App\Controllers\InviteController::class, 'accept'], false);

// Gehilfenansicht (Mieter, Eigentümer, Beauftragte)
$router->get('/meine-uebergabe', [\App\Controllers\HelperController::class, 'home']);
$router->post('/helpers/create', [\App\Controllers\HelperController::class, 'createWithTemplate']);

// Dashboard / Übersicht
$router->get('/', [\App\Controllers\DashboardController::class, 'index']);
$router->get('/protocols', [\App\Controllers\DashboardController::class, 'index']);
$router->get('/protocols/export.csv', [\App\Controllers\DashboardController::class, 'exportCsv']);

// Protokoll-Lebenszyklus
$router->post('/protocols/create', [\App\Controllers\ProtocolController::class, 'create']);
$router->post('/protocols/bulk-archive', [\App\Controllers\ProtocolController::class, 'bulkArchive']);
$router->get('/protocols/{id}', [\App\Controllers\ProtocolController::class, 'show']);
$router->post('/protocols/{id}/duplicate', [\App\Controllers\ProtocolController::class, 'duplicate']);
$router->post('/protocols/{id}/archive', [\App\Controllers\ProtocolController::class, 'archive']);
$router->post('/protocols/{id}/unarchive', [\App\Controllers\ProtocolController::class, 'unarchive']);
$router->post('/protocols/{id}/cancel', [\App\Controllers\ProtocolController::class, 'cancel']);
$router->post('/protocols/{id}/new-version', [\App\Controllers\ProtocolController::class, 'newVersion']);
$router->get('/protocols/{id}/print', [\App\Controllers\ProtocolController::class, 'printView']);
$router->get('/protocols/{id}/defects.pdf', [\App\Controllers\PdfController::class, 'defectList']);

// Gehilfenzugänge zu einem Protokoll
$router->post('/protocols/{id}/helper-access', [\App\Controllers\HelperController::class, 'createForProtocol']);
$router->post('/protocols/{id}/helper-access/revoke', [\App\Controllers\HelperController::class, 'revoke']);
$router->post('/protocols/{id}/helper-access/resend', [\App\Controllers\HelperController::class, 'resendCredentials']);
$router->get('/protocols/{id}/done', [\App\Controllers\HelperController::class, 'done']);
$router->get('/protocols/{id}/confirm', [\App\Controllers\HelperController::class, 'confirm']);

// Wizard
$router->get('/protocols/{id}/wizard/{step}', [\App\Controllers\WizardController::class, 'step']);
$router->post('/protocols/{id}/wizard/{step}', [\App\Controllers\WizardController::class, 'saveStep']);
$router->post('/protocols/{id}/autosave', [\App\Controllers\WizardController::class, 'autosave']);
$router->post('/protocols/{id}/complete', [\App\Controllers\ProtocolController::class, 'complete']);

// Teil-Datensätze (Räume, Mängel, Zähler, Schlüssel, Gegenstände, Notizen, Beteiligte)
$router->post('/protocols/{id}/record/{entity}/save', [\App\Controllers\RecordController::class, 'save']);
$router->post('/protocols/{id}/record/{entity}/delete', [\App\Controllers\RecordController::class, 'delete']);
$router->post('/protocols/{id}/record/{entity}/sort', [\App\Controllers\RecordController::class, 'sort']);
$router->post('/protocols/{id}/rooms/{roomId}/duplicate', [\App\Controllers\RecordController::class, 'duplicateRoom']);

// Dateien
$router->post('/protocols/{id}/files/upload', [\App\Controllers\FileController::class, 'upload']);
$router->post('/protocols/{id}/files/{fileId}/delete', [\App\Controllers\FileController::class, 'delete']);
$router->get('/files/{fileId}', [\App\Controllers\FileController::class, 'download']);
$router->get('/files/{fileId}/thumb', [\App\Controllers\FileController::class, 'thumbnail']);

// Signaturen
$router->post('/protocols/{id}/signatures/save', [\App\Controllers\SignatureController::class, 'save']);
$router->post('/protocols/{id}/signatures/{sigId}/delete', [\App\Controllers\SignatureController::class, 'delete']);

// PDF & E-Mail
$router->get('/protocols/{id}/pdf', [\App\Controllers\PdfController::class, 'show']);
$router->get('/protocols/{id}/pdf/download', [\App\Controllers\PdfController::class, 'download']);
$router->get('/protocols/{id}/email', [\App\Controllers\EmailController::class, 'form']);
$router->post('/protocols/{id}/email/send', [\App\Controllers\EmailController::class, 'send']);

// Administration
$router->get('/admin', [\App\Controllers\AdminController::class, 'index']);
$router->post('/admin/settings', [\App\Controllers\AdminController::class, 'saveSettings']);
$router->get('/admin/users', [\App\Controllers\AdminController::class, 'users']);
$router->post('/admin/users/save', [\App\Controllers\AdminController::class, 'saveUser']);
$router->post('/admin/users/invite', [\App\Controllers\AdminController::class, 'inviteUser']);
$router->post('/admin/users/invitations/delete', [\App\Controllers\AdminController::class, 'deleteInvitation']);
$router->post('/admin/users/invitations/resend', [\App\Controllers\AdminController::class, 'resendInvitation']);
$router->post('/admin/helpers/resend', [\App\Controllers\HelperController::class, 'resendCredentials']);
$router->post('/admin/helpers/create', [\App\Controllers\HelperController::class, 'createWithTemplate']);
$router->get('/admin/audit', [\App\Controllers\AdminController::class, 'audit']);

$router->dispatch();

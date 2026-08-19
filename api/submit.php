<?php

declare(strict_types=1);

require_once __DIR__ . '/db.php';

set_time_limit(120);
header('Content-Type: application/json; charset=utf-8');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['ok' => false, 'error' => 'Method not allowed.'], JSON_UNESCAPED_UNICODE);
    exit;
}

$name = trim((string) ($_POST['name'] ?? ''));
$phone = trim((string) ($_POST['phone'] ?? ''));
$email = trim((string) ($_POST['email'] ?? ''));
$purpose = trim((string) ($_POST['purpose'] ?? ''));
$plan = trim((string) ($_POST['plan'] ?? ''));

if ($name === '') {
    echo json_encode(['ok' => false, 'error' => 'Укажите имя.'], JSON_UNESCAPED_UNICODE);
    exit;
}

if ($phone === '') {
    echo json_encode(['ok' => false, 'error' => 'Укажите телефон.'], JSON_UNESCAPED_UNICODE);
    exit;
}

if ($email !== '' && !filter_var($email, FILTER_VALIDATE_EMAIL)) {
    echo json_encode(['ok' => false, 'error' => 'Укажите корректный e-mail.'], JSON_UNESCAPED_UNICODE);
    exit;
}

try {
    ensureDatabaseReady();

    dbExecuteUntilSuccess(function (PDO $pdo) use ($name, $phone, $email, $purpose, $plan): void {
        $stmt = $pdo->prepare(
            'INSERT INTO orders (name, phone, email, purpose, plan)
             VALUES (:name, :phone, :email, :purpose, :plan)'
        );
        $stmt->execute([
            'name' => $name,
            'phone' => $phone,
            'email' => $email !== '' ? $email : null,
            'purpose' => $purpose !== '' ? $purpose : null,
            'plan' => $plan !== '' ? $plan : null,
        ]);
    });

    echo json_encode(['ok' => true], JSON_UNESCAPED_UNICODE);
} catch (Throwable $e) {
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => 'Не удалось сохранить заявку.'], JSON_UNESCAPED_UNICODE);
}

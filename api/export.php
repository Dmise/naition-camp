<?php

declare(strict_types=1);

require_once __DIR__ . '/db.php';

header('Content-Type: application/json; charset=utf-8');

try {
    $pdo = ensureDatabaseReady();

    $visits = $pdo->query(
        'SELECT id, time FROM visits ORDER BY time DESC, id DESC'
    )->fetchAll();

    $orders = $pdo->query(
        'SELECT id, time, name, phone, email, purpose, plan
         FROM orders ORDER BY time DESC, id DESC'
    )->fetchAll();

    echo json_encode([
        'visits' => $visits,
        'orders' => $orders,
        'meta' => [
            'visits_count' => count($visits),
            'orders_count' => count($orders),
            'generated_at' => (new DateTimeImmutable('now'))->format(DateTimeInterface::ATOM),
        ],
    ], JSON_UNESCAPED_UNICODE);
} catch (Throwable $e) {
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => 'Unable to export data.'], JSON_UNESCAPED_UNICODE);
}

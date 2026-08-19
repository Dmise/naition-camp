<?php

declare(strict_types=1);

require_once __DIR__ . '/db.php';

header('Content-Type: application/json; charset=utf-8');

const MAX_GROUP_SIZE = 14;

try {
    ensureDatabaseReady();

    $ordersCount = (int) dbExecuteUntilSuccess(function (PDO $pdo): int {
        $stmt = $pdo->query('SELECT COUNT(*) AS cnt FROM orders');
        $row = $stmt->fetch();

        return (int) ($row['cnt'] ?? 0);
    });

    $spotsLeft = max(0, MAX_GROUP_SIZE - $ordersCount);

    echo json_encode([
        'ok' => true,
        'orders_count' => $ordersCount,
        'spots_left' => $spotsLeft,
    ], JSON_UNESCAPED_UNICODE);
} catch (Throwable $e) {
    http_response_code(500);
    echo json_encode(['ok' => false, 'error' => 'Unable to load stats.'], JSON_UNESCAPED_UNICODE);
}

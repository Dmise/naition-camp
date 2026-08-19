<?php

declare(strict_types=1);

function getDbPath(): string
{
    return dirname(__DIR__) . '/data/app.db';
}

function getPdo(): PDO
{
    static $pdo = null;

    if ($pdo instanceof PDO) {
        return $pdo;
    }

    $dataDir = dirname(__DIR__) . '/data';
    if (!is_dir($dataDir)) {
        mkdir($dataDir, 0755, true);
    }

    $pdo = new PDO('sqlite:' . getDbPath());
    $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    $pdo->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE, PDO::FETCH_ASSOC);
    $pdo->exec('PRAGMA journal_mode=WAL');
    $pdo->exec('PRAGMA busy_timeout=200');

    return $pdo;
}

function isSqliteBusy(PDOException $e): bool
{
    if ((int) $e->getCode() === 5) {
        return true;
    }

    $message = strtolower($e->getMessage());

    return str_contains($message, 'database is locked')
        || str_contains($message, 'database table is locked');
}

function dbExecuteUntilSuccess(callable $fn): mixed
{
    $pdo = getPdo();
    $delayMs = 5;

    while (true) {
        try {
            return $fn($pdo);
        } catch (PDOException $e) {
            if (!isSqliteBusy($e)) {
                throw $e;
            }

            usleep($delayMs * 1000);
            $delayMs = min($delayMs * 2, 100);
        }
    }
}

function initDatabase(PDO $pdo): void
{
    $schemaPath = dirname(__DIR__) . '/sql/schema.sql';
    $schema = file_get_contents($schemaPath);

    if ($schema === false) {
        throw new RuntimeException('Unable to read schema file.');
    }

    $pdo->exec($schema);
}

function tableHasColumn(PDO $pdo, string $table, string $column): bool
{
    $stmt = $pdo->query('PRAGMA table_info(' . $table . ')');
    if ($stmt === false) {
        return false;
    }

    foreach ($stmt->fetchAll() as $info) {
        if (($info['name'] ?? '') === $column) {
            return true;
        }
    }

    return false;
}

function migrateRemoveBotSessionId(PDO $pdo): void
{
    if (!tableHasColumn($pdo, 'visits', 'bot_session_id') && !tableHasColumn($pdo, 'orders', 'bot_session_id')) {
        return;
    }

    $pdo->exec('BEGIN IMMEDIATE');
    try {
        if (tableHasColumn($pdo, 'visits', 'bot_session_id')) {
            $pdo->exec(
                'CREATE TABLE visits_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    time DATETIME DEFAULT CURRENT_TIMESTAMP
                )'
            );
            $pdo->exec('INSERT INTO visits_new (id, time) SELECT id, time FROM visits');
            $pdo->exec('DROP TABLE visits');
            $pdo->exec('ALTER TABLE visits_new RENAME TO visits');
        }

        if (tableHasColumn($pdo, 'orders', 'bot_session_id')) {
            $pdo->exec(
                'CREATE TABLE orders_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    time DATETIME DEFAULT CURRENT_TIMESTAMP,
                    name TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    email TEXT NOT NULL,
                    purpose TEXT NOT NULL
                )'
            );
            $pdo->exec(
                'INSERT INTO orders_new (id, time, name, phone, email, purpose)
                 SELECT id, time, name, phone, email, purpose FROM orders'
            );
            $pdo->exec('DROP TABLE orders');
            $pdo->exec('ALTER TABLE orders_new RENAME TO orders');
        }

        $pdo->exec('COMMIT');
    } catch (Throwable $e) {
        $pdo->exec('ROLLBACK');
        throw $e;
    }
}

function migrateOrdersOptionalFields(PDO $pdo): void
{
    $needsRebuild = false;

    if (tableHasColumn($pdo, 'orders', 'email')) {
        $stmt = $pdo->query('PRAGMA table_info(orders)');
        foreach ($stmt->fetchAll() as $info) {
            if (($info['name'] ?? '') === 'email' && (int) ($info['notnull'] ?? 0) === 1) {
                $needsRebuild = true;
                break;
            }
        }
    }

    if (!$needsRebuild && !tableHasColumn($pdo, 'orders', 'plan')) {
        $pdo->exec('ALTER TABLE orders ADD COLUMN plan TEXT');
    }

    if (!$needsRebuild) {
        return;
    }

    $pdo->exec('BEGIN IMMEDIATE');
    try {
        $pdo->exec(
            'CREATE TABLE orders_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time DATETIME DEFAULT CURRENT_TIMESTAMP,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                email TEXT,
                purpose TEXT,
                plan TEXT
            )'
        );

        if (tableHasColumn($pdo, 'orders', 'plan')) {
            $pdo->exec(
                'INSERT INTO orders_new (id, time, name, phone, email, purpose, plan)
                 SELECT id, time, name, phone, email, purpose, plan FROM orders'
            );
        } else {
            $pdo->exec(
                'INSERT INTO orders_new (id, time, name, phone, email, purpose)
                 SELECT id, time, name, phone, email, purpose FROM orders'
            );
        }

        $pdo->exec('DROP TABLE orders');
        $pdo->exec('ALTER TABLE orders_new RENAME TO orders');
        $pdo->exec('COMMIT');
    } catch (Throwable $e) {
        $pdo->exec('ROLLBACK');
        throw $e;
    }
}

function ensureDatabaseReady(): PDO
{
    $pdo = getPdo();
    initDatabase($pdo);
    migrateRemoveBotSessionId($pdo);
    migrateOrdersOptionalFields($pdo);

    return $pdo;
}

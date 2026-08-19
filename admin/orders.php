<?php

declare(strict_types=1);

session_start();

require_once dirname(__DIR__) . '/api/db.php';

const ADMIN_PASSWORD = 'FirstAid2026!';

$error = '';

if (isset($_POST['logout'])) {
    unset($_SESSION['orders_admin']);
    header('Location: orders.php');
    exit;
}

if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['password'])) {
    if ($_POST['password'] === ADMIN_PASSWORD) {
        $_SESSION['orders_admin'] = true;
        header('Location: orders.php');
        exit;
    }

    $error = 'Неверный пароль.';
}

$isAuthorized = !empty($_SESSION['orders_admin']);
$orders = [];

if ($isAuthorized) {
    try {
        $pdo = ensureDatabaseReady();
        $orders = $pdo->query(
            'SELECT id, time, name, phone, email, purpose, plan
             FROM orders ORDER BY time DESC, id DESC'
        )->fetchAll();
    } catch (Throwable $e) {
        $error = 'Не удалось загрузить заявки.';
        $isAuthorized = false;
    }
}
?>
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Заявки на курс</title>
    <style>
        body {
            font-family: Georgia, "Times New Roman", serif;
            background: #faf7f5;
            color: #4a4a4a;
            margin: 0;
            padding: 32px 20px;
        }

        .panel {
            max-width: 1100px;
            margin: 0 auto;
            background: #fff;
            border-radius: 16px;
            padding: 28px;
            box-shadow: 0 10px 30px rgba(45, 52, 54, 0.08);
        }

        h1 {
            margin-top: 0;
            color: #2d3436;
        }

        form {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            margin-bottom: 20px;
        }

        input[type="password"] {
            flex: 1;
            min-width: 220px;
            padding: 12px 14px;
            border: 1px solid #d8d2cb;
            border-radius: 10px;
            font-size: 16px;
        }

        button {
            padding: 12px 18px;
            border: none;
            border-radius: 10px;
            background: #b8d4e3;
            color: #2d3436;
            font-size: 16px;
            cursor: pointer;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }

        th, td {
            border-bottom: 1px solid #ece7e1;
            padding: 12px 10px;
            text-align: left;
            vertical-align: top;
        }

        th {
            background: #f0ebe3;
            color: #2d3436;
        }

        .error {
            color: #c0392b;
            margin-bottom: 16px;
        }

        .toolbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 16px;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <div class="panel">
        <h1>Заявки на курс</h1>

        <?php if ($error !== ''): ?>
            <p class="error"><?= htmlspecialchars($error, ENT_QUOTES, 'UTF-8') ?></p>
        <?php endif; ?>

        <?php if (!$isAuthorized): ?>
            <form method="post">
                <input type="password" name="password" placeholder="Пароль" required>
                <button type="submit">Войти</button>
            </form>
        <?php else: ?>
            <div class="toolbar">
                <p>Всего заявок: <?= count($orders) ?></p>
                <form method="post">
                    <button type="submit" name="logout" value="1">Выйти</button>
                </form>
            </div>

            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Время</th>
                        <th>Имя</th>
                        <th>Телефон</th>
                        <th>E-mail</th>
                        <th>Цель</th>
                        <th>Тариф</th>
                    </tr>
                </thead>
                <tbody>
                    <?php if ($orders === []): ?>
                        <tr>
                            <td colspan="7">Заявок пока нет.</td>
                        </tr>
                    <?php else: ?>
                        <?php foreach ($orders as $order): ?>
                            <tr>
                                <td><?= (int) $order['id'] ?></td>
                                <td><?= htmlspecialchars((string) $order['time'], ENT_QUOTES, 'UTF-8') ?></td>
                                <td><?= htmlspecialchars((string) $order['name'], ENT_QUOTES, 'UTF-8') ?></td>
                                <td><?= htmlspecialchars((string) $order['phone'], ENT_QUOTES, 'UTF-8') ?></td>
                                <td><?= htmlspecialchars((string) ($order['email'] ?? ''), ENT_QUOTES, 'UTF-8') ?></td>
                                <td><?= nl2br(htmlspecialchars((string) ($order['purpose'] ?? ''), ENT_QUOTES, 'UTF-8')) ?></td>
                                <td><?= htmlspecialchars((string) ($order['plan'] ?? ''), ENT_QUOTES, 'UTF-8') ?></td>
                            </tr>
                        <?php endforeach; ?>
                    <?php endif; ?>
                </tbody>
            </table>
        <?php endif; ?>
    </div>
</body>
</html>

<?php
require_once __DIR__ . '/config.php';

function airadio_load_url2ai_auth() {
    $path = '/home/kojima/work/url2ai/src/auth_common.php';
    if (file_exists($path)) {
        require_once $path;
        return function_exists('url2ai_auth_bootstrap');
    }
    return false;
}

function airadio_auth() {
    if (getenv('AIRADIO_ALLOW_DEV_LOGIN') === '1' && !empty($_COOKIE['AIRADIO_DEV_USER'])) {
        $user = preg_replace('/[^A-Za-z0-9_]/', '', $_COOKIE['AIRADIO_DEV_USER']);
        return [
            'logged_in' => $user !== '',
            'session_user' => $user,
            'is_admin' => $user === AIRADIO_ALLOWED_USER,
            'allowed' => $user === AIRADIO_ALLOWED_USER,
            'login_url' => '?demo_login=' . AIRADIO_ALLOWED_USER,
            'logout_url' => '?demo_logout=1',
        ];
    }
    if (airadio_load_url2ai_auth()) {
        $auth = url2ai_auth_bootstrap();
        $auth['allowed'] = !empty($auth['logged_in']) && ($auth['session_user'] ?? '') === AIRADIO_ALLOWED_USER;
        return $auth;
    }
    if (session_status() !== PHP_SESSION_ACTIVE) { session_start(); }
    $user = $_SESSION['session_username'] ?? '';
    return [
        'logged_in' => $user !== '',
        'session_user' => $user,
        'is_admin' => $user === AIRADIO_ALLOWED_USER,
        'allowed' => $user === AIRADIO_ALLOWED_USER,
        'login_url' => '?demo_login=' . AIRADIO_ALLOWED_USER,
        'logout_url' => '?demo_logout=1',
    ];
}

function airadio_handle_dev_login() {
    if (getenv('AIRADIO_ALLOW_DEV_LOGIN') !== '1') { return; }
    if (isset($_GET['demo_login'])) {
        if (session_status() !== PHP_SESSION_ACTIVE) { session_start(); }
        $_SESSION['session_username'] = preg_replace('/[^A-Za-z0-9_]/', '', $_GET['demo_login']);
        $_SESSION['session_logged_in_until'] = time() + 60 * 60 * 24 * 365;
        setcookie('AIRADIO_DEV_USER', $_SESSION['session_username'], time() + 3600, '/', '', false, true);
        header('Location: ' . strtok($_SERVER['REQUEST_URI'], '?'));
        exit;
    }
    if (isset($_GET['demo_logout'])) {
        if (session_status() !== PHP_SESSION_ACTIVE) { session_start(); }
        session_destroy();
        setcookie('AIRADIO_DEV_USER', '', time() - 3600, '/', '', false, true);
        header('Location: ' . strtok($_SERVER['REQUEST_URI'], '?'));
        exit;
    }
}

function airadio_require_allowed_json() {
    $auth = airadio_auth();
    if (empty($auth['allowed'])) {
        http_response_code(empty($auth['logged_in']) ? 401 : 403);
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode(['ok' => false, 'error' => 'not_allowed', 'auth' => $auth], JSON_UNESCAPED_UNICODE);
        exit;
    }
    return $auth;
}

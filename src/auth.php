<?php
require_once __DIR__ . '/config.php';

function airadio_load_url2ai_auth() {
    $candidates = [
        getenv('AIRADIO_AUTH_COMMON') ?: '',
        __DIR__ . '/auth_common.php',
        dirname(__DIR__) . '/auth_common.php',
        '/home/kojima/work/url2ai/src/auth_common.php',
        '/home/users/0/exbridge/web/aiknowledgecms_exbridge_jp/auth_common.php',
        '/web/aiknowledgecms_exbridge_jp/auth_common.php',
        '../aiknowledgecms_exbridge_jp/auth_common.php',
    ];
    foreach ($candidates as $path) {
        if ($path !== '' && file_exists($path)) {
            require_once $path;
            return function_exists('url2ai_auth_bootstrap');
        }
    }
    foreach (glob(dirname(__DIR__) . '/../*/auth_common.php') ?: [] as $path) {
        require_once $path;
        if (function_exists('url2ai_auth_bootstrap')) {
            return true;
        }
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
            'allowed' => $user !== '',
            'login_url' => '?demo_login=' . AIRADIO_ALLOWED_USER,
            'logout_url' => '?demo_logout=1',
        ];
    }
    if (airadio_load_url2ai_auth()) {
        $auth = url2ai_auth_bootstrap();
        $auth['allowed'] = !empty($auth['logged_in']);
        $auth['login_url'] = airadio_common_login_url();
        $auth['logout_url'] = airadio_common_logout_url();
        return $auth;
    }
    if (session_status() !== PHP_SESSION_ACTIVE) { session_start(); }
    $user = isset($_SESSION['session_username']) ? $_SESSION['session_username'] : '';
    return [
        'logged_in' => $user !== '',
        'session_user' => $user,
        'is_admin' => $user === AIRADIO_ALLOWED_USER,
        'allowed' => $user !== '',
        'login_url' => '?demo_login=' . AIRADIO_ALLOWED_USER,
        'logout_url' => '?demo_logout=1',
    ];
}

function airadio_common_login_url() {
    return 'https://aiknowledgecms.exbridge.jp/aiknowledgesns.php?aks_login=1&return=' . urlencode(AIRADIO_PUBLIC_BASE_URL);
}

function airadio_common_logout_url() {
    return 'https://aiknowledgecms.exbridge.jp/aiknowledgesns.php?aks_logout=1&return=' . urlencode(AIRADIO_PUBLIC_BASE_URL);
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

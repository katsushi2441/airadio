<?php
require_once __DIR__ . '/auth.php';
require_once __DIR__ . '/config.php';

airadio_handle_login();
$auth = airadio_require_allowed_json();

$action = isset($_GET['action']) ? preg_replace('/[^A-Za-z0-9_-]/', '', (string)$_GET['action']) : 'status';
$method = isset($_SERVER['REQUEST_METHOD']) ? strtoupper((string)$_SERVER['REQUEST_METHOD']) : 'GET';
$body = file_get_contents('php://input');
if ($body === false) { $body = '{}'; }

function airadio_proxy_base() {
    if (defined('AIRADIO_APP_API_BASE') && trim((string)AIRADIO_APP_API_BASE) !== '') {
        return rtrim((string)AIRADIO_APP_API_BASE, '/');
    }
    $env = trim((string)getenv('AIRADIO_APP_API_BASE'));
    if ($env !== '') { return rtrim($env, '/'); }
    return 'http://exbridge.ddns.net:18310';
}

function airadio_proxy_error($error, $code = 502, $extra = []) {
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode(array_merge(['ok' => false, 'error' => $error], $extra), JSON_UNESCAPED_UNICODE);
    exit;
}

$url = airadio_proxy_base() . '/api/' . rawurlencode($action);
$headers = [
    'Content-Type: application/json',
    'X-Airadio-Auth: ' . json_encode($auth, JSON_UNESCAPED_UNICODE),
];
$opts = [
    'http' => [
        'method' => $method === 'POST' ? 'POST' : 'GET',
        'header' => implode("\r\n", $headers) . "\r\n",
        'timeout' => $action === 'tts' ? 75 : 45,
        'ignore_errors' => true,
    ],
];
if ($method === 'POST') { $opts['http']['content'] = $body !== '' ? $body : '{}'; }
$ctx = stream_context_create($opts);
$raw = @file_get_contents($url, false, $ctx);
$status = 502;
$contentType = 'application/json; charset=utf-8';
if (isset($http_response_header) && is_array($http_response_header)) {
    foreach ($http_response_header as $line) {
        if (preg_match('#^HTTP/\S+\s+(\d+)#', $line, $m)) { $status = (int)$m[1]; }
        if (stripos($line, 'Content-Type:') === 0) { $contentType = trim(substr($line, 13)); }
    }
}
if ($raw === false) {
    airadio_proxy_error('airadio_app_api_unreachable', 502, ['target' => airadio_proxy_base()]);
}
http_response_code($status);
header('Content-Type: ' . $contentType);
if ($action === 'tts') { header('Cache-Control: private, max-age=86400'); }
echo $raw;

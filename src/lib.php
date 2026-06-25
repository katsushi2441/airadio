<?php
require_once __DIR__ . '/config.php';

function airadio_read_json($path, $fallback) {
    if (!file_exists($path)) { return $fallback; }
    $raw = file_get_contents($path);
    $data = json_decode($raw ?: '', true);
    return is_array($data) ? $data : $fallback;
}

function airadio_write_json($path, $data) {
    $dir = dirname($path);
    if (!is_dir($dir)) { mkdir($dir, 0775, true); }
    $tmp = $path . '.tmp';
    file_put_contents($tmp, json_encode($data, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT) . "\n", LOCK_EX);
    rename($tmp, $path);
}

function airadio_state() {
    return airadio_read_json(AIRADIO_STATE_FILE, [
        'status' => 'idle',
        'theme' => 'AI思考、バイブコーディング、やさしい睡眠ラジオ',
        'duration_hours' => 1,
        'started_at' => '',
        'ends_at' => '',
        'loop_state' => 'waiting',
        'now_talking' => '',
        'research_status' => 'idle',
        'updated_at' => date('c'),
    ]);
}

function airadio_queue() {
    return airadio_read_json(AIRADIO_QUEUE_FILE, ['items' => []]);
}

function airadio_update_state($patch) {
    $state = array_merge(airadio_state(), $patch, ['updated_at' => date('c')]);
    airadio_write_json(AIRADIO_STATE_FILE, $state);
    return $state;
}

function airadio_append_log($message, $data = []) {
    $line = json_encode(['time' => date('c'), 'message' => $message, 'data' => $data], JSON_UNESCAPED_UNICODE) . "\n";
    file_put_contents(AIRADIO_LOG_FILE, $line, FILE_APPEND | LOCK_EX);
}

function airadio_profile_from_session() {
    $profile = ['username' => '', 'name' => '', 'description' => '', 'source' => 'session'];
    if (session_status() !== PHP_SESSION_ACTIVE) { @session_start(); }
    $profile['username'] = $_SESSION['session_username'] ?? '';
    $token = $_SESSION['session_access_token'] ?? '';
    if ($token !== '') {
        $url = 'https://api.twitter.com/2/users/me?user.fields=description,profile_image_url,public_metrics,verified';
        $ctx = stream_context_create(['http' => [
            'method' => 'GET',
            'header' => "Authorization: Bearer $token\r\nUser-Agent: KurageAIRadio/0.1\r\n",
            'timeout' => 8,
            'ignore_errors' => true,
        ]]);
        $raw = @file_get_contents($url, false, $ctx);
        $json = json_decode($raw ?: '{}', true);
        if (!empty($json['data'])) {
            $profile = array_merge($profile, $json['data']);
            $profile['source'] = 'x_api';
        }
    }
    return $profile;
}

function airadio_start_worker($theme, $profile, $reason = 'manual') {
    $payload = AIRADIO_STORAGE_DIR . '/worker_payload.json';
    airadio_write_json($payload, ['theme' => $theme, 'profile' => $profile, 'reason' => $reason, 'created_at' => date('c')]);
    $python = getenv('AIRADIO_PYTHON') ?: '/usr/bin/python3';
    $cmd = sprintf(
        'cd %s && nohup %s %s --payload %s >> %s 2>&1 & echo $!',
        escapeshellarg(dirname(__DIR__)),
        escapeshellcmd($python),
        escapeshellarg(__DIR__ . '/airadio_worker.py'),
        escapeshellarg($payload),
        escapeshellarg(AIRADIO_LOG_FILE)
    );
    $pid = trim((string)shell_exec($cmd));
    airadio_append_log('worker_started', ['pid' => $pid, 'theme' => $theme, 'reason' => $reason]);
    return $pid;
}

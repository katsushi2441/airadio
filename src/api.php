<?php
require_once __DIR__ . '/auth.php';
require_once __DIR__ . '/lib.php';

airadio_handle_login();
$auth = airadio_require_allowed_json();
header('Content-Type: application/json; charset=utf-8');

$action = isset($_GET['action']) ? $_GET['action'] : 'status';
$method = isset($_SERVER['REQUEST_METHOD']) ? $_SERVER['REQUEST_METHOD'] : 'GET';
$input = json_decode(file_get_contents('php://input') ?: '{}', true);
if (!is_array($input)) { $input = []; }

function ok($data = []) { echo json_encode(array_merge(['ok' => true], $data), JSON_UNESCAPED_UNICODE); exit; }
function bad($error, $code = 400, $data = []) { http_response_code($code); echo json_encode(array_merge(['ok' => false, 'error' => $error], $data), JSON_UNESCAPED_UNICODE); exit; }

function require_admin($auth) {
    if (empty($auth['is_admin'])) { bad('admin_required', 403); }
}

function airadio_post_json($url, $payload, $headers = []) {
    $body = json_encode($payload, JSON_UNESCAPED_UNICODE);
    $headerLines = ["Content-Type: application/json"];
    foreach ($headers as $key => $value) { $headerLines[] = $key . ': ' . $value; }
    $ctx = stream_context_create(['http' => [
        'method' => 'POST',
        'header' => implode("\r\n", $headerLines) . "\r\n",
        'content' => $body,
        'timeout' => 30,
        'ignore_errors' => true,
    ]]);
    $raw = @file_get_contents($url, false, $ctx);
    $data = json_decode($raw ? $raw : '{}', true);
    return is_array($data) ? $data : ['raw' => $raw];
}

function airadio_default_stream_key() {
    $env = trim((string)getenv('YOUTUBE_STREAM_KEY'));
    if ($env !== '') { return $env; }
    $configPath = AIRADIO_KVTUBER_DIR . '/storage/youtube-live.json';
    if (is_file($configPath)) {
        $config = json_decode(file_get_contents($configPath), true);
        if (is_array($config) && !empty($config['streamKey'])) {
            return trim((string)$config['streamKey']);
        }
    }
    $localPath = AIRADIO_STORAGE_DIR . '/youtube-live.json';
    if (is_file($localPath)) {
        $config = json_decode(file_get_contents($localPath), true);
        if (is_array($config) && !empty($config['streamKey'])) {
            return trim((string)$config['streamKey']);
        }
    }
    return '';
}

if ($action === 'status') {
    ok([
        'auth' => $auth,
        'state' => airadio_state(),
        'queue' => airadio_queue(),
        'current' => airadio_current_segment(),
        'comments' => airadio_comments(),
        'youtube' => ['has_default_stream_key' => airadio_default_stream_key() !== ''],
    ]);
}

if ($action === 'profile') {
    ok(['profile' => airadio_profile_from_session()]);
}

if ($action === 'current') {
    ok(['state' => airadio_state(), 'current' => airadio_current_segment(), 'comments' => airadio_comments()]);
}

if ($action === 'tts') {
    $text = isset($input['text']) ? (string)$input['text'] : '';
    try {
        $path = airadio_tts_audio_path($text);
    } catch (Throwable $e) {
        bad('tts_failed', 500, ['message' => $e->getMessage()]);
    }
    header('Content-Type: audio/mpeg');
    header('Content-Length: ' . filesize($path));
    header('Cache-Control: private, max-age=86400');
    readfile($path);
    exit;
}

if ($action === 'comments') {
    ok(['comments' => airadio_comments()]);
}

if ($action === 'comment') {
    $text = trim((string)(isset($input['text']) ? $input['text'] : ''));
    if ($text === '') { bad('comment_required'); }
    $user = isset($auth['session_user']) ? (string)$auth['session_user'] : '';
    $item = airadio_add_comment($user, $text, !empty($auth['is_admin']));
    ok(['comment' => $item, 'comments' => airadio_comments()]);
}

if ($action === 'start') {
    require_admin($auth);
    $rawTheme = trim((string)(isset($input['theme']) ? $input['theme'] : ''));
    $hasInstruction = $rawTheme !== '';
    $theme = airadio_normalize_theme_request($rawTheme);
    $profile = airadio_profile_from_session();
    if ($theme === '') { $theme = airadio_default_theme_from_profile($profile); }
    $themeGuidance = airadio_theme_guidance($theme);
    $hours = max(1, min(6, (int)(isset($input['duration_hours']) ? $input['duration_hours'] : 1)));
    $now = time();
    airadio_reset_program_memory();
    $state = airadio_update_state([
        'status' => 'on_air',
        'theme' => $theme,
        'duration_hours' => $hours,
        'started_at' => date('c', $now),
        'ends_at' => date('c', $now + $hours * 3600),
        'loop_state' => 'speaking',
        'research_status' => 'queued',
        'broadcaster' => isset($auth['session_user']) ? $auth['session_user'] : AIRADIO_ALLOWED_USER,
        'requested_theme' => $rawTheme,
        'theme_guidance' => $themeGuidance,
    ]);
    $items = [[
        'id' => 'opening-' . time(),
        'theme' => $theme,
        'requested_theme' => $rawTheme,
        'title' => $hasInstruction ? airadio_spoken_theme_title($theme, $rawTheme) . 'を始めます' : 'オープニング',
        'text' => $hasInstruction
            ? 'こんばんは。Kurage AI VTuber Radioです。' . airadio_spoken_theme_title($theme, $rawTheme) . 'について話します。'
            : 'こんばんは。Kurage AI VTuber Radioです。' . airadio_spoken_theme_title($theme) . 'について話します。',
        'source' => 'opening',
        'created_at' => date('c'),
    ]];
    $items = array_merge(
        $items,
        $hasInstruction
            ? airadio_seed_instruction_program($theme, $rawTheme, $themeGuidance)
            : airadio_seed_profile_program($theme, $profile)
    );
    $queue = ['items' => $items, 'updated_at' => date('c')];
    airadio_write_json(AIRADIO_QUEUE_FILE, $queue);
    $ttsPid = airadio_start_tts_prefetch($items, 'start');
    $pid = airadio_start_worker($theme, $profile, 'start', [
        'instruction' => $rawTheme,
        'theme_guidance' => $themeGuidance,
        'ignore_profile_script' => $hasInstruction,
    ]);
    ok(['state' => $state, 'worker_pid' => $pid, 'tts_prefetch_pid' => $ttsPid, 'prefetch_items' => array_slice($items, 0, AIRADIO_TTS_PREFETCH_LIMIT)]);
}

if ($action === 'stop') {
    require_admin($auth);
    airadio_clear_current_segment();
    $state = airadio_update_state(['status' => 'idle', 'loop_state' => 'stopped', 'now_talking' => '', 'research_status' => 'idle']);
    ok(['state' => $state]);
}

if ($action === 'interrupt') {
    require_admin($auth);
    $rawTheme = trim((string)(isset($input['theme']) ? $input['theme'] : ''));
    $theme = airadio_normalize_theme_request($rawTheme);
    if ($theme === '') { bad('theme_required'); }
    $themeGuidance = airadio_theme_guidance($theme);
    $queue = airadio_queue();
    $interruptItem = [
        'id' => 'interrupt-' . time(),
        'theme' => $theme,
        'requested_theme' => $rawTheme,
        'title' => airadio_spoken_theme_title($theme, $rawTheme) . 'へ切り替え',
        'text' => airadio_spoken_theme_title($theme, $rawTheme) . 'について話します。',
        'source' => 'interrupt',
        'created_at' => date('c'),
    ];
    array_unshift($queue['items'], $interruptItem);
    airadio_write_json(AIRADIO_QUEUE_FILE, $queue);
    $ttsPid = airadio_start_tts_prefetch([$interruptItem], 'interrupt');
    $state = airadio_update_state(['theme' => $theme, 'requested_theme' => $rawTheme, 'theme_guidance' => $themeGuidance, 'research_status' => 'queued', 'loop_state' => 'theme_interrupt']);
    $pid = airadio_start_worker($theme, airadio_profile_from_session(), 'interrupt', [
        'instruction' => $rawTheme,
        'theme_guidance' => $themeGuidance,
        'ignore_profile_script' => true,
    ]);
    ok(['state' => $state, 'worker_pid' => $pid, 'tts_prefetch_pid' => $ttsPid, 'queue' => $queue]);
}

if ($action === 'next') {
    require_admin($auth);
    $state = airadio_state();
    if (isset($state['status']) && $state['status'] !== 'on_air') {
        bad('radio_not_on_air', 409, ['state' => $state, 'current' => airadio_current_segment()]);
    }
    $queue = airadio_queue();
    $items = isset($queue['items']) ? $queue['items'] : [];
    if (!is_array($items)) { $items = []; }
    $item = array_shift($items);
    if (!$item) {
        $theme = isset($state['theme']) ? $state['theme'] : 'AI思考';
        $bridgeCount = isset($state['bridge_count']) ? ((int)$state['bridge_count'] + 1) : 1;
        $bridgeTexts = [
            $theme . 'について、次の台本を待つあいだに全体像を短く整理します。資料にあることと、まだ分からないことを分けて聞くと理解しやすくなります。',
            $theme . 'を別の角度から見ます。大事なのは、名前の印象ではなく、何を説明しようとしているのかを押さえることです。',
            $theme . 'の話を聞くときは、背景、仕組み、使いどころ、注意点に分けると、内容がほどけていきます。',
            $theme . 'について、次に確認したい問いを一つ置きます。この資料は、誰のどんな課題に役立つのか。そこから見ていきます。',
        ];
        $bridgeText = $bridgeTexts[($bridgeCount - 1) % count($bridgeTexts)];
        $item = [
            'id' => 'bridge-' . time(),
            'theme' => $theme,
            'title' => '補助線 ' . $bridgeCount,
            'text' => $bridgeText,
            'source' => 'bridge',
            'created_at' => date('c'),
        ];
        $researchStatus = isset($state['research_status']) ? $state['research_status'] : '';
        if ($researchStatus !== 'collecting' && $researchStatus !== 'scripting') {
            airadio_start_worker($theme, airadio_profile_from_session(), 'queue_empty');
        }
    }
    $queue['items'] = $items;
    airadio_write_json(AIRADIO_QUEUE_FILE, $queue);
    $upcoming = array_slice($items, 0, AIRADIO_TTS_PREFETCH_LIMIT);
    if (!empty($upcoming)) {
        airadio_start_tts_prefetch($upcoming, 'next');
    }
    $patch = ['now_talking' => isset($item['title']) ? $item['title'] : '', 'loop_state' => 'speaking'];
    if (isset($bridgeCount)) { $patch['bridge_count'] = $bridgeCount; }
    $current = airadio_set_current_segment($item);
    airadio_update_state($patch);
    ok(['item' => $item, 'current' => $current, 'queue_remaining' => count($items), 'prefetch_items' => $upcoming, 'state' => airadio_state()]);
}

if ($action === 'youtube_start') {
    require_admin($auth);
    $streamKey = trim((string)(isset($input['stream_key']) ? $input['stream_key'] : ''));
    if ($streamKey === '') { $streamKey = airadio_default_stream_key(); }
    $viewerUrl = trim((string)(isset($input['viewer_url']) ? $input['viewer_url'] : AIRADIO_PUBLIC_BASE_URL));
    $controlBase = rtrim((string)getenv('AIRADIO_KVTUBER_CONTROL_BASE'), '/');
    $adminToken = trim((string)getenv('AIRADIO_KVTUBER_ADMIN_TOKEN'));
    if ($controlBase !== '') {
        if ($adminToken === '') { bad('kvtuber_admin_token_not_configured', 500); }
        $headers = ['X-Admin-Token' => $adminToken];
        $configResult = airadio_post_json($controlBase . '/control/youtube-live', [
            'streamKey' => $streamKey,
            'viewerUrl' => $viewerUrl,
        ], $headers);
        if (empty($configResult['ok']) && empty($configResult['config'])) {
            bad('kvtuber_youtube_config_failed', 502, ['result' => $configResult]);
        }
        $startResult = airadio_post_json($controlBase . '/control/youtube-live/start', [], $headers);
        if (empty($startResult['ok']) && empty($startResult['status']) && empty($startResult['pid'])) {
            bad('kvtuber_youtube_start_failed', 502, ['result' => $startResult]);
        }
        ok(['mode' => 'kvtuber-control-api', 'viewer_url' => $viewerUrl, 'result' => $startResult]);
    }
    $configPath = AIRADIO_KVTUBER_DIR . '/storage/youtube-live.json';
    $scriptPath = AIRADIO_KVTUBER_DIR . '/scripts/youtube-live-rtmp.mjs';
    if (!is_file($scriptPath)) {
        bad('youtube_live_not_configured', 500, [
            'hint' => 'Set AIRADIO_KVTUBER_CONTROL_BASE/AIRADIO_KVTUBER_ADMIN_TOKEN or deploy kvtuber on the same host.',
        ]);
    }
    $config = file_exists($configPath) ? json_decode(file_get_contents($configPath), true) : [];
    if (!is_array($config)) { $config = []; }
    $config['viewerUrl'] = $viewerUrl;
    if ($streamKey !== '') { $config['streamKey'] = $streamKey; }
    if (empty($config['streamKey'])) { bad('stream_key_required', 400); }
    if (!is_dir(dirname($configPath))) { mkdir(dirname($configPath), 0775, true); }
    file_put_contents($configPath, json_encode($config, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT) . "\n");
    $cmd = 'cd ' . escapeshellarg(AIRADIO_KVTUBER_DIR) . ' && nohup node scripts/youtube-live-rtmp.mjs start >> /tmp/airadio-youtube-live.log 2>&1 & echo $!';
    $pid = trim((string)shell_exec($cmd));
    ok(['pid' => $pid, 'viewer_url' => $viewerUrl]);
}

if ($action === 'youtube_stop') {
    require_admin($auth);
    $controlBase = rtrim((string)getenv('AIRADIO_KVTUBER_CONTROL_BASE'), '/');
    $adminToken = trim((string)getenv('AIRADIO_KVTUBER_ADMIN_TOKEN'));
    if ($controlBase !== '') {
        if ($adminToken === '') { bad('kvtuber_admin_token_not_configured', 500); }
        $result = airadio_post_json($controlBase . '/control/youtube-live/stop', [], ['X-Admin-Token' => $adminToken]);
        ok(['mode' => 'kvtuber-control-api', 'result' => $result]);
    }
    if (!is_file(AIRADIO_KVTUBER_DIR . '/scripts/youtube-live-rtmp.mjs')) {
        bad('youtube_live_not_configured', 500);
    }
    $cmd = 'cd ' . escapeshellarg(AIRADIO_KVTUBER_DIR) . ' && node scripts/youtube-live-rtmp.mjs stop 2>&1';
    $out = shell_exec($cmd);
    ok(['output' => $out]);
}

bad('unknown_action', 404, ['action' => $action]);

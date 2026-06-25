<?php
require_once __DIR__ . '/auth.php';
require_once __DIR__ . '/lib.php';

airadio_handle_dev_login();
$auth = airadio_require_allowed_json();
header('Content-Type: application/json; charset=utf-8');

$action = isset($_GET['action']) ? $_GET['action'] : 'status';
$method = isset($_SERVER['REQUEST_METHOD']) ? $_SERVER['REQUEST_METHOD'] : 'GET';
$input = json_decode(file_get_contents('php://input') ?: '{}', true);
if (!is_array($input)) { $input = []; }

function ok($data = []) { echo json_encode(array_merge(['ok' => true], $data), JSON_UNESCAPED_UNICODE); exit; }
function bad($error, $code = 400, $data = []) { http_response_code($code); echo json_encode(array_merge(['ok' => false, 'error' => $error], $data), JSON_UNESCAPED_UNICODE); exit; }

if ($action === 'status') {
    ok(['auth' => $auth, 'state' => airadio_state(), 'queue' => airadio_queue()]);
}

if ($action === 'profile') {
    ok(['profile' => airadio_profile_from_session()]);
}

if ($action === 'start') {
    $theme = trim((string)(isset($input['theme']) ? $input['theme'] : ''));
    if ($theme === '') { $theme = 'AI思考、バイブコーディング、静かな睡眠ラジオ'; }
    $hours = max(1, min(6, (int)(isset($input['duration_hours']) ? $input['duration_hours'] : 1)));
    $now = time();
    $state = airadio_update_state([
        'status' => 'on_air',
        'theme' => $theme,
        'duration_hours' => $hours,
        'started_at' => date('c', $now),
        'ends_at' => date('c', $now + $hours * 3600),
        'loop_state' => 'speaking',
        'research_status' => 'queued',
    ]);
    $queue = airadio_queue();
    if (empty($queue['items'])) {
        $queue['items'] = [[
            'id' => 'opening-' . time(),
            'theme' => $theme,
            'title' => 'オープニング',
            'text' => 'こんばんは。Kurage AI VTuber Radioです。今夜は、' . $theme . 'をテーマに、ゆっくり考えていきます。裏側では情報収集を進めながら、こちらでは待たせず、静かに話し続けます。眠くなったら、そのまま目を閉じてください。',
            'source' => 'opening',
            'created_at' => date('c'),
        ]];
        airadio_write_json(AIRADIO_QUEUE_FILE, $queue);
    }
    $pid = airadio_start_worker($theme, airadio_profile_from_session(), 'start');
    ok(['state' => $state, 'worker_pid' => $pid]);
}

if ($action === 'stop') {
    $state = airadio_update_state(['status' => 'idle', 'loop_state' => 'stopped', 'now_talking' => '', 'research_status' => 'idle']);
    ok(['state' => $state]);
}

if ($action === 'interrupt') {
    $theme = trim((string)(isset($input['theme']) ? $input['theme'] : ''));
    if ($theme === '') { bad('theme_required'); }
    $queue = airadio_queue();
    array_unshift($queue['items'], [
        'id' => 'interrupt-' . time(),
        'theme' => $theme,
        'title' => 'テーマ割り込み',
        'text' => 'テーマを切り替えます。ここからは、' . $theme . 'について、静かに考えていきます。すぐに結論を急がず、背景、論点、実践の順に、ゆっくり眺めていきましょう。裏側では関連情報の収集を始めています。',
        'source' => 'interrupt',
        'created_at' => date('c'),
    ]);
    airadio_write_json(AIRADIO_QUEUE_FILE, $queue);
    $state = airadio_update_state(['theme' => $theme, 'research_status' => 'queued', 'loop_state' => 'theme_interrupt']);
    $pid = airadio_start_worker($theme, airadio_profile_from_session(), 'interrupt');
    ok(['state' => $state, 'worker_pid' => $pid, 'queue' => $queue]);
}

if ($action === 'next') {
    $state = airadio_state();
    $queue = airadio_queue();
    $items = isset($queue['items']) ? $queue['items'] : [];
    if (!is_array($items)) { $items = []; }
    $item = array_shift($items);
    if (!$item) {
        $theme = isset($state['theme']) ? $state['theme'] : 'AI思考';
        $item = [
            'id' => 'bridge-' . time(),
            'theme' => $theme,
            'title' => 'ブリッジトーク',
            'text' => '少しだけ、静かな間を置きます。裏側では、' . $theme . 'について情報を集めています。次の話題が届くまで、呼吸をゆっくり整えながら、考えの流れをほどいていきましょう。',
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
    airadio_update_state(['now_talking' => isset($item['title']) ? $item['title'] : '', 'loop_state' => 'speaking']);
    ok(['item' => $item, 'queue_remaining' => count($items), 'state' => airadio_state()]);
}

if ($action === 'youtube_start') {
    $streamKey = trim((string)(isset($input['stream_key']) ? $input['stream_key'] : ''));
    $viewerUrl = trim((string)(isset($input['viewer_url']) ? $input['viewer_url'] : AIRADIO_PUBLIC_BASE_URL));
    $configPath = AIRADIO_KVTUBER_DIR . '/storage/youtube-live.json';
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
    $cmd = 'cd ' . escapeshellarg(AIRADIO_KVTUBER_DIR) . ' && node scripts/youtube-live-rtmp.mjs stop 2>&1';
    $out = shell_exec($cmd);
    ok(['output' => $out]);
}

bad('unknown_action', 404, ['action' => $action]);

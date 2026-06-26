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

function airadio_current_segment() {
    return airadio_read_json(AIRADIO_CURRENT_FILE, ['item' => null, 'updated_at' => '']);
}

function airadio_comments() {
    $comments = airadio_read_json(AIRADIO_COMMENTS_FILE, ['items' => []]);
    $items = isset($comments['items']) && is_array($comments['items']) ? $comments['items'] : [];
    $comments['items'] = array_slice($items, -80);
    return $comments;
}

function airadio_add_comment($user, $text, $is_editor = false) {
    $text = trim(preg_replace('/\s+/', ' ', (string)$text));
    if ($text === '') { return null; }
    if (function_exists('mb_strlen') && mb_strlen($text, 'UTF-8') > 500) {
        $text = mb_substr($text, 0, 500, 'UTF-8');
    } elseif (!function_exists('mb_strlen') && strlen($text) > 1500) {
        $text = substr($text, 0, 1500);
    }
    $comments = airadio_comments();
    $items = isset($comments['items']) && is_array($comments['items']) ? $comments['items'] : [];
    $item = [
        'id' => 'comment-' . time() . '-' . substr(sha1($text . microtime(true)), 0, 8),
        'user' => $is_editor ? '編集者' : ((string)$user !== '' ? (string)$user : 'リスナー'),
        'role' => $is_editor ? 'editor' : 'listener',
        'text' => $text,
        'created_at' => date('c'),
    ];
    $items[] = $item;
    $comments['items'] = array_slice($items, -80);
    $comments['updated_at'] = date('c');
    airadio_write_json(AIRADIO_COMMENTS_FILE, $comments);
    return $item;
}

function airadio_set_current_segment($item) {
    $current = [
        'item' => $item,
        'updated_at' => date('c'),
    ];
    airadio_write_json(AIRADIO_CURRENT_FILE, $current);
    return $current;
}

function airadio_clear_current_segment() {
    airadio_write_json(AIRADIO_CURRENT_FILE, ['item' => null, 'updated_at' => date('c')]);
}

function airadio_reset_program_memory() {
    airadio_write_json(AIRADIO_QUEUE_FILE, ['items' => [], 'updated_at' => date('c')]);
    airadio_clear_current_segment();
    airadio_write_json(AIRADIO_MEMORY_FILE, [
        'fingerprints' => [],
        'topics' => [],
        'recent_texts' => [],
        'updated_at' => date('c'),
    ]);
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

function airadio_tts_audio_path($text) {
    $text = trim((string)$text);
    if ($text === '') { throw new RuntimeException('tts_text_required'); }
    if (!is_dir(AIRADIO_TTS_CACHE_DIR)) { mkdir(AIRADIO_TTS_CACHE_DIR, 0775, true); }

    $endpoint = defined('AIRADIO_TTS_ENDPOINT') ? (string)AIRADIO_TTS_ENDPOINT : '';
    $hash = hash('sha256', $endpoint . "\n" . AIRADIO_TTS_VOICE . "\n" . AIRADIO_TTS_RATE . "\n" . AIRADIO_TTS_PITCH . "\n" . $text);
    $out = AIRADIO_TTS_CACHE_DIR . '/' . $hash . '.mp3';
    if (is_file($out) && filesize($out) > 1000) { return $out; }

    $payload = json_encode([
        'input' => $text,
        'voice' => AIRADIO_TTS_VOICE,
        'speed' => 1.1,
    ], JSON_UNESCAPED_UNICODE);
    if ($endpoint !== '') {
        $ctx = stream_context_create(['http' => [
            'method' => 'POST',
            'header' => "Content-Type: application/json\r\n",
            'content' => $payload,
            'timeout' => 45,
            'ignore_errors' => true,
        ]]);
        $audio = @file_get_contents($endpoint, false, $ctx);
        $contentType = '';
        if (isset($http_response_header) && is_array($http_response_header)) {
            foreach ($http_response_header as $line) {
                if (stripos($line, 'Content-Type:') === 0) {
                    $contentType = strtolower(trim(substr($line, 13)));
                    break;
                }
            }
        }
        if (is_string($audio) && strlen($audio) > 1000 && strpos($contentType, 'audio/') === 0) {
            file_put_contents($out, $audio, LOCK_EX);
            return $out;
        }
    }

    if (!is_file(AIRADIO_TTS_SCRIPT)) {
        throw new RuntimeException('tts_script_not_found: ' . AIRADIO_TTS_SCRIPT);
    }
    $cmd = 'env'
        . ' KURAGE_TTS_VOICE=' . escapeshellarg(AIRADIO_TTS_VOICE)
        . ' KURAGE_TTS_RATE=' . escapeshellarg(AIRADIO_TTS_RATE)
        . ' KURAGE_TTS_PITCH=' . escapeshellarg(AIRADIO_TTS_PITCH)
        . ' KURAGE_TTS_NORMALIZER_DIR=' . escapeshellarg('/home/kojima/work/kurage/backend')
        . ' ' . escapeshellarg(AIRADIO_TTS_PYTHON)
        . ' ' . escapeshellarg(AIRADIO_TTS_SCRIPT)
        . ' --output ' . escapeshellarg($out);
    $proc = proc_open($cmd, [
        0 => ['pipe', 'r'],
        1 => ['pipe', 'w'],
        2 => ['pipe', 'w'],
    ], $pipes, dirname(AIRADIO_TTS_SCRIPT));
    if (!is_resource($proc)) { throw new RuntimeException('tts_process_failed'); }
    fwrite($pipes[0], $payload);
    fclose($pipes[0]);
    $stdout = stream_get_contents($pipes[1]);
    fclose($pipes[1]);
    $stderr = stream_get_contents($pipes[2]);
    fclose($pipes[2]);
    $code = proc_close($proc);
    if ($code !== 0 || !is_file($out) || filesize($out) <= 1000) {
        @unlink($out);
        throw new RuntimeException('tts_failed: ' . substr((string)$stderr . ' ' . (string)$stdout, -1000));
    }
    return $out;
}

function airadio_prefetch_payload_path($reason) {
    $safeReason = preg_replace('/[^A-Za-z0-9_-]/', '_', (string)$reason);
    return AIRADIO_STORAGE_DIR . '/tts_prefetch_' . $safeReason . '_' . time() . '_' . substr(sha1((string)microtime(true)), 0, 8) . '.json';
}

function airadio_start_tts_prefetch($items, $reason = 'queue') {
    if (!is_array($items) || empty($items)) { return ''; }
    $limited = [];
    foreach ($items as $item) {
        if (!is_array($item)) { continue; }
        $text = trim((string)(isset($item['text']) ? $item['text'] : ''));
        if ($text === '') { continue; }
        $limited[] = [
            'id' => isset($item['id']) ? (string)$item['id'] : '',
            'title' => isset($item['title']) ? (string)$item['title'] : '',
            'text' => $text,
        ];
        if (count($limited) >= AIRADIO_TTS_PREFETCH_LIMIT) { break; }
    }
    if (empty($limited)) { return ''; }
    $payload = airadio_prefetch_payload_path($reason);
    airadio_write_json($payload, ['reason' => $reason, 'items' => $limited, 'created_at' => date('c')]);
    $php = getenv('AIRADIO_PHP_BINARY') ?: AIRADIO_PHP_BINARY;
    $cmd = sprintf(
        'cd %s && nohup %s %s --payload %s >> %s 2>&1 & echo $!',
        escapeshellarg(dirname(__DIR__)),
        escapeshellcmd($php),
        escapeshellarg(__DIR__ . '/tts_prefetch.php'),
        escapeshellarg($payload),
        escapeshellarg(AIRADIO_LOG_FILE)
    );
    $pid = trim((string)shell_exec($cmd));
    airadio_append_log('tts_prefetch_started', ['pid' => $pid, 'reason' => $reason, 'count' => count($limited)]);
    airadio_update_state(['tts_status' => 'prefetching', 'tts_prefetch_reason' => $reason]);
    return $pid;
}

function airadio_profile_from_session() {
    $profile = airadio_fetch_x_profile(AIRADIO_ALLOWED_USER);
    if (session_status() !== PHP_SESSION_ACTIVE) { @session_start(); }
    $profile['listener_username'] = AIRADIO_ALLOWED_USER;
    $profile['logged_in_user'] = isset($_SESSION['session_username']) ? $_SESSION['session_username'] : '';
    return $profile;
}

function airadio_fetch_x_profile($username) {
    $username = preg_replace('/[^A-Za-z0-9_]/', '', (string)$username);
    if ($username === '') { $username = AIRADIO_ALLOWED_USER; }
    $cache_file = AIRADIO_STORAGE_DIR . '/x_profile_' . $username . '.json';
    $cached = airadio_read_json($cache_file, []);
    if (!empty($cached['username']) && !empty($cached['description']) && isset($cached['cached_at']) && time() - (int)$cached['cached_at'] < 3600) {
        $cached['source'] = isset($cached['source']) ? $cached['source'] : 'fxtwitter_cache';
        return $cached;
    }
    $profile = [
        'username' => $username,
        'name' => $username,
        'description' => '',
        'source' => 'fxtwitter',
    ];
    $url = 'https://api.fxtwitter.com/' . rawurlencode($username);
    $ctx = stream_context_create(['http' => [
            'method' => 'GET',
            'header' => "User-Agent: KurageAIRadio/0.1\r\nAccept: application/json\r\n",
            'timeout' => 12,
            'ignore_errors' => true,
    ]]);
    $raw = @file_get_contents($url, false, $ctx);
    $json = json_decode($raw ? $raw : '{}', true);
    $user = isset($json['user']) && is_array($json['user']) ? $json['user'] : [];
    if (!empty($user)) {
        $description = '';
        if (isset($user['raw_description']['text'])) {
            $description = (string)$user['raw_description']['text'];
        } elseif (isset($user['description'])) {
            $description = (string)$user['description'];
        }
        $profile = [
            'username' => isset($user['screen_name']) ? (string)$user['screen_name'] : $username,
            'name' => isset($user['name']) ? (string)$user['name'] : $username,
            'description' => $description,
            'followers' => isset($user['followers']) ? (int)$user['followers'] : 0,
            'following' => isset($user['following']) ? (int)$user['following'] : 0,
            'tweets' => isset($user['tweets']) ? (int)$user['tweets'] : 0,
            'likes' => isset($user['likes']) ? (int)$user['likes'] : 0,
            'url' => isset($user['url']) ? (string)$user['url'] : 'https://x.com/' . $username,
            'source' => 'fxtwitter',
            'cached_at' => time(),
        ];
        airadio_write_json($cache_file, $profile);
    } elseif (!empty($cached)) {
        $cached['source'] = 'fxtwitter_cache_stale';
        return $cached;
    }
    return $profile;
}

function airadio_default_theme_from_profile($profile) {
    $username = isset($profile['username']) ? trim((string)$profile['username']) : '';
    $description = isset($profile['description']) ? trim((string)$profile['description']) : '';
    if ($username === 'xb_bittensor' || stripos($description, 'bittensor') !== false || stripos($description, 'Web3xAIxSNS') !== false) {
        return '編集者が学びたい、Bittensor、分散AI、AI Agent、Claude Code/Codex、バイブコーディング、Web3収益化を静かに深掘りする';
    }
    if ($description !== '') {
        return 'Xプロフィールに合わせて、AI活用、発信、収益化、実装のヒントを静かに深掘りする';
    }
    return '編集者が学びたい、AI Agent、バイブコーディング、分散AI、Web3収益化を静かに深掘りする';
}

function airadio_seed_profile_program($theme, $profile) {
    $username = isset($profile['username']) && $profile['username'] !== '' ? $profile['username'] : 'xb_bittensor';
    $now = time();
    $texts = [
        [
            'title' => 'プロフィールから始める',
            'text' => '今夜のKurageは、編集者が学びたいテーマを入口に、他のリスナーにも伝わる形で話します。Bittensor、分散AI、AI Agent、Claude CodeやCodex、そしてバイブコーディング。これらは別々の流行語ではなく、個人や小さな会社が、情報収集から実装、発信、収益化までを自分で回すための部品です。最初は、この部品をどうつなぐかから静かに見ていきます。',
            'source' => 'claude-seed-profile',
        ],
        [
            'title' => 'Bittensorを仕事の流れで見る',
            'text' => 'Bittensorを考えるとき、価格やトークンだけを見ると話が浅くなります。Kurageが注目したいのは、知能や推論、データ処理をネットワークとして扱う発想です。もしAI Agentが情報を集め、評価し、成果物を作るなら、その価値をどう測るのか。分散AIの文脈は、ここで実装と収益化の話につながります。',
            'source' => 'claude-seed-bittensor',
        ],
        [
            'title' => 'Claude CodeとCodexの使い分け',
            'text' => 'Claude CodeとCodexは、どちらが上かではなく、どこに置くかで考えると実用的です。Claudeには構成や判断、長い文脈の整理を任せる。Codexにはリポジトリを触りながら実装、テスト、コミットまで進めさせる。この二つを雑に混ぜるより、役割を分けたほうが失敗ログも残り、次の改善が楽になります。',
            'source' => 'claude-seed-tools',
        ],
        [
            'title' => 'バイブコーディングの本質',
            'text' => 'バイブコーディングは、気分でコードを書くことではありません。自然言語で目的を伝え、AIに作業させ、動作確認し、違和感を言葉にして戻す。この往復を速くする開発スタイルです。大事なのは、AIに丸投げすることではなく、成果物を見る目、修正を指示する言葉、そして作業ログを残す習慣です。',
            'source' => 'claude-seed-vibe',
        ],
        [
            'title' => '収益化は発信量から始まる',
            'text' => 'Web3やAIで稼ぐ話は派手に見えますが、最初の現実的なレバーは発信量です。調べたことをブログにし、短い動画にし、SNSで告知し、反応を見て次のテーマを決める。ここをAI Agentで半自動化できると、ひとりでも検証回数を増やせます。収益化は一発の正解より、検証回数の設計に近いです。',
            'source' => 'claude-seed-monetization',
        ],
        [
            'title' => 'Kurage AgentReachによる情報収集',
            'text' => '情報収集では、ただ検索結果を並べても価値になりません。Kurageが見るべきなのは、誰が何に反応しているか、どの切り口が伸びているか、そこから自分のプロダクトにどう接続できるかです。Kurage AgentReachは、話題を拾う入口であり、台本や実装タスクへ変換して初めて仕事になります。',
            'source' => 'claude-seed-research',
        ],
        [
            'title' => '失敗回避の設計',
            'text' => 'AI Agentを使うときの失敗は、賢さ不足だけではありません。同じ話を繰り返す、古いデータを読む、ログが残らない、確認せず投稿する。こうした失敗を避けるには、記憶、キュー、状態、レビューの層を分けます。今回のラジオでも、話した内容を記録し、同じ台本へ戻らないことが重要です。',
            'source' => 'claude-seed-risk',
        ],
        [
            'title' => '次の問い',
            'text' => '最後に、編集者とリスナーへ問いを置きます。Bittensor、AI Agent、バイブコーディングを、自分の発信やサービスに組み込むなら、最初に自動化する一手は何でしょうか。調査でしょうか、台本生成でしょうか、動画化でしょうか。Kurageは次の話題で、その一手を小さな実装単位に分けていきます。',
            'source' => 'claude-seed-question',
        ],
    ];
    $items = [];
    foreach ($texts as $i => $row) {
        $row['id'] = 'seed-' . $now . '-' . $i;
        $row['theme'] = $theme;
        $row['listener'] = $username;
        $row['created_at'] = date('c', $now);
        $items[] = $row;
    }
    return $items;
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

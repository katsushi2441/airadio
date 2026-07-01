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
        'theme' => '編集者が選ぶテーマを静かに深掘りするラジオ',
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
            'timeout' => 660,
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

function airadio_extract_github_repo_label($input) {
    $text = (string)$input;
    if (preg_match('~https?://github\.com/([^/\s]+)/([^/\s?#]+)~i', $text, $m)) {
        $repo = preg_replace('/\.git$/i', '', $m[2]);
        return $m[1] . '/' . $repo;
    }
    return '';
}

function airadio_theme_is_github_repo($input) {
    $text = trim((string)$input);
    if (airadio_extract_github_repo_label($text) !== '') { return true; }
    return preg_match('~^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\s|$)~', $text) === 1;
}

function airadio_spoken_theme_title($theme, $instruction = '') {
    $source = trim((string)$instruction) !== '' ? (string)$instruction : (string)$theme;
    if (airadio_extract_github_repo_label($source) !== '' || preg_match('~[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+~', (string)$theme)) {
        return 'このリポジトリ';
    }
    $spoken = preg_replace('~https?://[^\s「」『』"\'`<>]+~u', '', (string)$theme);
    $spoken = preg_replace('/\s+/u', ' ', $spoken);
    return trim($spoken) !== '' ? trim($spoken) : 'このテーマ';
}

function airadio_default_theme_from_profile($profile) {
    $description = isset($profile['description']) ? trim((string)$profile['description']) : '';
    if ($description !== '') {
        return 'Xプロフィールに合わせて、編集者が関心を持つテーマを静かに深掘りする';
    }
    return '編集者が選ぶテーマを静かに深掘りする';
}

function airadio_normalize_theme_request($input) {
    $text = trim((string)$input);
    if ($text === '') { return ''; }
    $repoLabel = airadio_extract_github_repo_label($text);
    $text = preg_replace('/[「」『』"\'`]/u', '', $text);
    $text = preg_replace('/\s+/u', ' ', $text);
    $patterns = [
        '/^(.+?)(?:という|っていう|といった)?テーマで(?:話して|話す|解説して|教えて|お願いします|ください)?[。.!！]*$/u',
        '/^(.+?)(?:を|について)(?:テーマにして|話して|解説して|教えて|お願いします|ください)[。.!！]*$/u',
        '/^(.+?)(?:を|について)(?:初心者向けに|入門向けに)?(?:話して|解説して|教えて|お願いします|ください)[。.!！]*$/u',
    ];
    foreach ($patterns as $pattern) {
        if (preg_match($pattern, $text, $m) && trim($m[1]) !== '') {
            $text = trim($m[1]);
            break;
        }
    }
    $text = preg_replace('/(?:という|っていう|といった)?テーマ$/u', '', $text);
    $text = preg_replace('/(?:を|について)$/u', '', $text);
    $text = preg_replace('/^[\s。、.!！?]+|[\s。、.!！?]+$/u', '', $text);
    if ($repoLabel !== '') {
        if ($text === '' || preg_match('#^https?://github\.com/#i', $text)) {
            return $repoLabel . ' の教材内容';
        }
        if (strpos($text, $repoLabel) === false) {
            return $repoLabel . ' の教材内容: ' . $text;
        }
    }
    return $text !== '' ? $text : trim((string)$input);
}

function airadio_theme_guidance($theme) {
    $theme = (string)$theme;
    if (airadio_theme_is_github_repo($theme)) {
        return 'GitHubリポジトリを一次資料として扱い、READMEとリポジトリ情報から重要点を判断して話す。資料にない文脈を勝手に足さない。';
    }
    if (preg_match('/入門|初心者|初級|はじめて|基礎/u', $theme)) {
        return '初心者向けに、専門用語を短く説明し、初めて聞く人が理解できる順番で話す。';
    }
    if (preg_match('/応用|実践/u', $theme)) {
        return '実践者向けに、具体的な手順、検証方法、失敗時の立て直しを中心に話す。';
    }
    return '入力されたテーマの意図を保ち、一般論に薄めず、資料や指示に沿って話す。';
}

function airadio_seed_profile_program($theme, $profile) {
    $username = isset($profile['username']) && $profile['username'] !== '' ? $profile['username'] : '編集者';
    $now = time();
    $texts = [[
        'title' => 'オープニング',
        'text' => '今夜は、プロフィールから見えてくる関心に沿って話します。具体的な中身は、集めた情報と台本生成の結果をもとに、順番に深めていきます。',
        'source' => 'profile-seed-opening',
    ]];
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

function airadio_seed_instruction_program($theme, $instruction, $guidance) {
    $now = time();
    $spoken = airadio_spoken_theme_title($theme, $instruction);
    $texts = [[
        'title' => $spoken,
        'text' => $spoken . 'について、資料の内容から順に見ていきます。まずは全体像、次に重要なポイント、最後に使いどころを整理します。',
        'source' => 'instruction-seed-opening',
    ]];
    $items = [];
    foreach ($texts as $i => $row) {
        $row['id'] = 'instruction-seed-' . $now . '-' . $i;
        $row['theme'] = $theme;
        $row['requested_theme'] = trim((string)$instruction);
        $row['created_at'] = date('c', $now);
        $items[] = $row;
    }
    return $items;
}

function airadio_start_worker($theme, $profile, $reason = 'manual', $extra = []) {
    $payload = AIRADIO_STORAGE_DIR . '/worker_payload.json';
    $data = array_merge([
        'theme' => $theme,
        'profile' => $profile,
        'reason' => $reason,
        'created_at' => date('c'),
    ], is_array($extra) ? $extra : []);
    airadio_write_json($payload, $data);
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

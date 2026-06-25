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

function airadio_reset_program_memory() {
    airadio_write_json(AIRADIO_QUEUE_FILE, ['items' => [], 'updated_at' => date('c')]);
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

function airadio_profile_from_session() {
    $profile = ['username' => '', 'name' => '', 'description' => '', 'source' => 'session'];
    if (session_status() !== PHP_SESSION_ACTIVE) { @session_start(); }
    $profile['username'] = isset($_SESSION['session_username']) ? $_SESSION['session_username'] : '';
    $token = isset($_SESSION['session_access_token']) ? $_SESSION['session_access_token'] : '';
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

function airadio_default_theme_from_profile($profile) {
    $username = isset($profile['username']) ? trim((string)$profile['username']) : '';
    $description = isset($profile['description']) ? trim((string)$profile['description']) : '';
    if ($username === 'xb_bittensor' || stripos($description, 'bittensor') !== false) {
        return 'xb_bittensor向けに、Bittensor、分散AI、AI Agent、Claude Code/Codex、バイブコーディング、Web3収益化を静かに深掘りする';
    }
    if ($description !== '') {
        return 'Xプロフィールに合わせて、AI活用、発信、収益化、実装のヒントを静かに深掘りする';
    }
    return 'xb_bittensor向けに、AI Agent、バイブコーディング、分散AI、Web3収益化を静かに深掘りする';
}

function airadio_seed_profile_program($theme, $profile) {
    $username = isset($profile['username']) && $profile['username'] !== '' ? $profile['username'] : 'xb_bittensor';
    $now = time();
    $texts = [
        [
            'title' => 'プロフィールから始める',
            'text' => 'xb_bittensorさん、今夜のKurageは、ただAIニュースを読むのではなく、あなたの関心に合わせて話します。Bittensor、分散AI、AI Agent、Claude CodeやCodex、そしてバイブコーディング。これらは別々の流行語ではなく、個人や小さな会社が、情報収集から実装、発信、収益化までを自分で回すための部品です。最初は、この部品をどうつなぐかから静かに見ていきます。',
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
            'title' => 'kagentreach的な情報収集',
            'text' => '情報収集では、ただ検索結果を並べても価値になりません。Kurageが見るべきなのは、誰が何に反応しているか、どの切り口が伸びているか、そこから自分のプロダクトにどう接続できるかです。kagentreachのような収集系は、話題を拾う入口であり、台本や実装タスクへ変換して初めて仕事になります。',
            'source' => 'claude-seed-research',
        ],
        [
            'title' => '失敗回避の設計',
            'text' => 'AI Agentを使うときの失敗は、賢さ不足だけではありません。同じ話を繰り返す、古いデータを読む、ログが残らない、確認せず投稿する。こうした失敗を避けるには、記憶、キュー、状態、レビューの層を分けます。今回のラジオでも、話した内容を記録し、同じ台本へ戻らないことが重要です。',
            'source' => 'claude-seed-risk',
        ],
        [
            'title' => '次の問い',
            'text' => '最後に、xb_bittensorさんへ問いを置きます。Bittensor、AI Agent、バイブコーディングを、自分の発信やサービスに組み込むなら、最初に自動化する一手は何でしょうか。調査でしょうか、台本生成でしょうか、動画化でしょうか。Kurageは次の話題で、その一手を小さな実装単位に分けていきます。',
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

<?php
// =========================================
// airadio.php
// ニュース → 5分ラジオ台本生成（Ollama）→ 音声生成（TTS API）
// =========================================

// -------------------------
// 設定
// -------------------------
date_default_timezone_set("Asia/Tokyo");

// Google News RSS（デフォルト）
define("NEWS_RSS", "https://news.google.com/rss?hl=ja&gl=JP&ceid=JP:ja");

// Ollama
define("OLLAMA_URL", "https://exbridge.ddns.net/api/generate");
define("OLLAMA_MODEL", "gemma3:12b");

// TTS（成功していたまま）
define("TTS_URL", "http://exbridge.ddns.net:8002/tts");

// 生成するニュース件数
define("NEWS_LIMIT", 8);

// -------------------------
// VOICE プロファイル読込
// -------------------------
$voice_profile = [
    "speaker" => 2,
    "speed" => 1.0,
    "pitch" => 0.0,
    "intonation" => 1.0,
    "volume" => 1.0,
];

$profile_file = __DIR__ . "/voice_profile.json";
if (file_exists($profile_file)) {
    $json = json_decode(file_get_contents($profile_file), true);
    if (is_array($json)) {
        $voice_profile = array_merge($voice_profile, $json);
    }
}

// -------------------------
// ユーティリティ
// -------------------------
function append_audio_log($audio_url, $keyword, $script) {
    $logFile = __DIR__ . "/airadio_log.json";

    $list = [];
    if (file_exists($logFile)) {
        $json = file_get_contents($logFile);
        $list = json_decode($json, true);
        if (!is_array($list)) $list = [];
    }

    $path = parse_url($audio_url, PHP_URL_PATH);
    $file = basename($path);

    $list[] = [
        "file" => $file,
        "datetime" => date("Y-m-d H:i:s"),
        "keyword" => $keyword,
        "script" => $script
    ];

    file_put_contents(
        $logFile,
        json_encode($list, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT)
    );
}

function http_get($url, $timeout = 15) {
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_FOLLOWLOCATION => true,
        CURLOPT_TIMEOUT => $timeout,
        CURLOPT_CONNECTTIMEOUT => $timeout,
        CURLOPT_USERAGENT => "airadio.php/1.0",
        CURLOPT_SSL_VERIFYPEER => true,
        CURLOPT_SSL_VERIFYHOST => 2,
    ]);
    $res = curl_exec($ch);
    $err = curl_error($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    if ($res === false) return [false, "curl_error: ".$err, $code];
    if ($code < 200 || $code >= 300) return [false, "http_status: ".$code, $code];
    return [true, $res, $code];
}

function http_post_json($url, $payload, $timeout = 60) {
    $ch = curl_init($url);
    $json = json_encode($payload, JSON_UNESCAPED_UNICODE);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_FOLLOWLOCATION => true,
        CURLOPT_TIMEOUT => $timeout,
        CURLOPT_CONNECTTIMEOUT => 15,
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => $json,
        CURLOPT_HTTPHEADER => [
            "Content-Type: application/json",
            "Accept: application/json",
        ],
    ]);
    $res = curl_exec($ch);
    $err = curl_error($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    if ($res === false) return [false, "curl_error: ".$err, $code, null];
    $data = json_decode($res, true);





    return [($code >= 200 && $code < 300), $res, $code, $data];
}

function fetch_news_items() {

    $rss = NEWS_RSS;

    if (isset($_POST["keyword"]) && $_POST["keyword"] !== "") {
        $rss = "https://news.google.com/rss/search?q="
             . urlencode($_POST["keyword"])
             . "&hl=ja&gl=JP&ceid=JP:ja";
    }

    list($ok, $body, $code) = http_get($rss, 20);
    if (!$ok) return [false, "RSS取得失敗: ".$body, []];

    libxml_use_internal_errors(true);
    $xml = simplexml_load_string($body);
    if ($xml === false) return [false, "RSS解析失敗", []];

    $items = [];
    if (!isset($xml->channel->item)) return [true, "", []];

    $count = 0;
    foreach ($xml->channel->item as $item) {
        $title = trim((string)$item->title);
        $link  = trim((string)$item->link);
        $pub   = trim((string)$item->pubDate);
        if ($title === "" || $link === "") continue;

        $items[] = [
            "title" => $title,
            "link" => $link,
            "pubDate" => $pub,
        ];
        $count++;
        if ($count >= NEWS_LIMIT) break;
    }
    return [true, "", $items];
}

function build_prompt($news_items) {
    global $keyword;
    $today = date("Y-m-d H:i");
    $lines = [];
    $i = 1;
    foreach ($news_items as $n) {
        $lines[] = $i.". ".$n["title"]." (".$n["pubDate"].")";
        $lines[] = "   ".$n["link"];
        $i++;
    }
    $news_text = implode("\n", $lines);

    $prompt = "
あなたはプロのラジオ構成作家です。
以下のニュース一覧を参考に、約5分番組用の
【実際にそのまま読み上げる日本語のセリフ本文】だけを作ってください。

# 今日の日時
{$today}

# ニュース一覧（参考）
{$news_text}

# 条件
- 尺は約5分。文字数の目安は1200〜1700文字。
- 口語で、聞き取りやすい短文を中心にする。
- 構成は「自然な導入 → 今日の注目トピック3本 → 小ネタ1本 → まとめ」の流れにする。
- ニュース内容は断定しすぎず、「〜と報じられています」「〜の可能性があります」など慎重な表現を使う。
- 一般の日本語話者に分かるよう、専門用語は噛み砕いて説明する。

# 出力形式に関する最重要ルール
- あなたは質問に答えたり、指示に返事をする存在ではない。
- これから出力する文章は「完成済みのラジオ原稿」であり、会話ではない。
- 読者や依頼者、指示内容に言及してはいけない。
- 出力の冒頭で、挨拶、返答、前置き、断り書き、確認文を一切書いてはいけない。

# 冒頭文に関する絶対ルール
- 冒頭に挨拶を入れてはいけない。
- 聞き手の感情や思考を推測する表現を書いてはいけない。
- 「お伝えします」「ご紹介します」など説明者視点の文を冒頭に使ってはいけない。
- 冒頭の一文は、番組のテーマを端的に示す事実ベースの文にすること。

# 出力に関する厳格な制限（最重要）
- 説明文、演出指示、ト書きは一切書かない。
- 「オープニング」「エンディング」「BGM」「SE」「パーソナリティ」などの語を使わない。
- 括弧（ ）やコロン「：」を使わない。
- 見出し、箇条書き、記号、強調表現を使わない。
- URLや注釈を書かない。
- 出力は【人がそのまま音声で読み上げるセリフ本文のみ】に限定する。

# 絶対禁止事項
- 「はい」「承知しました」「了解です」「わかりました」「以下が」「それでは」などの
  指示に対する返答・前置き・開始宣言を一切書いてはいけない。
- 「これから」「今回」「本日は」「ご紹介します」などのメタ的な導入表現を書いてはいけない。

# 開始条件（厳守）
- 出力は必ず、番組本文の最初のセリフから書き始めること。
- 先頭の一文は、すぐに内容に入る自然な日本語の文章にすること。
- 先頭の文字は必ず日本語の本文から始めること。

# 開始文（この一文から必ず書き始めること・改変禁止）
- {$keyword}に関するニュースです。
";

    return $prompt;
}

function ollama_generate_script($prompt) {
    $payload = [
        "model" => OLLAMA_MODEL,
        "prompt" => $prompt,
        "stream" => false,
        "options" => [
            "temperature" => 0.7,
        ],
    ];
    list($ok, $raw, $code, $data) = http_post_json(OLLAMA_URL, $payload, 120);
    if (!$ok || !is_array($data) || !isset($data["response"])) {
        $msg = "Ollama生成失敗 (HTTP {$code})";
        if (is_string($raw) && $raw !== "") $msg .= " / ".$raw;
        return [false, $msg, ""];
    }
    $text = trim($data["response"]);
    return [true, "", $text];
}

function tts_generate_audio($text) {
    global $voice_profile;

    $payload = [
        "text" => $text,
        "speaker" => (int)$voice_profile["speaker"],
        "speed" => (float)$voice_profile["speed"],
        "pitch" => (float)$voice_profile["pitch"],
        "intonation" => (float)$voice_profile["intonation"],
        "volume" => (float)$voice_profile["volume"],
    ];

    list($ok, $raw, $code, $data) = http_post_json(TTS_URL, $payload, 120);
    if (!$ok || !is_array($data)) {
        $msg = "TTS失敗 (HTTP {$code})";
        if (is_string($raw) && $raw !== "") $msg .= " / ".$raw;
        return [false, $msg, ""];
    }

    if (isset($data["audio_url"]) && is_string($data["audio_url"])) {
        return [true, "", $data["audio_url"]];
    }
    if (isset($data["url"]) && is_string($data["url"])) {
        return [true, "", $data["url"]];
    }
    return [false, "TTS応答に audio_url がありません: ".$raw, ""];
}

// -------------------------
// メイン処理
// -------------------------
$err = "";
$news_items = [];
$script = "";
$audio_url = "";
$keyword = isset($_POST["keyword"]) ? (string)$_POST["keyword"] : "";


// -------------------------
// file指定で台本を読み込む
// -------------------------
if (isset($_GET["file"]) && $_GET["file"] !== "") {
    $target = basename($_GET["file"]);
    $logFile = __DIR__ . "/airadio_log.json";

    if (file_exists($logFile)) {
        $list = json_decode(file_get_contents($logFile), true);
        if (is_array($list)) {
            foreach ($list as $row) {
                if (isset($row["file"]) && $row["file"] === $target) {
                    if (isset($row["script"])) {
                        $script = $row["script"];
                    }
                    break;
                }
            }
        }
    }
}

// -------------------------
// 台本の更新保存（airadio.php メイン処理）
// -------------------------
if (isset($_POST["save_script"])) {

    $file = isset($_POST["file"]) ? basename((string)$_POST["file"]) : "";
    $script = isset($_POST["script"]) ? trim((string)$_POST["script"]) : "";

    $logFile = __DIR__ . "/airadio_log.json";

    if ($file !== "" && file_exists($logFile)) {

        $list = json_decode(file_get_contents($logFile), true);

        if (is_array($list)) {

            foreach ($list as &$row) {

                if (
                    isset($row["file"])
                    && $row["file"] === $file
                ) {
                    $row["script"] = $script;
                    $row["datetime"] = date("Y-m-d H:i:s");
                    break;
                }

            }

            file_put_contents(
                $logFile,
                json_encode(
                    $list,
                    JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT
                )
            );
        }
    }
}



if (isset($_POST["generate"])) {
    list($ok, $msg, $news_items) = fetch_news_items();
    if (!$ok) {
        $err = $msg;
    } else {
        $prompt = build_prompt($news_items);
        list($ok2, $msg2, $script) = ollama_generate_script($prompt);
        if (!$ok2) $err = $msg2;
    }
}

if (isset($_POST["tts"])) {
    $script = isset($_POST["script"]) ? trim((string)$_POST["script"]) : "";
    if ($script === "") {
        $err = "台本が空です";
    } else {
        list($ok3, $msg3, $audio_url) = tts_generate_audio($script);
        if (!$ok3) {
            $err = $msg3;
        } else {
            append_audio_log(
                $audio_url,
                isset($_POST["keyword"]) ? (string)$_POST["keyword"] : "",
                $script
            );
        }

    }
}
?>
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>ニュースラジオ生成</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
/* ===============================
   Web3 Navy / Metallic UI
   構造・機能変更なし
=============================== */

body {
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    background:
        radial-gradient(1200px 600px at 10% -10%, #1e3a8a33, transparent 40%),
        radial-gradient(800px 400px at 90% 10%, #0ea5e933, transparent 35%),
        linear-gradient(180deg, #020617 0%, #020617 100%);
    color: #e5e7eb;
    padding: 16px;
}

.wrap {
    max-width: 980px;
    margin: 0 auto;
}

/* ガラス＋メタリック */
.card {
    background:
        linear-gradient(
            135deg,
            rgba(30, 58, 138, 0.35),
            rgba(15, 23, 42, 0.65)
        );
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 16px;
    padding: 16px;
    margin-bottom: 14px;
    backdrop-filter: blur(10px);
    box-shadow:
        0 10px 30px rgba(2, 6, 23, 0.6),
        inset 0 1px 0 rgba(255,255,255,0.04);
}

h1 {
    font-size: 18px;
    margin: 0 0 10px;
    font-weight: 700;
    letter-spacing: 0.3px;
    color: #f8fafc;
}

/* ボタン（Web3っぽい発光） */
.btn {
    border: 0;
    background:
        linear-gradient(135deg, #2563eb, #0ea5e9);
    color: #ffffff;
    padding: 10px 16px;
    border-radius: 12px;
    cursor: pointer;
    font-weight: 600;
    box-shadow:
        0 6px 18px rgba(37, 99, 235, 0.45);
}

.btn:hover {
    filter: brightness(1.08);
}

.btn2 {
    border: 1px solid rgba(148, 163, 184, 0.4);
    background: rgba(2, 6, 23, 0.6);
    color: #e5e7eb;
    padding: 10px 16px;
    border-radius: 12px;
    cursor: pointer;
    font-weight: 500;
}

.btn2:hover {
    background: rgba(15, 23, 42, 0.8);
}

/* 入力系 */
input[type="text"],
textarea {
    width: 100%;
    background: rgba(2, 6, 23, 0.7);
    color: #e5e7eb;
    border-radius: 12px;
    border: 1px solid rgba(148, 163, 184, 0.35);
    padding: 10px;
    font-size: 14px;
    line-height: 1.6;
}

textarea {
    min-height: 260px;
}

input::placeholder,
textarea::placeholder {
    color: #94a3b8;
}

/* テキスト */
.muted {
    color: #94a3b8;
    font-size: 13px;
}

.err {
    color: #f87171;
    font-weight: 600;
}

/* リスト */
ul {
    margin: 8px 0 0 18px;
}

li {
    margin-bottom: 8px;
}

/* リンク */
a {
    color: #38bdf8;
    text-decoration: none;
}

a:hover {
    text-decoration: underline;
}

/* レイアウト */
.row {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    align-items: center;
}

/* audio */
audio {
    background: rgba(2, 6, 23, 0.6);
    border-radius: 10px;
}

/* ===============================
   Top Navigation
=============================== */
.top-nav {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    margin-bottom: 14px;
}

.top-nav a {
    display: inline-block;
    padding: 8px 14px;
    border-radius: 10px;
    font-size: 13px;
    font-weight: 600;
    color: #e5e7eb;
    text-decoration: none;
    background: rgba(2, 6, 23, 0.55);
    border: 1px solid rgba(148, 163, 184, 0.35);
    backdrop-filter: blur(8px);
}

.top-nav a:hover {
    background: rgba(30, 58, 138, 0.45);
}

</style>
</head>
<body>
<div class="wrap">
<div class="top-nav">
    <a href="airadio.php">News2Audio</a>
    <a href="voicebox_ui.php">Voicebox UI</a>
    <a href="bgm_manager.php">BGM Manager</a>
    <a href="ttsfile.php">TTS Files</a>
    <a href="audio2mp4.php">Audio2MP4</a>
    <a href="video2mp4.php">Video2MP4</a>
</div>


    <div class="card">
        <h1>指定したキーワードに関連するニュースからラジオ生成</h1>
        <div class="muted">
        1. キーワードで検索されたニュース取得 -> 2. AIで台本生成 -> 3. TTSで音声生成
        </div>
        <?php if ($err !== ""): ?>
            <div class="err" style="margin-top:10px;"><?php echo htmlspecialchars($err, ENT_QUOTES, "UTF-8"); ?></div>
        <?php endif; ?>
        <form method="post" class="row" style="margin-top:12px;">
            <input type="text" name="keyword"
                   value="<?php echo isset($_POST['keyword']) ? htmlspecialchars($_POST['keyword'], ENT_QUOTES, 'UTF-8') : ''; ?>"
                   placeholder="検索キーワード">
            <button class="btn" type="submit" name="generate" value="1">キーワード検索したニュースから台本を生成</button>
        </form>
    </div>

    <?php if (!empty($news_items)): ?>
    <div class="card">
        <div style="font-weight:700; margin-bottom:6px;">参考ニュース（<?php echo count($news_items); ?>件）</div>
        <ul>
            <?php foreach ($news_items as $n): ?>
                <li>
                    <?php echo htmlspecialchars($n["title"], ENT_QUOTES, "UTF-8"); ?>
                    <div class="muted"><?php echo htmlspecialchars($n["pubDate"], ENT_QUOTES, "UTF-8"); ?></div>
                    <div><a href="<?php echo htmlspecialchars($n["link"], ENT_QUOTES, "UTF-8"); ?>" target="_blank" rel="noopener">記事を開く</a></div>
                </li>
            <?php endforeach; ?>
        </ul>
    </div>
    <?php endif; ?>

    <div class="card">
        <div style="font-weight:700; margin-bottom:6px;">台本（編集可）</div>
        <form method="post">
            <input type="hidden" name="keyword"
                   value="<?php echo isset($_POST['keyword']) ? htmlspecialchars($_POST['keyword'], ENT_QUOTES, 'UTF-8') : ''; ?>">
            <textarea name="script"><?php echo htmlspecialchars($script, ENT_QUOTES, "UTF-8"); ?></textarea>
            <input type="hidden" name="file"
       value="<?php echo isset($_GET["file"]) ? htmlspecialchars($_GET["file"], ENT_QUOTES, 'UTF-8') : ''; ?>">

            <div class="row" style="margin-top:10px;">
                <button class="btn2" type="submit" name="tts" value="1">台本から音声生成</button>
                <button class="btn" type="submit" name="save_script" value="1">
台本を保存
</button>

            </div>
        </form>

        <?php if ($audio_url !== ""): ?>
            <hr>
            <div class="muted" style="margin-bottom:6px;">
                TTS音声URL：
                <a href="<?php echo htmlspecialchars($audio_url, ENT_QUOTES, "UTF-8"); ?>"
                   target="_blank" rel="noopener">
                    <?php echo htmlspecialchars($audio_url, ENT_QUOTES, "UTF-8"); ?>
                </a>
            </div>
            <audio controls style="width:100%;">
                <source src="<?php echo htmlspecialchars($audio_url, ENT_QUOTES, "UTF-8"); ?>">
            </audio>
        <?php endif; ?>
    </div>

</div>
</body>
</html>



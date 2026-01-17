<?php
// ================================
// ttsfile.php
// TTS音声ファイル管理（一覧 / 再生 / 削除 / Blogger投稿）
// ================================

date_default_timezone_set("Asia/Tokyo");

// -------------------------------
// API: airadio_log.json 追記
// -------------------------------
if (
    $_SERVER["REQUEST_METHOD"] === "POST"
    && isset($_SERVER["CONTENT_TYPE"])
    && strpos($_SERVER["CONTENT_TYPE"], "application/json") !== false
) {
    $raw = file_get_contents("php://input");
    $data = json_decode($raw, true);

    if (is_array($data) && isset($data["mode"]) && $data["mode"] === "append_log") {

        if (
            isset($data["audio_url"])
            && isset($data["keyword"])
            && isset($data["script"])
        ) {
            $logFile = __DIR__ . "/airadio_log.json";

            $list = array();
            if (file_exists($logFile)) {
                $json = json_decode(file_get_contents($logFile), true);
                if (is_array($json)) {
                    $list = $json;
                }
            }

            $path = parse_url($data["audio_url"], PHP_URL_PATH);
            $file = basename($path);

            $list[] = array(
                "file"     => $file,
                "datetime" => date("Y-m-d H:i:s"),
                "keyword"  => (string)$data["keyword"],
                "script"   => (string)$data["script"]
            );

            file_put_contents(
                $logFile,
                json_encode($list, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT)
            );

            header("Content-Type: application/json");
            echo json_encode(array("ok" => true));
            exit;
        }

        header("Content-Type: application/json");
        echo json_encode(array(
            "ok" => false,
            "error" => "invalid payload"
        ));
        exit;
    }
}




define("TTS_API_BASE", "http://exbridge.ddns.net:8002");
define("TTS_AUDIO_BASE", "https://exbridge.ddns.net/aidexx");
define("MIXED_AUDIO_BASE", "https://exbridge.ddns.net/aidexx/mixed");

function url_exists($url) {
    $headers = @get_headers($url);
    if (!is_array($headers)) return false;
    return (strpos($headers[0], "200") !== false);
}

function http_get_json($url) {
    $ch = curl_init($url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_TIMEOUT, 15);
    $res = curl_exec($ch);
    curl_close($ch);
    return json_decode($res, true);
}

function http_post_json($url, $payload) {
    $ch = curl_init($url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_TIMEOUT, 30);
    curl_setopt($ch, CURLOPT_HTTPHEADER, array("Content-Type: application/json"));
    curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($payload, JSON_UNESCAPED_UNICODE));
    $res = curl_exec($ch);
    curl_close($ch);
    return json_decode($res, true);
}

$msg  = "";
$res  = null;
$file = "";

// ----------------
// 削除
// ----------------
if (isset($_POST["delete"])) {
    http_post_json(
        TTS_API_BASE . "/delete",
        array("file" => $_POST["delete"])
    );
    header("Location: ".$_SERVER["PHP_SELF"]);
    exit;
}

// ----------------
// 台本ログ（PHPサーバ側）
// ----------------
$scriptMap = array();
$logFile = __DIR__ . "/airadio_log.json";

if (file_exists($logFile)) {
    $json = json_decode(file_get_contents($logFile), true);
    if (is_array($json)) {
        foreach ($json as $row) {
            if (isset($row["file"])) {
                if (isset($row["script"])) {
                    $scriptMap[$row["file"]] = $row["script"];
                } else {
                    $scriptMap[$row["file"]] = "";
                }
            }
        }
    }
}

// ----------------
// Blogger投稿
// ----------------
if (isset($_POST["send_blog"])) {
    $file = basename((string)$_POST["send_blog"]);

    $script = "";
    if (isset($scriptMap[$file])) {
        $script = $scriptMap[$file];
    }

    $res = http_post_json(
        TTS_API_BASE . "/blogger",
        array(
            "file"   => $file,
            "script" => $script
        )
    );

    if (is_array($res) && isset($res["ok"]) && $res["ok"]) {
        $msg = "✅ Bloggerに投稿しました: " . htmlspecialchars($file, ENT_QUOTES, "UTF-8");
    } else {
        $msg = "❌ 投稿失敗<br><pre>" .
               htmlspecialchars(
                   json_encode($res, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT),
                   ENT_QUOTES,
                   "UTF-8"
               ) .
               "</pre>";
    }
}

// ----------------
// TTSファイル一覧
// ----------------
$files = http_get_json(TTS_API_BASE . "/files");
if (!is_array($files)) {
    $files = array();
}
?>
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>TTSファイル管理</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body {
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    background:#f6f7f9;
    padding:16px;
}
.wrap {
    max-width: 980px;
    margin: 0 auto;
}
.card {
    background:#fff;
    border:1px solid #e5e7eb;
    border-radius:14px;
    padding:14px;
}
h1 {
    font-size:18px;
    margin:0 0 12px;
}
table {
    width:100%;
    border-collapse:collapse;
}
th, td {
    padding:8px;
    border-bottom:1px solid #e5e7eb;
    font-size:14px;
    vertical-align:middle;
}
th {
    text-align:left;
    background:#f9fafb;
}
audio {
    width:220px;
}
.btn-blog {
    background:#2563eb;
    color:#fff;
    border:0;
    padding:6px 10px;
    border-radius:8px;
    cursor:pointer;
}
.btn-del {
    background:#b91c1c;
    color:#fff;
    border:0;
    padding:6px 10px;
    border-radius:8px;
    cursor:pointer;
}
.muted {
    color:#6b7280;
    font-size:12px;
}
.msg {
    margin-bottom:10px;
    font-weight:600;
}
/* ================================
   スマホ対応（CSSのみ）
================================ */
@media screen and (max-width: 768px) {

    table,
    thead,
    tbody,
    tr,
    th,
    td {
        display: block;
        width: 100%;
    }

    thead {
        display: none;
    }

    tr {
        margin-bottom: 16px;
        padding: 12px;
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        background: #fff;
    }

    td {
        border: none;
        padding: 6px 0;
    }

    td a {
        word-break: break-all;
    }

    audio {
        width: 100%;
    }

    .muted {
        font-size: 13px;
        line-height: 1.6;
        max-height: 4.8em;   /* 約3行 */
        overflow: hidden;
    }

    .btn-blog,
    .btn-del {
        width: 100%;
        margin-top: 6px;
    }
}

</style>
</head>
<body>
<div class="wrap">
<div class="card">

<h1>TTS音声ファイル管理</h1>

<?php if ($msg !== ""): ?>
<div class="msg"><?php echo $msg; ?></div>
<?php endif; ?>

<table>
<tr>
<th>ファイル名</th>
<th>台本（冒頭）</th>
<th>再生</th>
<th>操作</th>
</tr>

<?php foreach ($files as $f): ?>
<tr>
<td>
<a href="airadio.php?file=<?php echo urlencode($f["file"]); ?>">
<?php echo htmlspecialchars($f["file"], ENT_QUOTES, "UTF-8"); ?>
</a>
</td>

<td class="muted">
<?php
$script = "";
if (isset($scriptMap[$f["file"]])) {
    $script = $scriptMap[$f["file"]];
}
$short = mb_substr($script, 0, 50);
echo htmlspecialchars($short, ENT_QUOTES, "UTF-8");
if (mb_strlen($script) > 50) {
    echo "…";
}
?>
</td>
<td>
<?php
$ttsFile  = $f["file"];
$base     = pathinfo($ttsFile, PATHINFO_FILENAME);
$mixedMp3 = $base . ".mp3";

$mixedUrl = MIXED_AUDIO_BASE . "/" . $mixedMp3;

if (url_exists($mixedUrl)) {
    $playUrl = $mixedUrl;
    $label   = "🎵 BGM MIX";
    $name    = $mixedMp3;
} else {
    $playUrl = TTS_AUDIO_BASE . "/tts/" . $ttsFile;
    $label   = "tts";
    $name    = $ttsFile;
}
?>
<div class="muted">
<?php echo htmlspecialchars($label . ": " . $name, ENT_QUOTES, "UTF-8"); ?>
</div>
<audio controls>
    <source src="<?php echo htmlspecialchars($playUrl, ENT_QUOTES, "UTF-8"); ?>">
</audio>
</td>

<td>
<form method="post" style="display:inline;">
<button class="btn-blog"
        name="send_blog"
        value="<?php echo htmlspecialchars($f["file"], ENT_QUOTES, "UTF-8"); ?>">
Blogger投稿
</button>
</form>
<form method="post"
      style="display:inline;"
      onsubmit="return confirm('削除しますか？');">
<button class="btn-del"
        name="delete"
        value="<?php echo htmlspecialchars($f["file"], ENT_QUOTES, "UTF-8"); ?>">
削除
</button>
</form>
</td>
</tr>
<?php endforeach; ?>

</table>

</div>
</div>
</body>
</html>



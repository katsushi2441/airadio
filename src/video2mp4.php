<?php


// =========================================
// audio2mp4.php
// 画像 + mp3/wav URL + ラジオ台本 → mp4 生成（スクロール対応）
// + 音声ファイル事前アップロード（専用ボタン）
// PHP5互換 / 機能削除なし
// =========================================

date_default_timezone_set("Asia/Tokyo");

define("API_ENDPOINT", "http://exbridge.ddns.net:8002/audio_to_video_mp4");


$musicDir = __DIR__ . "/musics";
$musicUrlBase = "https://airadio.exbridge.jp/musics";

if (!is_dir($musicDir)) {
    mkdir($musicDir, 0755, true);
}

$msg = "";
$result = null;
$audio_url = "";

/* =========================
   音声アップロード専用処理
========================= */
if (
    $_SERVER["REQUEST_METHOD"] === "POST"
    && isset($_POST["upload_audio"])
) {
    if (
        isset($_FILES["audio_file"])
        && isset($_FILES["audio_file"]["tmp_name"])
        && $_FILES["audio_file"]["tmp_name"] !== ""
    ) {
        $org_name = isset($_FILES["audio_file"]["name"]) ? $_FILES["audio_file"]["name"] : "";
        $tmp_path = $_FILES["audio_file"]["tmp_name"];

        $ext = strtolower(trim(pathinfo($org_name, PATHINFO_EXTENSION)));

        $mime = "";
        if (function_exists("mime_content_type")) {
            $mime = @mime_content_type($tmp_path);
        }

        // MIMEから拡張子推定（拡張子が取れない/変な場合の救済）
        $mime_to_ext = "";
        if ($mime !== "") {
            $m = strtolower(trim($mime));
            if ($m === "audio/mpeg" || $m === "audio/mp3" || $m === "audio/x-mp3" || $m === "audio/mpeg3") {
                $mime_to_ext = "mp3";
            }
            if (
                $m === "audio/wav"
                || $m === "audio/x-wav"
                || $m === "audio/wave"
                || $m === "audio/x-pn-wav"
                || $m === "application/octet-stream"
            ) {
            }
        }

        if ($ext === "mpeg") $ext = "mp3";

        $is_mp3 = false;
        $is_wav = false;

        if ($ext === "mp3") $is_mp3 = true;
        if ($ext === "wav") $is_wav = true;

        if (!$is_mp3 && !$is_wav && $mime_to_ext === "mp3") {
            $ext = "mp3";
            $is_mp3 = true;
        }

        if ($is_mp3 || $is_wav) {
            $saveName = "music." . $ext;
            $savePath = $musicDir . "/" . $saveName;

            if (move_uploaded_file($tmp_path, $savePath)) {
                $audio_url = $musicUrlBase . "/" . $saveName;
                $msg = "✅ 音声アップロード完了";
            } else {
                $msg = "❌ 音声ファイルの保存に失敗しました";
            }
        } else {
            $msg = "❌ mp3 または wav のみ対応しています"
                 . "<br>ファイル名: " . htmlspecialchars($org_name, ENT_QUOTES, "UTF-8")
                 . "<br>拡張子判定: " . htmlspecialchars($ext, ENT_QUOTES, "UTF-8")
                 . "<br>MIME判定: " . htmlspecialchars($mime, ENT_QUOTES, "UTF-8");
        }
    } else {
        $msg = "❌ 音声ファイルを選択してください";
    }
}

/* =========================
   MP4生成処理
========================= */
if (
    $_SERVER["REQUEST_METHOD"] === "POST"
    && !isset($_POST["upload_audio"])
) {

    if (
        isset($_FILES["image"])
        && isset($_POST["audio_url"])
        && isset($_POST["script_text"])
        && isset($_FILES["image"]["tmp_name"])
        && $_FILES["image"]["tmp_name"] !== ""
        && trim($_POST["audio_url"]) !== ""
    ) {

        $audio_url   = trim($_POST["audio_url"]);
        $script_text = trim($_POST["script_text"]);

        $ch = curl_init(API_ENDPOINT);

        $post = array(
            "audio_url"   => $audio_url,
            "script_text" => $script_text,
            "image" => new CURLFile(
                $_FILES["image"]["tmp_name"],
                mime_content_type($_FILES["image"]["tmp_name"]),
                $_FILES["image"]["name"]
            )
        );
        

        curl_setopt($ch, CURLOPT_POST, true);
        curl_setopt($ch, CURLOPT_POSTFIELDS, $post);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_TIMEOUT, 300);

        $res = curl_exec($ch);
        $err = curl_error($ch);
        curl_close($ch);

        if ($res === false) {
            $msg = "❌ API通信失敗: " . htmlspecialchars($err, ENT_QUOTES, "UTF-8");
        } else {
            $json = json_decode($res, true);
            if (is_array($json) && isset($json["ok"]) && $json["ok"]) {
                $result = $json;
                $msg = "✅ MP4生成完了";
            } else {
                $msg = "❌ 生成失敗<br><pre>" .
                    htmlspecialchars($res, ENT_QUOTES, "UTF-8") .
                    "</pre>";
            }
        }

    } else {
        $msg = "❌ 画像・音声URL・台本をすべて指定してください";
    }
}
?>
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>音声＋台本 → MP4</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
/* ===============================
   Web3 Navy / Metallic UI
   audio2mp4.php
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
    max-width: 720px;
    margin: 0 auto;
}

.card {
    background:
        linear-gradient(
            135deg,
            rgba(30, 58, 138, 0.35),
            rgba(15, 23, 42, 0.65)
        );
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 18px;
    padding: 16px;
    margin-bottom: 18px;
    backdrop-filter: blur(10px);
    box-shadow:
        0 10px 30px rgba(2, 6, 23, 0.6),
        inset 0 1px 0 rgba(255,255,255,0.04);
}

h1 {
    font-size: 18px;
    margin: 0 0 12px;
    font-weight: 700;
    color: #f8fafc;
    letter-spacing: 0.3px;
}

h2 {
    font-size: 15px;
    margin: 14px 0 8px;
    font-weight: 600;
    color: #c7d2fe;
}

label {
    font-size: 13px;
    display: block;
    margin-bottom: 4px;
    color: #94a3b8;
}

input[type="text"],
input[type="file"],
textarea {
    width: 100%;
    background: rgba(2, 6, 23, 0.7);
    color: #e5e7eb;
    border-radius: 12px;
    border: 1px solid rgba(148, 163, 184, 0.35);
    padding: 8px;
    font-size: 14px;
}

textarea {
    min-height: 160px;
}

button {
    width: 100%;
    margin-top: 12px;
    padding: 10px;
    border: 0;
    border-radius: 12px;
    background:
        linear-gradient(135deg, #2563eb, #0ea5e9);
    color: #ffffff;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    box-shadow: 0 6px 18px rgba(37, 99, 235, 0.45);
}

video {
    width: 100%;
    margin-top: 8px;
    border-radius: 14px;
    background: rgba(2, 6, 23, 0.6);
}

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
<h1>🎵 音声/楽曲ファイルアップロード</h1>

<form method="post" enctype="multipart/form-data" action="video2mp4.php">

<input type="hidden" name="upload_audio" value="1">

<label>音声/楽曲ファイル（mp3 / wav）</label>
<input type="file" name="audio_file" accept=".mp3,.wav" required>

<button type="submit">音声をアップロード</button>
</form>
</div>

<div class="card">
<h1>🎬 背景動画＋ラジオ音声＋台本 → MP4</h1>

<?php if ($msg !== ""): ?>
<div><?php echo $msg; ?></div>
<?php endif; ?>

<form method="post" enctype="multipart/form-data">

<label>① 背景動画</label>
<input type="file" name="image" accept="video/mp4" required>

<label style="margin-top:12px;">② 音声/楽曲URL</label>
<input type="text" name="audio_url" value="<?php echo htmlspecialchars($audio_url, ENT_QUOTES, "UTF-8"); ?>" required>

<label style="margin-top:12px;">③ ラジオ台本（スクロール表示）</label>
<textarea name="script_text"></textarea>

<button type="submit">MP4を生成</button>
</form>
</div>

<?php if ($result): ?>
<div class="card">
<h2>生成結果</h2>

<video controls>
    <source src="<?php echo htmlspecialchars($result["mp4_url"], ENT_QUOTES, "UTF-8"); ?>">
</video>

<a href="<?php echo htmlspecialchars($result["mp4_url"], ENT_QUOTES, "UTF-8"); ?>" target="_blank">
<?php echo htmlspecialchars($result["mp4_url"], ENT_QUOTES, "UTF-8"); ?>
</a>
</div>
<?php endif; ?>

</div>

</body>
</html>


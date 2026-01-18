<?php
// =========================================
// audio_to_mp4.php
// 画像 + mp3/wav URL → mp4 生成（API経由）
// PHP5互換
// =========================================

date_default_timezone_set("Asia/Tokyo");

define("API_ENDPOINT", "http://exbridge.ddns.net:8002/audio_to_mp4");

$msg = "";
$result = null;

if ($_SERVER["REQUEST_METHOD"] === "POST") {

    if (
        isset($_FILES["image"])
        && isset($_POST["audio_url"])
        && $_FILES["image"]["tmp_name"] !== ""
        && trim($_POST["audio_url"]) !== ""
    ) {

        $audio_url = trim($_POST["audio_url"]);

        $ch = curl_init(API_ENDPOINT);

        $post = array(
            "audio_url" => $audio_url,
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
        $msg = "❌ 画像ファイルと音声URLを指定してください";
    }
}
?>
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>MP3 / WAV → MP4 生成</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body {
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    background:#f6f7f9;
    padding:16px;
}
.wrap {
    max-width:720px;
    margin:0 auto;
}
.card {
    background:#fff;
    border:1px solid #e5e7eb;
    border-radius:16px;
    padding:16px;
    margin-bottom:16px;
}
h1 {
    font-size:18px;
    margin:0 0 12px;
}
label {
    display:block;
    font-size:13px;
    margin-bottom:4px;
}
input[type=text],
input[type=file] {
    width:100%;
    padding:6px;
}
button {
    width:100%;
    margin-top:12px;
    padding:10px;
    border:0;
    border-radius:10px;
    background:#2563eb;
    color:#fff;
    font-size:14px;
    cursor:pointer;
}
.msg {
    font-weight:600;
    margin-bottom:10px;
}
.note {
    font-size:12px;
    color:#6b7280;
}
video {
    width:100%;
    margin-top:8px;
    border-radius:12px;
}
a {
    word-break: break-all;
}
</style>
</head>
<body>

<div class="wrap">

<div class="card">
<h1>🎬 ラジオ音声 → MP4 動画生成</h1>

<?php if ($msg !== ""): ?>
<div class="msg"><?php echo $msg; ?></div>
<?php endif; ?>

<form method="post" enctype="multipart/form-data">
    <label>① 画像ファイル（PNG / JPG）</label>
    <input type="file" name="image" accept="image/*" required>

    <label style="margin-top:12px;">② 音声ファイルURL（mp3 / wav）</label>
    <input type="text" name="audio_url" placeholder="https://exbridge.ddns.net/aidexx/mixed/xxxx.mp3" required>

    <button type="submit">MP4を生成する</button>
</form>

<div class="note">
・ffmpeg は Python サーバ側で実行されます<br>
・PHP サーバには音声・動画ファイルは保存されません
</div>
</div>

<?php if ($result): ?>
<div class="card">
<h1>生成されたMP4</h1>

<div class="note">
<?php echo htmlspecialchars($result["file"], ENT_QUOTES, "UTF-8"); ?>
</div>

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


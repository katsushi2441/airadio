<?php
// =========================================
// bgm_manager.php
// BGMファイル管理（アップロード / 一覧 / 再生 / 削除）
// + ラジオURL同時再生 / ミックス保存
// PHP5互換
// =========================================

$bgm_dir = __DIR__ . "/bgm";
if (!is_dir($bgm_dir)) {
    mkdir($bgm_dir, 0755, true);
}

/* -------------------------
   ミックス保存処理
------------------------- */
if (
    $_SERVER["REQUEST_METHOD"] === "POST"
    && isset($_SERVER["CONTENT_TYPE"])
    && strpos($_SERVER["CONTENT_TYPE"], "application/json") !== false
) {
    handle_mix_request();
}

/* -------------------------
   ミックス処理本体
------------------------- */
function handle_mix_request() {
    $raw  = file_get_contents("php://input");
    $data = json_decode($raw, true);

    if (!is_array($data)) return;
    if (!isset($data["mode"]) || $data["mode"] !== "mix") return;

    $radio_url = $data["radio_url"];
    $bgm_file  = $data["bgm_file"];
    $bgm_vol   = isset($data["bgm_volume"]) ? (int)$data["bgm_volume"] : 30;
    $bgm_vol   = max(0, min(100, $bgm_vol));
    $bgm_start = isset($data["bgm_start"]) ? (float)$data["bgm_start"] : 0;

    $src = basename(parse_url($radio_url, PHP_URL_PATH));


    // ===== voicebox_api /mix に転送 =====
    $api_url = "http://exbridge.ddns.net:8002/mix";

    $bgm_url = "https://exbridge.jp/aidexx/bgm/" . $bgm_file;

    $payload = json_encode(array(
        "radio_url"  => $radio_url,
        "bgm_url"    => $bgm_url,
        "bgm_volume" => $bgm_vol,
        "bgm_start"  => $bgm_start,
        "source_file" => $src
    ));

    error_log("BGM_API payload: " . $payload);

    $ch = curl_init($api_url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_POST, true);
    curl_setopt($ch, CURLOPT_HTTPHEADER, array(
        "Content-Type: application/json",
        "Content-Length: " . strlen($payload)
    ));
    curl_setopt($ch, CURLOPT_POSTFIELDS, $payload);

    $res = curl_exec($ch);
    $err = curl_error($ch);
    curl_close($ch);
    error_log("BGM_API response: " . $res);
    if ($err) {
        error_log("BGM_API curl_error: " . $err);
    }

    header("Content-Type: application/json");

    if ($res === false) {
        echo json_encode(array("ok" => false, "error" => $err));
        exit;
    }

    echo $res;
    exit;
}

/* -------------------------
   削除処理
------------------------- */
if (isset($_GET["delete"])) {
    $file = basename($_GET["delete"]);
    $path = $bgm_dir . "/" . $file;
    if (is_file($path)) unlink($path);
    header("Location: ".$_SERVER["PHP_SELF"]);
    exit;
}

/* -------------------------
   アップロード処理
------------------------- */
if (isset($_FILES["bgm"])) {
    $name = $_FILES["bgm"]["name"];
    $tmp  = $_FILES["bgm"]["tmp_name"];
    if ($tmp != "") {
        move_uploaded_file($tmp, $bgm_dir . "/" . $name);
    }
    header("Location: ".$_SERVER["PHP_SELF"]);
    exit;
}

/* -------------------------
   ファイル一覧取得
------------------------- */
$files = array();
$dh = opendir($bgm_dir);
while (($f = readdir($dh)) !== false) {
    if ($f === "." || $f === "..") continue;
    if (is_file($bgm_dir . "/" . $f)) $files[] = $f;
}
closedir($dh);
sort($files);
?>
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>BGM Manager</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
/* ===============================
   Web3 Navy / Metallic UI
   bgm_manager.php
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

/* ガラス＋メタリックカード */
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
    margin: 0 0 14px;
    font-weight: 700;
    color: #f8fafc;
    letter-spacing: 0.3px;
}

h2 {
    font-size: 15px;
    margin: 16px 0 8px;
    font-weight: 600;
    color: #c7d2fe;
}

/* フォーム */
label {
    display: block;
    font-size: 13px;
    margin-bottom: 4px;
    color: #94a3b8;
}

input[type="text"],
input[type="file"],
input[type="number"],
input[type="range"] {
    width: 100%;
    background: rgba(2, 6, 23, 0.7);
    color: #e5e7eb;
    border-radius: 12px;
    border: 1px solid rgba(148, 163, 184, 0.35);
    padding: 8px;
    font-size: 14px;
}

/* ボタン */
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

button:hover {
    filter: brightness(1.08);
}

button.sub {
    background: rgba(2, 6, 23, 0.7);
    box-shadow: none;
}

.btn-mini {
    width: auto;
    margin: 2px;
    padding: 6px 10px;
    font-size: 13px;
    border-radius: 10px;
    background: rgba(15, 23, 42, 0.8);
    color: #e5e7eb;
}

/* テーブル */
table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}

th, td {
    border-bottom: 1px solid rgba(148, 163, 184, 0.2);
    padding: 10px 6px;
    vertical-align: middle;
}

th {
    text-align: left;
    background: rgba(2, 6, 23, 0.6);
    color: #c7d2fe;
    font-weight: 600;
}

tr:hover td {
    background: rgba(30, 58, 138, 0.12);
}

/* audio */
audio {
    width: 100%;
    height: 40px;
    background: rgba(2, 6, 23, 0.6);
    border-radius: 10px;
}

/* アクション */
.td-actions {
    text-align: center;
    white-space: nowrap;
}

.td-actions .btn-mini {
    display: inline-block;
}

/* ノート */
.note {
    font-size: 12px;
    color: #94a3b8;
    margin-top: 8px;
}

/* MIX成果物強調 */
#mix_result {
    background:
        linear-gradient(
            135deg,
            rgba(30, 58, 138, 0.3),
            rgba(15, 23, 42, 0.7)
        );
    border: 2px solid #2563eb;
    border-radius: 14px;
    padding: 14px;
    font-size: 13px;
    color: #e5e7eb;
}

#mix_result audio {
    width: 100%;
    height: 48px;
    margin-bottom: 8px;
}

#mix_result a {
    word-break: break-all;
    font-size: 12px;
    color: #38bdf8;
}
</style>
</head>
<body>

<div class="wrap">

<div class="card">
<h1>BGM マネージャー</h1>
<form method="post" enctype="multipart/form-data">
    <label>BGMアップロード</label>
    <input type="file" name="bgm" accept="audio/*" required>
    <button type="submit">アップロード</button>
</form>
<div class="note">※ mp3 / wav / mp4 対応</div>
</div>

<div class="card">
<h2>ラジオ音源URL</h2>
<input type="text" id="radio_url">
<label>BGM音量</label>
<input type="range" id="bgm_volume" min="0" max="100">
<div class="note">※ 音量は保存・ミックスにも反映されます</div>
</div>
<label>BGM開始秒</label>
<input type="number" id="bgm_start" min="0" value="0">
<div class="note">※ BGMを何秒後から再生するか（保存・同時再生に反映）</div>


<div class="card">
<h2>BGM一覧</h2>
<table>
<tr>
    <th>ファイル</th>
    <th width="30%">再生</th>
    <th>操作</th>
    <th>削除</th>
</tr>
<?php foreach ($files as $f): ?>
<tr>
    <td><?php echo htmlspecialchars($f, ENT_QUOTES, 'UTF-8'); ?></td>
    <td>
        <audio controls>
            <source src="bgm/<?php echo rawurlencode($f); ?>">
        </audio>
    </td>
    <td class="td-actions">
        <button type="button" class="sub btn-mini" onclick="playBoth('<?php echo rawurlencode($f); ?>')">▶</button>
        <button type="button" class="sub btn-mini" onclick="stopBoth()">■</button>
        <button type="button" class="sub btn-mini" onclick="saveMix('<?php echo rawurlencode($f); ?>')">💾</button>
    </td>
    <td>
        <a href="?delete=<?php echo rawurlencode($f); ?>" onclick="return confirm('削除しますか？');">削除</a>
    </td>
</tr>
<?php endforeach; ?>
</table>
</div>

<div class="card">
<h2>生成されたMIX音源</h2>
<div id="mix_result" class="note">まだ生成されていません</div>
</div>

</div>

<audio id="radio_player"></audio>
<audio id="bgm_player" loop></audio>



<script>
var RADIO_KEY = "bgm_manager_radio_url";
var VOL_KEY   = "bgm_manager_bgm_volume";

var radioInput = document.getElementById("radio_url");
var volInput   = document.getElementById("bgm_volume");
var radio      = document.getElementById("radio_player");
var bgm        = document.getElementById("bgm_player");

document.addEventListener("DOMContentLoaded", function () {
    var r = localStorage.getItem(RADIO_KEY);
    var v = localStorage.getItem(VOL_KEY);
    if (r) radioInput.value = r;
    volInput.value = v !== null ? v : 30;
    bgm.volume = volInput.value / 100;
});

radioInput.addEventListener("input", function () {
    localStorage.setItem(RADIO_KEY, this.value);
});
volInput.addEventListener("input", function () {
    localStorage.setItem(VOL_KEY, this.value);
    bgm.volume = this.value / 100;
});
var startInput = document.getElementById("bgm_start");
function playBoth(bgmFile) {
    if (!radioInput.value) return alert("ラジオ音源URLを入力してください");

    var start = parseFloat(startInput.value) || 0;

    radio.pause();
    bgm.pause();

    radio.currentTime = 0;
    bgm.currentTime   = 0;

    radio.src = radioInput.value;
    bgm.src   = "bgm/" + bgmFile;

    radio.play();

    setTimeout(function () {
        bgm.play();
    }, start * 1000);
}

function stopBoth() {
    radio.pause(); bgm.pause();
    radio.currentTime = 0;
    bgm.currentTime   = 0;
}
function saveMix(bgmFile) {
    if (!radioInput.value) return alert("ラジオ音源URLを入力してください");
    fetch("bgm_manager.php", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({
            mode: "mix",
            radio_url: radioInput.value,
            bgm_file: bgmFile,
            bgm_volume: volInput.value,
            bgm_start: startInput.value,
            source_file: radioInput.value.split("/").pop()
        })
    })
    .then(r => r.json())
    .then(j => {
        if (j.ok) {
            alert("保存完了: " + (j.file || ""));
            document.getElementById("mix_result").innerHTML =
    '<audio controls src="https://exbridge.ddns.net/aidexx/mixed/' + (j.file || '') + '"></audio><br>' +
    '<a href="https://exbridge.ddns.net/aidexx/mixed/' + (j.file || '') + '" target="_blank">' +
    'https://exbridge.ddns.net/aidexx/mixed/' + (j.file || '') +
    '</a>';

        } else {
            alert("保存失敗: " + (j.error || j.file || ""));
        }
    });


}
</script>

</body>
</html>


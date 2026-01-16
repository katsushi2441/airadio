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

    // ===== voicebox_api /mix に転送 =====
    $api_url = "http://exbridge.ddns.net:8002/mix";

    $bgm_url = "https://exbridge.jp/aidexx/bgm/" . rawurlencode($bgm_file);

    $payload = json_encode(array(
        "radio_url"  => $radio_url,
        "bgm_url"    => $bgm_url,
        "bgm_volume" => $bgm_vol
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
    $name = basename($_FILES["bgm"]["name"]);
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
body {
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    background:#f6f7f9;
    padding:16px;
}
.wrap { max-width:720px; margin:0 auto; }
.card {
    background:#fff;
    border:1px solid #e5e7eb;
    border-radius:16px;
    padding:16px;
    margin-bottom:16px;
}
h1 { font-size:18px; margin:0 0 12px; }
h2 { font-size:15px; margin:16px 0 8px; }
label { display:block; font-size:13px; margin-bottom:4px; }
input[type=text], input[type=file] { width:100%; }
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
button.sub { background:#374151; }
.btn-mini {
    width:auto;
    margin:2px;
    padding:6px 10px;
    font-size:13px;
    border-radius:8px;
}
.td-actions { white-space:nowrap; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th, td { border-bottom:1px solid #e5e7eb; padding:8px 4px; }
audio { width:100%; height:40px; }
.note { font-size:12px; color:#6b7280; margin-top:8px; }

/* --- BGM一覧の視認性改善（構造変更なし） --- */
table audio {
    max-width: 220px;
}

.td-actions {
    text-align: center;
}

.td-actions .btn-mini {
    display: inline-block;
}

/* --- MIX結果を成果物として強調 --- */
#mix_result {
    background: #f9fafb;
    border: 2px solid #2563eb;
    border-radius: 12px;
    padding: 12px;
    font-size: 13px;
}

#mix_result audio {
    width: 100%;
    height: 48px;
    margin-bottom: 6px;
}

#mix_result a {
    word-break: break-all;
    font-size: 12px;
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
    <td><?php echo htmlspecialchars($f); ?></td>
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

function playBoth(bgmFile) {
    if (!radioInput.value) return alert("ラジオ音源URLを入力してください");
    radio.src = radioInput.value;
    bgm.src   = "bgm/" + bgmFile;
    radio.play();
    bgm.play();
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
            bgm_volume: volInput.value
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


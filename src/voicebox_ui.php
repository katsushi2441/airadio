<?php
// ---------------------------------
// voicebox UI
// - 設定保存 / 読込（JSON）
// - サンプル音声生成（PHP → Python API）
// ---------------------------------

$profile_file = __DIR__ . "/voice_profile.json";

if (
    $_SERVER["REQUEST_METHOD"] === "POST"
    && isset($_SERVER["CONTENT_TYPE"])
    && strpos($_SERVER["CONTENT_TYPE"], "application/json") !== false
) {
    $raw = file_get_contents("php://input");
    $data = json_decode($raw, true);

    // ---------- 設定保存 ----------
    if (is_array($data) && isset($data["mode"]) && $data["mode"] === "save") {
        file_put_contents(
            $profile_file,
            json_encode($data["profile"], JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT)
        );
        header("Content-Type: application/json");
        echo json_encode(array("ok" => true));
        exit;
    }

    // ---------- 設定読込 ----------
    if (is_array($data) && isset($data["mode"]) && $data["mode"] === "load") {
        header("Content-Type: application/json");
        if (file_exists($profile_file)) {
            echo file_get_contents($profile_file);
        } else {
            echo "{}";
        }
        exit;
    }

    // ---------- サンプル音声生成（既存処理） ----------
    if (is_array($data)) {
        $ch = curl_init("http://exbridge.ddns.net:8002/tts_sample");
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_POST, true);
        curl_setopt($ch, CURLOPT_HTTPHEADER, array("Content-Type: application/json"));
        curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($data));
        $res = curl_exec($ch);
        curl_close($ch);

        header("Content-Type: application/json");
        echo $res;
        exit;
    }
}
?>
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<title>VOICEBOX 話者・音声調整</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body {
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    background:#f6f7f9;
    padding:16px;
}
.wrap {
    max-width: 720px;
    margin: 0 auto;
}
.card {
    background:#fff;
    border:1px solid #e5e7eb;
    border-radius:16px;
    padding:16px;
}
h1 {
    font-size:18px;
    margin:0 0 12px;
}
label {
    display:block;
    font-size:13px;
    margin-top:12px;
    margin-bottom:4px;
}
select,
textarea,
input[type=range] {
    width:100%;
}
textarea {
    min-height:80px;
    padding:8px;
    font-size:14px;
}
.range-row {
    display:flex;
    align-items:center;
    gap:8px;
}
.range-row span {
    width:40px;
    text-align:right;
    font-size:12px;
    color:#555;
}
button {
    width:100%;
    margin-top:16px;
    padding:10px;
    border:0;
    border-radius:10px;
    background:#2563eb;
    color:#fff;
    font-size:15px;
    cursor:pointer;
}
audio {
    width:100%;
    margin-top:12px;
}
.note {
    font-size:12px;
    color:#6b7280;
    margin-top:8px;
}
</style>
</head>
<body>

<div class="wrap">
<div class="card">

<h1>VOICEBOX 話者・音声調整（UI）</h1>

<label>話者（speaker）</label>
<select id="speaker">
    <!-- 四国めたん -->
    <option value="1">四国めたん（ノーマル）</option>
    <option value="2">四国めたん（あまあま）</option>
    <option value="3">四国めたん（ツンツン）</option>
    <option value="4">四国めたん（セクシー）</option>
    <option value="5">四国めたん（ささやき）</option>
    <option value="6">四国めたん（ヒソヒソ）</option>

    <!-- ずんだもん -->
    <option value="7">ずんだもん（ノーマル）</option>
    <option value="8">ずんだもん（あまあま）</option>
    <option value="9">ずんだもん（ツンツン）</option>
    <option value="10">ずんだもん（セクシー）</option>
    <option value="11">ずんだもん（ささやき）</option>
    <option value="12">ずんだもん（ヒソヒソ）</option>

    <!-- 春日部つむぎ -->
    <option value="13">春日部つむぎ（ノーマル）</option>

    <!-- 冥鳴ひまり -->
    <option value="14">冥鳴ひまり（ノーマル）</option>

    <!-- 九州そら -->
    <option value="15">九州そら（ノーマル）</option>
    <option value="16">九州そら（あまあま）</option>
    <option value="17">九州そら（ツンツン）</option>
    <option value="18">九州そら（セクシー）</option>
    <option value="19">九州そら（ささやき）</option>

    <!-- もち子さん -->
    <option value="20">もち子さん（ノーマル）</option>
</select>

<label>サンプルテキスト</label>
<textarea id="text">これはサンプル音声です。</textarea>

<label>話速</label>
<div class="range-row">
<input id="speed" type="range" min="0.5" max="2.0" step="0.05" value="1.0">
<span>1.00</span>
</div>

<label>音高</label>
<div class="range-row">
<input id="pitch" type="range" min="-0.15" max="0.15" step="0.01" value="0.0">
<span>0.00</span>
</div>

<label>抑揚</label>
<div class="range-row">
<input id="intonation" type="range" min="0.0" max="2.0" step="0.05" value="1.0">
<span>1.00</span>
</div>

<label>音量</label>
<div class="range-row">
<input id="volume" type="range" min="0.0" max="2.0" step="0.05" value="1.0">
<span>1.00</span>
</div>

<button id="play">▶ サンプル再生</button>

<audio id="audio" controls></audio>

<div class="note">
※ 話者・パラメータを調整してサンプル音声を確認できます。
</div>

</div>
</div>

<script>
// ---------- スライダー数値表示 ----------
document.querySelectorAll(".range-row").forEach(function(row) {
    const range = row.querySelector("input[type=range]");
    const span  = row.querySelector("span");
    span.textContent = Number(range.value).toFixed(2);
    range.addEventListener("input", function () {
        span.textContent = Number(this.value).toFixed(2);
    });
});

// ---------- 初期ロード：設定読込 ----------
(async function loadProfile() {
    const res = await fetch("voicebox_ui.php", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({mode:"load"})
    });
    const p = await res.json();
    if (!p.speaker) return;

    speaker.value = p.speaker;
    speed.value = p.speed;
    pitch.value = p.pitch;
    intonation.value = p.intonation;
    volume.value = p.volume;

    document.querySelectorAll(".range-row span").forEach(function(span, i) {
        const r = [speed, pitch, intonation, volume][i];
        span.textContent = Number(r.value).toFixed(2);
    });
})();

// ---------- 再生 + 設定保存 ----------
document.getElementById("play").addEventListener("click", async function () {

    const profile = {
        speaker: Number(speaker.value),
        speed: Number(speed.value),
        pitch: Number(pitch.value),
        intonation: Number(intonation.value),
        volume: Number(volume.value)
    };

    // 設定保存
    await fetch("voicebox_ui.php", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({
            mode: "save",
            profile: profile
        })
    });

    // サンプル音声生成
    const res = await fetch("voicebox_ui.php", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify(Object.assign(
            { text: text.value },
            profile
        ))
    });

    const json = await res.json();
    audio.src = json.audio_url + "?t=" + Date.now();
    audio.play();
});
</script>

</body>
</html>


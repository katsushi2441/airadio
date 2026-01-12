<?php
// =========================================
// spotify_rss.php
// airadio_log.json → Spotify用 RSS.xml 生成
// ・PHP5互換
// ・<?xml 誤認識回避
// ・削除済み音声ファイルを除外
// =========================================

date_default_timezone_set("Asia/Tokyo");

// -------------------------
// 設定
// -------------------------
$logFile = __DIR__ . "/airadio_log.json";
$rssFile = __DIR__ . "/rss.xml";

$audioBase = "https://exbridge.ddns.net/aidexx/tts/";
$siteUrl   = "https://exbridge.ddns.net/aidexx/";
$feedTitle = "AI思考のラジオ";
$feedDesc  = "AIがニュースを素材に思考のきっかけを届ける音声番組";
$feedLang  = "ja-JP";

// TTSサーバ（現存ファイル確認用）
$TTS_FILES_API = "http://exbridge.ddns.net:8002/files";

// -------------------------
// TTSサーバから現存ファイル一覧取得
// -------------------------
function get_existing_tts_files($url) {

    $ch = curl_init($url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_TIMEOUT, 15);
    $res = curl_exec($ch);
    curl_close($ch);

    $data = json_decode($res, true);
    $files = array();

    if (is_array($data)) {
        foreach ($data as $row) {
            if (isset($row["file"])) {
                $files[] = $row["file"];
            }
        }
    }

    return $files;
}

// -------------------------
// ログ読み込み
// -------------------------
if (!file_exists($logFile)) {
    die("airadio_log.json not found");
}

$list = json_decode(file_get_contents($logFile), true);
if (!is_array($list)) {
    die("airadio_log.json invalid");
}

// 新しい順に
$list = array_reverse($list);

// -------------------------
// 現存音声ファイルのMap
// -------------------------
$existingFiles = get_existing_tts_files($TTS_FILES_API);
$existingMap = array_flip($existingFiles);

// -------------------------
// RSS生成
// -------------------------
$rss = '';
$rss .= '<' . '?xml version="1.0" encoding="UTF-8"?' . ">\n";
$rss .= "<rss version=\"2.0\">\n";
$rss .= "  <channel>\n";
$rss .= "    <title>" . htmlspecialchars($feedTitle, ENT_QUOTES, "UTF-8") . "</title>\n";
$rss .= "    <link>" . htmlspecialchars($siteUrl, ENT_QUOTES, "UTF-8") . "</link>\n";
$rss .= "    <description>" . htmlspecialchars($feedDesc, ENT_QUOTES, "UTF-8") . "</description>\n";
$rss .= "    <language>{$feedLang}</language>\n";

foreach ($list as $row) {

    if (!isset($row["file"]) || !isset($row["datetime"])) {
        continue;
    }

    // 削除済み音声は除外
    if (!isset($existingMap[$row["file"]])) {
        continue;
    }

    $file = basename($row["file"]);
    $audioUrl = $audioBase . $file;

    $keyword = isset($row["keyword"]) ? $row["keyword"] : "";
    $script  = isset($row["script"]) ? $row["script"] : "";

    $title = "AI思考のラジオ｜" . $keyword;
    $desc  = mb_substr($script, 0, 300);

    $pubDate = date(DATE_RSS, strtotime($row["datetime"]));

    $rss .= "    <item>\n";
    $rss .= "      <title><![CDATA[" . $title . "]]></title>\n";
    $rss .= "      <description><![CDATA[" . $desc . "]]></description>\n";
    $rss .= "      <enclosure url=\"" . htmlspecialchars($audioUrl, ENT_QUOTES, "UTF-8") . "\" type=\"audio/wav\" />\n";
    $rss .= "      <guid>" . htmlspecialchars($audioUrl, ENT_QUOTES, "UTF-8") . "</guid>\n";
    $rss .= "      <pubDate>{$pubDate}</pubDate>\n";
    $rss .= "    </item>\n";
}

$rss .= "  </channel>\n";
$rss .= "</rss>\n";

// -------------------------
// 書き込み
// -------------------------
file_put_contents($rssFile, $rss);

// -------------------------
// 確認用出力
// -------------------------
header("Content-Type: text/plain; charset=UTF-8");
echo "OK: rss.xml generated\n";
echo $rss;


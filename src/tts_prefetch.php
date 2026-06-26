<?php
if (PHP_SAPI !== 'cli') {
    http_response_code(404);
    exit;
}
require_once __DIR__ . '/lib.php';

$payloadPath = '';
for ($i = 1; $i < count($argv); $i++) {
    if ($argv[$i] === '--payload' && isset($argv[$i + 1])) {
        $payloadPath = $argv[$i + 1];
        $i++;
    }
}

$payload = $payloadPath !== '' ? airadio_read_json($payloadPath, []) : [];
$items = isset($payload['items']) && is_array($payload['items']) ? $payload['items'] : [];
$reason = isset($payload['reason']) ? (string)$payload['reason'] : 'manual';
$limit = AIRADIO_TTS_PREFETCH_LIMIT;
$ok = 0;
$failed = 0;

airadio_append_log('tts_prefetch_running', ['reason' => $reason, 'count' => count($items)]);
airadio_update_state(['tts_status' => 'prefetching', 'tts_prefetch_reason' => $reason]);

foreach (array_slice($items, 0, $limit) as $item) {
    if (!is_array($item)) { continue; }
    $text = trim((string)(isset($item['text']) ? $item['text'] : ''));
    if ($text === '') { continue; }
    try {
        $path = airadio_tts_audio_path($text);
        $ok++;
        airadio_append_log('tts_prefetch_cached', [
            'reason' => $reason,
            'id' => isset($item['id']) ? (string)$item['id'] : '',
            'title' => isset($item['title']) ? (string)$item['title'] : '',
            'bytes' => is_file($path) ? filesize($path) : 0,
        ]);
    } catch (Throwable $e) {
        $failed++;
        airadio_append_log('tts_prefetch_failed', [
            'reason' => $reason,
            'id' => isset($item['id']) ? (string)$item['id'] : '',
            'title' => isset($item['title']) ? (string)$item['title'] : '',
            'error' => $e->getMessage(),
        ]);
    }
}

airadio_update_state([
    'tts_status' => $failed > 0 && $ok === 0 ? 'prefetch_failed' : 'prefetch_ready',
    'tts_cached' => $ok,
    'tts_failed' => $failed,
    'tts_prefetch_reason' => $reason,
]);

if ($payloadPath !== '' && is_file($payloadPath)) {
    @unlink($payloadPath);
}

echo json_encode(['ok' => $ok, 'failed' => $failed, 'reason' => $reason], JSON_UNESCAPED_UNICODE) . "\n";

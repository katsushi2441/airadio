# Kurage AI VTuber Radio

Kurage AI VTuber Radio is a sleep-friendly AI thinking radio system.
It combines the Kurage project family into one live radio product:

- `kvtuber` style PNG VTuber avatar and mouth animation
- `kagentreach` style background information gathering
- loop-engineering inspired foreground/background control loops
- shared URL2AI/X login, initially restricted to `xb_bittensor`
- optional YouTube Live / RTMP output through the existing Kurage VTuber tooling

## Concept

**聴きながらよく寝れる - AI思考のラジオ**

The most important product requirement is that the listener is not kept waiting.
The VTuber keeps speaking in the foreground while research and script generation
continue in the background. If the script queue runs dry, the foreground loop
uses quiet bridge talk and triggers another background research job.

## Current MVP

- `src/airadio.php`: white, URL2AI-like radio UI
- `src/api.php`: control API for start/stop/theme interrupt/next segment/YouTube Live hooks
- `src/airadio_worker.py`: background kagentreach/Ollama script refill worker
- `src/assets/kurage_radio_idle.png`: Kurage bishoujo idle avatar
- `src/assets/kurage_radio_talk.png`: Kurage bishoujo talking avatar

## Auth

The app uses URL2AI common login when available:

```php
/home/kojima/work/url2ai/src/auth_common.php
```

Only `xb_bittensor` is allowed in the first version.

## Radio Loop

Foreground loop:

1. Browser requests `api.php?action=next`.
2. If a script exists, Kurage speaks it using browser speech synthesis.
3. If no script exists, Kurage speaks a calm bridge segment immediately.
4. The avatar mouth switches while speaking.

Background loop:

1. `api.php?action=start` or `api.php?action=interrupt` launches `airadio_worker.py` with `nohup`.
2. The worker asks kagentreach/browser-use to search X when available.
3. The worker asks Ollama `gemma4:12b-it-qat` on `192.168.0.3` to create calm radio scripts.
4. New segments are appended to `storage/script_queue.json`.

## Theme Interrupt

The logged-in user can type a theme such as:

```text
バイブコーディングをテーマにして
```

The UI immediately queues a short transition segment and starts background
research for that theme. The radio keeps talking while the new script is built.

## Duration

The UI supports 1 to 6 hour sessions in 1 hour increments.

## YouTube Live

`api.php?action=youtube_start` can hand the AIRadio viewer URL to
`/home/kojima/work/kvtuber/scripts/youtube-live-rtmp.mjs`.

This keeps YouTube Live implementation in the Kurage VTuber layer and lets
AIRadio focus on the radio loop.

## Development

```bash
php -S 127.0.0.1:18080 -t src
# open http://127.0.0.1:18080/airadio.php
```

The app writes runtime state to `storage/`, which is intentionally not part of
Git history.

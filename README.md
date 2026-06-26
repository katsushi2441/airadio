# Kurage AI VTuber Radio

Kurage AI VTuber Radio is a sleep-friendly AI thinking radio system.
It combines the Kurage project family into one live radio product:

- `kvtuber` style PNG VTuber avatar and mouth animation
- `Kurage AgentReach` style background information gathering
- loop-engineering inspired foreground/background control loops
- shared URL2AI/X login for listeners; program profile based on the editor account
- optional YouTube Live / RTMP output through the existing Kurage VTuber tooling
- YouTube-style listener comments shared by the editor and logged-in listeners

## Concept

**聴きながらよく寝れる - AI思考のラジオ**

The most important product requirement is that the listener is not kept waiting.
The VTuber keeps speaking in the foreground while research and script generation
continue in the background. If the script queue runs dry, the foreground loop
uses quiet bridge talk and triggers another background research job.

Kurage AI VTuber Radio is also a content-production system for the sleep and
learning video niche. Sleep-friendly long-form videos often grow because they
earn long watch time, can be reused as background media, and do not require a
traditional face-on-camera performer. AIRadio turns that pattern into a live AI
VTuber workflow:

1. Kurage speaks continuously as a calm DJ.
2. The editor chooses what they want to learn.
3. Kurage AgentReach collects signals in the background.
4. The script queue is refilled while the foreground radio keeps speaking.
5. The same session can be streamed to YouTube Live and recorded as a long-form
   sleep-learning video asset.

In short, the product is not only "a radio that talks." It is:

> A sleep-friendly AI VTuber radio that can create reusable learning videos
> while it is being live-streamed.

This is why the editor role matters. The editor is not just a listener; the
editor curates the learning direction for other listeners. Kurage turns that
editorial intent into a calm, continuous program.

## Current MVP

- `src/airadio.php`: white, URL2AI-like radio UI
- `src/api.php`: control API for start/stop/theme interrupt/next segment/YouTube Live hooks
- `src/api.php?action=tts`: Kurage-standard edge-tts audio endpoint
- `src/airadio_worker.py`: background Kurage AgentReach/Ollama script refill worker
- `src/assets/kurage_radio_idle.png`: Kurage bishoujo idle avatar
- `src/assets/kurage_radio_talk.png`: Kurage bishoujo talking avatar

## Auth

The app carries a local copy of the URL2AI common login helper, matching the
`oss.php` pattern:

```text
src/auth_common.php
airadio.php?airadio_login=1
airadio.php?airadio_logout=1
```

Any logged-in common-login user can listen. The program content is based on the
editor account's X profile, but the public UI calls that role `編集者` instead
of showing the internal account name.

## Radio Loop

Foreground loop:

1. The editor/broadcaster account requests `api.php?action=next`.
2. If a script exists, the server consumes one shared queue item and writes it to `storage/current_segment.json`.
3. Listener accounts poll `api.php?action=current` and speak the same current script without consuming the queue.
4. If the editor is not on air, listener accounts stay in standby.
5. If no script exists, the broadcaster speaks a calm bridge segment immediately.
6. The avatar mouth switches while speaking.

Background loop:

1. `api.php?action=start` or `api.php?action=interrupt` launches `airadio_worker.py` with `nohup`.
2. The worker asks Kurage AgentReach/browser-use to search X when available.
3. The worker asks Claude when available, then Ollama `gemma4:12b-it-qat` on `192.168.0.3`, to create calm but substantive radio scripts.
4. New segments are appended to `storage/script_queue.json`.

Comment loop:

1. Any logged-in user can post a short comment through `api.php?action=comment`.
2. Admin/editor comments are displayed as `編集者`; other logged-in users are displayed as listener comments.
3. Comments are stored in `storage/comments.json` and returned with `status`/`current` polling.

## Theme Interrupt

The broadcaster account can type a theme such as:

```text
バイブコーディングをテーマにして
```

The UI immediately queues a short transition segment and starts background
research for that theme. The radio keeps talking while the new script is built.

## Duration

The UI supports 1 to 6 hour sessions in 1 hour increments.

## Voice / TTS

AIRadio uses the same Kurage-standard TTS path as the broader Kurage VTuber
tooling instead of browser `speechSynthesis`.

- Script: `/home/kojima/work/kvtuber/scripts/kurage-edge-tts.py`
- HTTP endpoint: `AIRADIO_TTS_ENDPOINT` or `http://exbridge.ddns.net:18308/kurage-tts/v1/audio/speech`
- Voice: `ja-JP-NanamiNeural`
- Rate: `+10%`
- Pitch: `-15Hz`
- Pronunciation normalization: `/home/kojima/work/kurage/backend/tts_normalizer.py`

The browser requests MP3 audio through `api.php?action=tts` and plays that audio.
Therefore YouTube Live receives the same generated Kurage voice that the local
viewer hears. Public FTP deployments should use the HTTP endpoint path so the
Apache/PHP host does not need local Python, edge-tts, or the kvtuber checkout.

AIRadio avoids long silent gaps by warming TTS audio ahead of playback:

- `api.php?action=start`, `interrupt`, and `next` enqueue `tts_prefetch.php` in the background.
- `airadio_worker.py` also starts `tts_prefetch.php` after adding newly generated segments.
- The browser prefetches the next few queued segments while the current segment is playing.
- The first segment may still need a short preparation message because both script and audio generation can start cold.

## YouTube Live

`api.php?action=youtube_start` can hand the AIRadio viewer URL to
`/home/kojima/work/kvtuber/scripts/youtube-live-rtmp.mjs`.

This keeps YouTube Live implementation in the Kurage VTuber layer and lets
AIRadio focus on the radio loop.

The stream key is not committed. AIRadio accepts a manual key from the UI, or
uses `YOUTUBE_STREAM_KEY`, `kvtuber/storage/youtube-live.json`, or
`airadio/storage/youtube-live.json` at runtime if one is already saved.

## Development

```bash
php -S 127.0.0.1:18080 -t src
# open http://127.0.0.1:18080/airadio.php
```

The app writes runtime state to `storage/`, which is intentionally not part of
Git history.

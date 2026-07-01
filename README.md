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
continue in the background. Before the first real script is ready, the UI shows
`台本作成中` silently instead of reading thin bridge copy. After the first
segment starts, AIRadio refills the script queue early so the radio can keep
talking with fewer gaps.

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
5. If no script exists yet, the broadcaster shows `台本作成中` silently and keeps polling.
6. When scripts exist, low queue depth triggers another background refill before the queue runs dry.
7. The avatar mouth switches while speaking.

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
このURLをテーマにして
初心者向けにこの資料を解説して
```

The UI immediately queues a short transition segment and starts background
research for that theme. Natural requests such as `...というテーマで話して`
are normalized into the actual topic before script generation. Beginner themes
such as `入門編` or `初心者向け` produce scripts that explain terms, first steps,
and common pitfalls instead of jumping into advanced monetization talk. The radio
keeps talking while the new script is built.

## Duration

The UI supports 1 to 6 hour sessions in 1 hour increments.

When the start text area has a free-form instruction, AIRadio treats that text
as the primary program direction and does not enqueue the profile-based seed
script. The profile is still available as background context, but the generated
program must follow the instruction text first.

## Voice / TTS

AIRadio uses the same Kurage-standard TTS path as the broader Kurage VTuber
tooling instead of browser `speechSynthesis`.

- Script: `/home/kojima/work/kvtuber/scripts/kurage-edge-tts.py`
- HTTP endpoint: `AIRADIO_TTS_ENDPOINT` or `http://exbridge.ddns.net:18308/kurage-tts/v1/audio/speech`
- Voice: `ja-JP-NanamiNeural`
- Rate: `+10%`
- Pitch: `-15Hz`
- Pronunciation normalization: `/home/kojima/work/kurage/backend/tts_normalizer.py`


## GitHub Repository Themes

When the editor enters a GitHub repository URL such as:

```text
https://github.com/datawhalechina/easy-vibe これをテーマに
```

AIRadio treats the repository as primary source material instead of just using
the URL as a search keyword. The background worker extracts `owner/repo`, reads
GitHub metadata and README content, summarizes the learning path, and passes
that material into the script prompt. X search remains supplemental.

This prevents repository-based topics from becoming generic AI talk. The
program should let Claude decide what matters from the README and metadata
instead of using hard-coded repository-specific talking points.

The spoken script must start with the topic itself, not meta explanations such
as "the editor instructed...". Repository URLs and `owner/repo` identifiers are
not read aloud. Internal account names are normalized to `編集者` before display
or speech. Do not add repository-specific script logic; source interpretation
belongs in the Claude prompt and generated script.

The browser requests MP3 audio through `api.php?action=tts` and plays that audio.
Therefore YouTube Live receives the same generated Kurage voice that the local
viewer hears. Public FTP deployments should use the HTTP endpoint path so the
Apache/PHP host does not need local Python, edge-tts, or the kvtuber checkout.

AIRadio avoids long silent gaps by warming TTS audio ahead of playback:

- `interrupt`, `next`, and newly generated queue items warm TTS in the background.
- `start` intentionally waits silently until the first real script exists, so it does not prefetch thin seed copy.
- `airadio_worker.py` also starts `tts_prefetch.php` after adding newly generated segments.
- The browser prefetches the next few queued segments while the current segment is playing.
- The first segment uses a silent `台本作成中` preparation state because both script and audio generation can start cold.

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

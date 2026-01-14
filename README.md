# AI Radio Generator

AI Radio Generator is an automated AI project that generates
radio-style audio episodes and podcast-compatible RSS feeds
from news articles or keywords.

Users receive ready-to-publish audio files and RSS feeds
without manual recording, editing, or voice work.

---

## What this project does

AI Radio Generator provides a complete, automated workflow:

- Ingests news articles or keyword-based content
- Generates radio-style scripts using large language models (LLMs)
- Converts scripts into natural-sounding speech via text-to-speech
- Outputs audio files and updates podcast-compatible RSS feeds

All steps are executed automatically.

---

## Outputs (What users get)

- 🎧 Radio-style audio episodes (WAV / MP3)
- 📡 Podcast-compatible RSS feeds ready for distribution
- ⚙️ Fully automated pipeline with no manual recording or editing

These outputs can be directly published to podcast platforms
or used as AI-generated audio content.

---

## Who this project is for

- Content creators experimenting with automated audio generation
- Educators exploring spoken summaries and AI narration
- Developers interested in AI-powered media pipelines
- Independent media projects and research prototypes

---

## Example outputs

- ▶ Sample audio: https://exbridge.ddns.net/aidexx/tts/2243b1178ef34e2698a5037bd26ba1d9.wav
- ▶ Sample RSS feed: https://exbridge.jp/aidexx/rss.xml

---

## How it works

1. Ingests news articles via RSS feeds or keyword-based search
2. Generates radio-style scripts using an LLM
3. Converts scripts into speech using a TTS engine
4. Processes audio/text for publishing
5. Outputs audio files and updates podcast-compatible RSS feeds

---

## Key features

- Fully automated end-to-end AI pipeline
- News-to-audio conversion
- Modular architecture (script generation, TTS, publishing)
- Self-hosted and customizable
- Open-source and extensible

---

## Tech stack

- Large Language Models (LLMs)
- Text-to-Speech (TTS)
- Podcast-compatible RSS generation
- Python and PHP-based automation scripts

---

## Repository structure

```text
.
├── src/
│   ├── airadio.php        # Core PHP orchestration logic
│   ├── airadio.py         # Python-based AI script generation
│   ├── ttsfile.php        # TTS integration and audio file handling
│   ├── tts2blog.py        # Audio/text post-processing and publishing utilities
│   ├── rss.php            # Podcast-compatible RSS feed generation
├── README.md
├── LICENSE
└── .gitignore

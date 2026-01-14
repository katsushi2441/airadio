# AI Radio Generator

AI Radio Generator is an automated AI project that generates
radio-style audio episodes and podcast-compatible RSS feeds
from news articles or keywords.

Users receive ready-to-publish audio files and RSS feeds
without manual recording, editing, or voice work.

This project focuses on clarity, automation, and practical
AI-powered content generation.

---

## What this project does

AI Radio Generator provides a complete, automated workflow:

- Ingests news articles or keyword-based content
- Generates radio-style scripts using large language models (LLMs)
- Converts scripts into natural-sounding speech via text-to-speech
- Outputs audio files and updates podcast-compatible RSS feeds

All steps are executed automatically.

---

## What users get (Outputs)

- 🎧 Radio-style audio episodes (WAV / MP3)
- 📡 Podcast-compatible RSS feeds ready for distribution
- ⚙️ Fully automated pipeline with no manual recording or editing

These outputs can be directly published to podcast platforms
or used as AI-generated audio content.

---

## Who this project is for

- Content creators who want automated audio generation
- Educators looking for spoken summaries or AI narration
- Developers exploring AI-powered media pipelines
- Podcasters experimenting with automated content production

## What this repository provides

This repository contains the open-source implementation of an automated
AI radio generation pipeline, including:

- Script generation from news or structured text using AI
- Text-to-speech (TTS) integration for audio output
- Podcast-compatible RSS feed generation
- Automation-oriented architecture for self-hosted deployment

This is **not a finished service**, but a reusable technical base for experimentation,
extension, and independent deployment.

---

## What you get

- 🎧 Automatically generated radio-style audio episodes (WAV / MP3)
- 📡 Podcast-compatible RSS feeds ready for distribution
- 🧠 AI-generated scripts using large language models (LLMs)
- 🔊 Text-to-speech synthesis for natural audio output
- ⚙️ Fully automated workflow from input to publication

---

## How it works

1. Ingests news articles via RSS feeds or keyword-based search
2. Generates radio-style scripts using an LLM
3. Converts scripts into speech using a TTS engine
4. Outputs audio files and updates podcast-compatible RSS feeds

All steps are automated and require no manual editing or voice recording.

---
## Example outputs

- ▶ Sample audio: https://exbridge.ddns.net/aidexx/tts/2243b1178ef34e2698a5037bd26ba1d9.wav
- ▶ Sample RSS feed: https://exbridge.jp/aidexx/rss.xml


---

## Who it’s for

- Developers interested in AI-powered media pipelines
- Content creators experimenting with automated audio generation
- Educators exploring spoken summaries and AI narration
- Independent media projects and research prototypes

---

## Features

- Fully automated end-to-end pipeline
- News-to-audio conversion
- Modular architecture (script generation, TTS, publishing)
- Self-hosted and customizable
- Open-source and extensible

---

## Tech stack

- Large Language Models (LLMs) for script generation
- Text-to-Speech (TTS) engines for audio synthesis
- RSS generation for podcast distribution
- Python and PHP-based automation scripts

---

## Repository structure

├── src/
│   ├── airadio.php        # Core PHP logic for orchestration and generation flow
│   ├── airadio.py         # Python-based AI script generation logic
│   ├── ttsfile.php        # TTS integration and audio file handling
│   ├── tts2blog.py        # Audio/text processing utilities
│   ├── rss.php            # Podcast-compatible RSS feed generation
├── README.md
├── LICENSE
└── .gitignore

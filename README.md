# AI Radio Generator

AI Radio Generator is an **early-stage open-source AI pipeline** that converts news
articles or keywords into short radio-style audio programs and
podcast-compatible RSS feeds.

This project provides the **core technical foundation** for generating and distributing
AI-powered audio content without manual recording or editing.
It is designed as an experimental and extensible media automation system.

---

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

- ▶ Sample audio: https://YOUR_AUDIO_SAMPLE_URL
- ▶ Sample RSS feed: https://YOUR_RSS_SAMPLE_URL

(Replace the URLs above with actual generated examples.)

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

```text
.
├── src/
│   ├── airadio.php        # Core PHP logic for orchestration and generation flow
│   ├── airadio.py         # Python-based AI script generation logic
│   ├── ttsfile.php        # TTS integration and audio file handling
│   ├── tts2blog.py        # Audio/text processing utilities
│   ├── rss.php            # Podcast-compatible RSS feed generation
│   └── ...
├── README.md
├── LICENSE
└── .gitignore

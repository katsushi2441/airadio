# AI Radio Generator

An open-source AI-powered radio generator that automatically creates short audio programs from news and structured data.

## Features
- Automatic script generation from news and keywords
- AI-based text-to-speech (TTS)
- RSS feed generation (Spotify-compatible)
- Designed for automated audio publishing

## Use Cases
- Independent AI radio
- Automated podcasts
- Educational audio content
- Experimental media automation

## Project Structure

This repository contains the core logic for an AI-powered radio generation system.
The project intentionally combines PHP and Python to support flexible deployment
and automation workflows.

## Source Code Overview

All core logic is located in the `src/` directory.

- `airadio.php`  
  Main PHP-based entry point for generating radio content.
  Handles request flow, data processing, and integration with TTS and RSS pipelines.

- `airadio.py`  
  Python-based script generation logic.
  Responsible for transforming news or structured data into radio-style scripts using AI.

- `tts2blog.py`  
  Utility script that converts generated scripts into audio-ready formats
  and supports publishing or blogging workflows.

- `ttsfile.php`  
  Handles text-to-speech file generation and audio output management.

  ## Roadmap

- Improve modularization of the generation pipeline
- Add configuration examples for easier setup
- Enhance RSS and podcast distribution support
- Documentation and usage examples

## Status
This project is under active development.
Early users, feedback, and contributors are welcome.

## License
MIT




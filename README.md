# AI Radio Generator

An open-source AI-powered radio generator that automatically creates short radio-style audio programs from news and structured data.

## What this repository provides

This repository provides the **core open-source implementation** of an AI-based radio generation pipeline.
It focuses on script generation, text-to-speech integration, and RSS feed output.
This is an early-stage project intended for experimentation and extension.

## Features
- Automatic script generation from news and keywords
- AI-based text-to-speech (TTS)
- RSS feed generation for podcast distribution
- Designed for automated and independent audio publishing

## Use Cases
- Independent AI radio experiments
- Automated podcast generation
- Educational and informational audio content
- Experimental media automation workflows

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
  Responsible for transforming news or struct

<?php
const AIRADIO_APP_NAME = 'Kurage AI VTuber Radio';
const AIRADIO_ALLOWED_USER = 'xb_bittensor';
const AIRADIO_STORAGE_DIR = __DIR__ . '/../storage';
const AIRADIO_STATE_FILE = AIRADIO_STORAGE_DIR . '/radio_state.json';
const AIRADIO_QUEUE_FILE = AIRADIO_STORAGE_DIR . '/script_queue.json';
const AIRADIO_CURRENT_FILE = AIRADIO_STORAGE_DIR . '/current_segment.json';
const AIRADIO_LOG_FILE = AIRADIO_STORAGE_DIR . '/radio_loop.log';
const AIRADIO_WORKER_LOCK = AIRADIO_STORAGE_DIR . '/worker.lock';
const AIRADIO_MEMORY_FILE = AIRADIO_STORAGE_DIR . '/talk_memory.json';
const AIRADIO_COMMENTS_FILE = AIRADIO_STORAGE_DIR . '/comments.json';
const AIRADIO_PUBLIC_BASE_URL = 'https://airadio.exbridge.jp/airadio.php';
const AIRADIO_OLLAMA_URL = 'http://192.168.0.3:11434/api/generate';
const AIRADIO_OLLAMA_MODEL = 'gemma4:12b-it-qat';
const AIRADIO_KAGENTREACH_DIR = '/home/kojima/work/kagentreach';
const AIRADIO_KVTUBER_DIR = '/home/kojima/work/kvtuber';
const AIRADIO_TTS_CACHE_DIR = AIRADIO_STORAGE_DIR . '/tts';
const AIRADIO_TTS_PYTHON = '/usr/bin/python3';
const AIRADIO_TTS_SCRIPT = AIRADIO_KVTUBER_DIR . '/scripts/kurage-edge-tts.py';
const AIRADIO_TTS_VOICE = 'ja-JP-NanamiNeural';
const AIRADIO_TTS_RATE = '+10%';
const AIRADIO_TTS_PITCH = '-15Hz';
if (!defined('AIRADIO_TTS_ENDPOINT')) {
    define('AIRADIO_TTS_ENDPOINT', getenv('AIRADIO_TTS_ENDPOINT') ?: 'http://exbridge.ddns.net:18308/kurage-tts/v1/audio/speech');
}

if (!defined('AIGM_BASE_URL')) { define('AIGM_BASE_URL', 'https://airadio.exbridge.jp'); }
if (!defined('AIGM_AUTH_BASE_URL')) { define('AIGM_AUTH_BASE_URL', 'https://aiknowledgecms.exbridge.jp'); }
if (!defined('AIGM_COOKIE_DOMAIN')) { define('AIGM_COOKIE_DOMAIN', '.exbridge.jp'); }
if (!defined('AIGM_ADMIN')) { define('AIGM_ADMIN', AIRADIO_ALLOWED_USER); }

if (!is_dir(AIRADIO_STORAGE_DIR)) { mkdir(AIRADIO_STORAGE_DIR, 0775, true); }
if (!is_dir(AIRADIO_TTS_CACHE_DIR)) { mkdir(AIRADIO_TTS_CACHE_DIR, 0775, true); }

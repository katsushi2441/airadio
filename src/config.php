<?php
const AIRADIO_APP_NAME = 'Kurage AI VTuber Radio';
const AIRADIO_ALLOWED_USER = 'xb_bittensor';
const AIRADIO_STORAGE_DIR = __DIR__ . '/../storage';
const AIRADIO_STATE_FILE = AIRADIO_STORAGE_DIR . '/radio_state.json';
const AIRADIO_QUEUE_FILE = AIRADIO_STORAGE_DIR . '/script_queue.json';
const AIRADIO_LOG_FILE = AIRADIO_STORAGE_DIR . '/radio_loop.log';
const AIRADIO_WORKER_LOCK = AIRADIO_STORAGE_DIR . '/worker.lock';
const AIRADIO_PUBLIC_BASE_URL = 'https://airadio.exbridge.jp/airadio.php';
const AIRADIO_OLLAMA_URL = 'http://192.168.0.3:11434/api/generate';
const AIRADIO_OLLAMA_MODEL = 'gemma4:12b-it-qat';
const AIRADIO_KAGENTREACH_DIR = '/home/kojima/work/kagentreach';
const AIRADIO_KVTUBER_DIR = '/home/kojima/work/kvtuber';

if (!is_dir(AIRADIO_STORAGE_DIR)) { mkdir(AIRADIO_STORAGE_DIR, 0775, true); }

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
STORAGE = ROOT / 'storage'
STATE = STORAGE / 'radio_state.json'
QUEUE = STORAGE / 'script_queue.json'
CURRENT = STORAGE / 'current_segment.json'
LOG = STORAGE / 'radio_loop.log'

KVTUBER_CONTROL_BASE = os.environ.get('AIRADIO_KVTUBER_CONTROL_BASE', 'http://127.0.0.1:18308').rstrip('/')
KVTUBER_ADMIN_TOKEN = os.environ.get('AIRADIO_KVTUBER_ADMIN_TOKEN', os.environ.get('KURAGE_ADMIN_TOKEN', ''))


def now_iso() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%S%z')


def append_log(message: str, data: dict[str, Any] | None = None) -> None:
    STORAGE.mkdir(parents=True, exist_ok=True)
    with LOG.open('a', encoding='utf-8') as f:
        f.write(json.dumps({'time': now_iso(), 'message': message, 'data': data or {}}, ensure_ascii=False) + '\n')


def read_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return fallback


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)


def parse_state_time(value: str) -> float:
    text = str(value or '').strip()
    for fmt in ('%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(text, fmt).timestamp()
        except Exception:
            pass
    return 0.0


def update_state(patch: dict[str, Any]) -> dict[str, Any]:
    state = read_json(STATE, {})
    if not isinstance(state, dict):
        state = {}
    state.update(patch)
    state['updated_at'] = now_iso()
    write_json(STATE, state)
    return state


def stop_youtube_live(reason: str) -> dict[str, Any]:
    if not KVTUBER_ADMIN_TOKEN:
        return {'ok': False, 'skipped': True, 'reason': 'kvtuber_admin_token_not_configured'}
    try:
        res = requests.post(
            f'{KVTUBER_CONTROL_BASE}/control/youtube-live/stop',
            headers={'X-Admin-Token': KVTUBER_ADMIN_TOKEN},
            timeout=30,
        )
        try:
            result = res.json()
        except Exception:
            result = {'status_code': res.status_code, 'text': res.text[-500:]}
        return {'ok': res.status_code < 400 and not (isinstance(result, dict) and result.get('ok') is False), 'status_code': res.status_code, 'result': result}
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--started-at', required=True)
    parser.add_argument('--ends-at', required=True)
    parser.add_argument('--reason', default='duration_elapsed')
    args = parser.parse_args()

    end_ts = parse_state_time(args.ends_at)
    if not end_ts:
        append_log('duration_guard_invalid_end_time', {'started_at': args.started_at, 'ends_at': args.ends_at})
        return 2

    sleep_for = max(0.0, end_ts - time.time())
    append_log('duration_guard_waiting', {'started_at': args.started_at, 'ends_at': args.ends_at, 'sleep_seconds': round(sleep_for, 1)})
    if sleep_for:
        time.sleep(sleep_for)

    state = read_json(STATE, {})
    if state.get('started_at') != args.started_at:
        append_log('duration_guard_skipped_newer_program', {'guard_started_at': args.started_at, 'current_started_at': state.get('started_at')})
        return 0
    if state.get('status') != 'on_air':
        append_log('duration_guard_skipped_not_on_air', {'started_at': args.started_at, 'status': state.get('status')})
        return 0
    if time.time() < end_ts - 2:
        append_log('duration_guard_skipped_not_due', {'started_at': args.started_at, 'ends_at': args.ends_at})
        return 0

    write_json(CURRENT, {'item': None, 'updated_at': now_iso()})
    write_json(QUEUE, {'items': [], 'updated_at': now_iso()})
    result = stop_youtube_live(args.reason)
    update_state({
        'status': 'idle',
        'loop_state': 'stopped',
        'now_talking': '',
        'research_status': 'idle',
        'stopped_reason': args.reason,
        'duration_guard_stopped_at': now_iso(),
    })
    append_log('duration_guard_stopped_program', {'started_at': args.started_at, 'ends_at': args.ends_at, 'youtube_stop': result})
    return 0 if result.get('ok') or result.get('skipped') else 1


if __name__ == '__main__':
    raise SystemExit(main())

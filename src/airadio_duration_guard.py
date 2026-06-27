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
KVTUBER_ROOT = Path(os.environ.get('AIRADIO_KVTUBER_ROOT', '/home/kojima/work/kvtuber'))
KVTUBER_YOUTUBE_SCRIPT = Path(os.environ.get('AIRADIO_KVTUBER_YOUTUBE_SCRIPT', str(KVTUBER_ROOT / 'scripts/youtube-live-rtmp.mjs')))


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
    api_result: dict[str, Any] | None = None
    if KVTUBER_ADMIN_TOKEN:
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
            ok = res.status_code < 400 and not (isinstance(result, dict) and result.get('ok') is False)
            if ok:
                return {'ok': True, 'method': 'control-api', 'status_code': res.status_code, 'result': result}
            api_result = {'ok': False, 'status_code': res.status_code, 'result': result}
        except Exception as exc:
            api_result = {'ok': False, 'error': str(exc)}
    if KVTUBER_YOUTUBE_SCRIPT.exists():
        import subprocess
        try:
            proc = subprocess.run(
                ['node', str(KVTUBER_YOUTUBE_SCRIPT), 'stop'],
                cwd=str(KVTUBER_ROOT),
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            return {
                'ok': proc.returncode == 0,
                'method': 'local-kvtuber-script',
                'api_result': api_result,
                'stdout': proc.stdout[-1200:],
                'stderr': proc.stderr[-1200:],
            }
        except Exception as exc:
            return {'ok': False, 'method': 'local-kvtuber-script', 'api_result': api_result, 'error': str(exc)}
    return {'ok': False, 'method': 'none', 'api_result': api_result, 'reason': 'no_stop_method_available'}


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

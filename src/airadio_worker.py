#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STORAGE = ROOT / 'storage'
QUEUE = STORAGE / 'script_queue.json'
STATE = STORAGE / 'radio_state.json'
LOCK = STORAGE / 'worker.lock'
KAGENTREACH = Path(os.environ.get('AIRADIO_KAGENTREACH_DIR', '/home/kojima/work/kagentreach'))
OLLAMA_URL = os.environ.get('AIRADIO_OLLAMA_URL', 'http://192.168.0.3:11434/api/generate')
OLLAMA_MODEL = os.environ.get('AIRADIO_OLLAMA_MODEL', 'gemma4:12b-it-qat')
LOCK_TTL_SECONDS = int(os.environ.get('AIRADIO_WORKER_LOCK_TTL', '900'))


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


def log_event(message: str, **data: Any) -> None:
    payload = {
        'time': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'message': message,
        'data': data,
    }
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def update_state(**patch: Any) -> None:
    state = read_json(STATE, {})
    state.update(patch)
    state['updated_at'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    write_json(STATE, state)


def append_queue(items: list[dict[str, Any]]) -> None:
    queue = read_json(QUEUE, {'items': []})
    existing = queue.get('items') if isinstance(queue.get('items'), list) else []
    existing.extend(items)
    queue['items'] = existing[-80:]
    queue['updated_at'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    write_json(QUEUE, queue)


def pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def acquire_lock() -> bool:
    if LOCK.exists():
        age = time.time() - LOCK.stat().st_mtime
        try:
            pid = int(LOCK.read_text(encoding='utf-8').strip() or '0')
        except Exception:
            pid = 0
        if pid and pid_is_alive(pid) and age < LOCK_TTL_SECONDS:
            log_event('worker_lock_active', pid=pid, age=round(age, 1))
            return False
        log_event('worker_lock_stale_removed', pid=pid, age=round(age, 1))
        try:
            LOCK.unlink()
        except FileNotFoundError:
            pass
    LOCK.write_text(str(os.getpid()), encoding='utf-8')
    return True


def run_x_search(theme: str) -> dict[str, Any]:
    if os.environ.get('AIRADIO_DISABLE_BROWSER_RESEARCH') == '1':
        return {'ok': False, 'skipped': True, 'reason': 'AIRADIO_DISABLE_BROWSER_RESEARCH=1'}
    script = KAGENTREACH / 'scripts' / 'x-search-browser-use.py'
    if not script.exists():
        return {'ok': False, 'error': 'x-search script not found'}
    query = f'{theme} lang:ja OR lang:en'
    python_bin = os.environ.get('BROWSER_AGENT_PYTHON', '/home/kojima/work/browser_agent/.venv/bin/python')
    if not Path(python_bin).exists():
        python_bin = sys.executable
    cmd = [python_bin, str(script), query, '--limit', '6', '--mode', 'top', '--host', os.environ.get('BROWSER_USE_OLLAMA_HOST', 'http://192.168.0.3:11434')]
    try:
        proc = subprocess.run(cmd, cwd=str(KAGENTREACH), text=True, capture_output=True, timeout=240, check=False)
        raw = proc.stdout.strip().split('\n')[-1] if proc.stdout.strip() else '{}'
        try:
            parsed = json.loads(proc.stdout)
        except Exception:
            parsed = {'ok': proc.returncode == 0, 'raw': proc.stdout[-3000:]}
        if proc.returncode != 0:
            parsed['stderr'] = proc.stderr[-1200:]
        return parsed
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}


def ollama(prompt: str, timeout: int = 240) -> str:
    payload = {'model': OLLAMA_MODEL, 'prompt': prompt, 'stream': False, 'format': 'json'}
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=timeout) as res:
        data = json.loads(res.read().decode('utf-8', errors='replace') or '{}')
    return str(data.get('response') or '')


def parse_json_object(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass
    start = text.find('{')
    end = text.rfind('}')
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def fallback_segments(theme: str) -> list[dict[str, Any]]:
    base = [
        f'今夜のテーマは、{theme}です。急がず、ひとつずつ考えていきます。結論を急がず、言葉の輪郭を静かに整えていきましょう。',
        'AI思考のラジオでは、答えを一気に出すよりも、問いを少しずつ深くしていきます。聞き流していても大丈夫です。大事なところだけ、心に残れば十分です。',
        'もし眠くなってきたら、そのまま目を閉じてください。話はゆっくり続きます。思考は流れ、必要な言葉だけが残っていきます。',
        f'{theme}を仕事に活かすなら、最初から大きな成果を狙わなくても大丈夫です。小さな確認、小さな試作、小さな改善を重ねることが、いちばん確かな前進になります。',
        '裏側では情報を集め、表側では話を止めない。この二つの流れを分けておくと、AIの待ち時間はサービスの沈黙ではなく、次の話題を育てる時間に変わります。',
        '今日の結論を急ぐ必要はありません。大切なのは、いま聞いた言葉の中から、明日の自分に少し役立つものを一つだけ残しておくことです。',
    ]
    return [{'id': f'fallback-{int(time.time())}-{i}', 'theme': theme, 'text': text, 'source': 'fallback'} for i, text in enumerate(base)]


def bridge_segments(theme: str) -> list[dict[str, Any]]:
    base = [
        f'{theme}について考えるとき、まず大切なのは、流行語として追いかけすぎないことです。道具、習慣、仕事の進め方がどう変わるのかを、静かに分けて見ていきます。',
        '新しい技術は、派手な成功例だけを見ると疲れてしまいます。けれど、毎日の小さな作業を少し楽にする視点で見ると、使いどころが自然に見えてきます。',
        'ここからは、情報収集で見つかった論点を、いったん生活や仕事の言葉に置き換えていきます。難しい言葉を急いで覚えるより、何に役立つのかをゆっくり確認しましょう。',
        '今日の話をひとつだけ持ち帰るなら、AIに任せる部分と、人が判断する部分を分けることです。その境目を丁寧に決めるほど、仕事は落ち着いて進みます。',
    ]
    now = int(time.time())
    return [
        {
            'id': f'bridge-{now}-{i}',
            'theme': theme,
            'title': f'{theme}の考え方 {i + 1}',
            'text': text,
            'source': 'bridge',
            'created_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        }
        for i, text in enumerate(base)
    ]


def build_segments(theme: str, profile: dict[str, Any], research: dict[str, Any]) -> list[dict[str, Any]]:
    profile_text = json.dumps(profile, ensure_ascii=False)[:1200]
    research_text = json.dumps(research, ensure_ascii=False)[:5000]
    prompt = f'''
あなたは「聴きながらよく寝れる - AI思考のラジオ」の構成作家です。
Kurage AI VTuberが、眠りを妨げない穏やかな声で話し続けるための短い台本キューを作ってください。

テーマ: {theme}
ログインユーザ/Xプロフィール: {profile_text}
情報収集メモ: {research_text}

要件:
- 日本語。
- 1本あたり45〜90秒程度で読める長さ。
- 強い煽り、断定、怒り、過度なテンションは禁止。
- 聴き流せるが、内容は薄くしない。
- kagentreachの情報収集に基づく感じで、具体的な論点、ツール、見方を入れる。
- 眠りを促すラジオなので、語尾は落ち着かせる。
- JSONだけで返す。shape: {{"segments":[{{"title":"...","text":"...","source":"..."}}]}}
- segmentsは6個。
'''.strip()
    try:
        response = ollama(prompt)
        parsed = parse_json_object(response)
        if not parsed:
            raise ValueError('Ollama response did not contain a valid JSON object')
        segs = parsed.get('segments') if isinstance(parsed, dict) else []
        out = []
        for i, seg in enumerate(segs[:8]):
            text = re.sub(r'\s+', ' ', str(seg.get('text') or '')).strip()
            if len(text) < 40:
                continue
            if sum(1 for ch in text if '\u3040' <= ch <= '\u30ff' or '\u4e00' <= ch <= '\u9fff') < 25:
                continue
            out.append({
                'id': f'{int(time.time())}-{i}',
                'theme': theme,
                'title': str(seg.get('title') or f'{theme} {i+1}'),
                'text': text,
                'source': str(seg.get('source') or 'ollama+kagentreach'),
                'created_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            })
        if len(out) >= 4:
            return out
        if out:
            out.extend(bridge_segments(theme)[: 6 - len(out)])
            return out
    except Exception as exc:
        update_state(research_status='fallback', last_error=str(exc)[-500:])
    return fallback_segments(theme)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--payload', required=True)
    args = parser.parse_args()
    payload = read_json(Path(args.payload), {})
    theme = str(payload.get('theme') or 'AI思考とバイブコーディング')
    profile = payload.get('profile') if isinstance(payload.get('profile'), dict) else {}

    if not acquire_lock():
        return
    try:
        log_event('worker_started', pid=os.getpid(), theme=theme)
        update_state(research_status='collecting', loop_state='background_research', current_research_theme=theme)
        research = run_x_search(theme)
        log_event('research_finished', theme=theme, ok=research.get('ok'), skipped=research.get('skipped', False))
        update_state(research_status='scripting', last_research=research)
        segments = build_segments(theme, profile, research)
        append_queue(segments)
        log_event('segments_appended', theme=theme, count=len(segments), sources=sorted({str(s.get('source')) for s in segments}))
        update_state(research_status='ready', loop_state='queue_refilled', last_segments=len(segments), current_research_theme=theme)
    except Exception as exc:
        # The foreground radio must keep talking even if research or LLM generation fails.
        segments = fallback_segments(theme)
        append_queue(segments)
        log_event('worker_failed_fallback_appended', theme=theme, error=str(exc)[-800:], count=len(segments))
        update_state(
            research_status='fallback',
            loop_state='queue_refilled',
            last_segments=len(segments),
            current_research_theme=theme,
            last_error=str(exc)[-800:],
        )
    finally:
        try:
            LOCK.unlink()
        except FileNotFoundError:
            pass


if __name__ == '__main__':
    main()

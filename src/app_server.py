#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
STORAGE = ROOT / 'storage'
STATE = STORAGE / 'radio_state.json'
QUEUE = STORAGE / 'script_queue.json'
CURRENT = STORAGE / 'current_segment.json'
MEMORY = STORAGE / 'talk_memory.json'
COMMENTS = STORAGE / 'comments.json'
WORKER_PAYLOAD = STORAGE / 'worker_payload.json'
LOG = STORAGE / 'radio_loop.log'
TTS_CACHE = STORAGE / 'tts'
ALLOWED_USER = os.environ.get('AIRADIO_ALLOWED_USER', 'xb_bittensor')
TTS_ENDPOINT = os.environ.get('AIRADIO_TTS_ENDPOINT', 'http://exbridge.ddns.net:18308/kurage-tts/v1/audio/speech')
PUBLIC_BASE_URL = os.environ.get('AIRADIO_PUBLIC_BASE_URL', 'https://airadio.exbridge.jp/airadio.php')
TTS_VOICE = os.environ.get('AIRADIO_TTS_VOICE', 'ja-JP-NanamiNeural')
TTS_RATE = os.environ.get('AIRADIO_TTS_RATE', '+10%')
TTS_PITCH = os.environ.get('AIRADIO_TTS_PITCH', '-15Hz')
TTS_SPEED = float(os.environ.get('AIRADIO_TTS_SPEED', '1.1'))
TTS_PREFETCH_LIMIT = int(os.environ.get('AIRADIO_TTS_PREFETCH_LIMIT', '4'))
KVTUBER_CONTROL_BASE = os.environ.get('AIRADIO_KVTUBER_CONTROL_BASE', 'http://127.0.0.1:18308').rstrip('/')
KVTUBER_ADMIN_TOKEN = os.environ.get('AIRADIO_KVTUBER_ADMIN_TOKEN', os.environ.get('KURAGE_ADMIN_TOKEN', ''))
KVTUBER_YOUTUBE_CONFIG = Path(os.environ.get('AIRADIO_KVTUBER_YOUTUBE_CONFIG', '/home/kojima/work/kvtuber/storage/youtube-live.json'))
KVTUBER_LEGACY_YOUTUBE_CONFIG = Path(os.environ.get('AIRADIO_KVTUBER_LEGACY_YOUTUBE_CONFIG', '/home/kojima/work/kvtuber/aituber-onair/storage/youtube-live.json'))

app = FastAPI(title='Kurage AI VTuber Radio API')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])


def now_iso() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%S%z')


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


def append_log(message: str, data: dict[str, Any] | None = None) -> None:
    STORAGE.mkdir(parents=True, exist_ok=True)
    LOG.open('a', encoding='utf-8').write(json.dumps({'time': now_iso(), 'message': message, 'data': data or {}}, ensure_ascii=False) + '\n')


def state() -> dict[str, Any]:
    return read_json(STATE, {
        'status': 'idle', 'theme': '編集者が選ぶテーマを静かに深掘りするラジオ',
        'duration_hours': 1, 'started_at': '', 'ends_at': '', 'loop_state': 'waiting',
        'now_talking': '', 'research_status': 'idle', 'updated_at': now_iso(),
    })


def update_state(patch: dict[str, Any]) -> dict[str, Any]:
    s = state()
    s.update(patch)
    s['updated_at'] = now_iso()
    write_json(STATE, s)
    return s


def queue() -> dict[str, Any]:
    q = read_json(QUEUE, {'items': []})
    if not isinstance(q.get('items'), list):
        q['items'] = []
    return q


def current() -> dict[str, Any]:
    return read_json(CURRENT, {'item': None, 'updated_at': ''})


def write_current(item: Any) -> dict[str, Any]:
    data = {'item': item, 'updated_at': now_iso()}
    write_json(CURRENT, data)
    return data


def comments() -> dict[str, Any]:
    c = read_json(COMMENTS, {'items': []})
    if not isinstance(c.get('items'), list):
        c['items'] = []
    c['items'] = c['items'][-80:]
    return c


def add_comment(user: str, text: str, is_admin: bool) -> dict[str, Any]:
    text = re.sub(r'\s+', ' ', text or '').strip()[:500]
    if not text:
        raise HTTPException(400, 'comment_required')
    c = comments()
    item = {
        'id': f'comment-{int(time.time())}-{abs(hash(text + str(time.time()))) % 100000000:08d}',
        'user': '編集者' if is_admin else (user or 'リスナー'),
        'role': 'editor' if is_admin else 'listener',
        'text': text,
        'created_at': now_iso(),
    }
    c['items'].append(item)
    c['items'] = c['items'][-80:]
    c['updated_at'] = now_iso()
    write_json(COMMENTS, c)
    return item


def extract_github_repo_label(text: str) -> str:
    m = re.search(r'https?://github\.com/([^/\s]+)/([^/\s?#]+)', text or '', re.I)
    if not m:
        return ''
    repo = re.sub(r'\.git$', '', m.group(2), flags=re.I)
    return f'{m.group(1)}/{repo}'


def extract_urls(text: str, limit: int = 12) -> list[str]:
    urls = re.findall(r'https?://[^\s「」『』"\'`<>]+', text or '')
    cleaned: list[str] = []
    for url in urls:
        url = url.rstrip('。、.!！?)]）')
        if url and url not in cleaned:
            cleaned.append(url)
        if len(cleaned) >= limit:
            break
    return cleaned


def normalize_url_list(text: str) -> str:
    return '\n'.join(extract_urls(text))


def spoken_theme_title(theme: str, instruction: str = '') -> str:
    source = instruction.strip() or theme
    url_count = len(extract_urls(source))
    if url_count >= 2:
        return f'{url_count}本の資料'
    if extract_github_repo_label(source) or re.search(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', theme or ''):
        return 'このリポジトリ'
    if re.search(r'https?://', source or ''):
        return 'この資料'
    spoken = re.sub(r'https?://[^\s「」『』"\'`<>]+', '', theme or '')
    spoken = re.sub(r'\s+', ' ', spoken).strip()
    return spoken or 'このテーマ'


def normalize_theme_request(text: str) -> str:
    original = (text or '').strip()
    if not original:
        return ''
    urls = extract_urls(original)
    if urls:
        return '\n'.join(urls)
    repo = extract_github_repo_label(original)
    cleaned = re.sub(r'[「」『』"\'`]', '', original)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    for pat in [
        r'^(.+?)(?:という|っていう|といった)?テーマで(?:話して|話す|解説して|教えて|お願いします|ください)?[。.!！]*$',
        r'^(.+?)(?:を|について)(?:テーマにして|話して|解説して|教えて|お願いします|ください)[。.!！]*$',
        r'^(.+?)(?:を|について)(?:初心者向けに|入門向けに)?(?:話して|解説して|教えて|お願いします|ください)[。.!！]*$',
    ]:
        m = re.match(pat, cleaned)
        if m and m.group(1).strip():
            cleaned = m.group(1).strip()
            break
    cleaned = re.sub(r'(?:という|っていう|といった)?テーマ$', '', cleaned).strip('。、.!！? ')
    cleaned = re.sub(r'(?:を|について)$', '', cleaned).strip('。、.!！? ')
    if repo:
        if not cleaned or cleaned.startswith('http'):
            return f'{repo} の教材内容'
        if repo not in cleaned:
            return f'{repo} の教材内容: {cleaned}'
    return cleaned or original


def theme_guidance(theme: str) -> str:
    url_count = len(extract_urls(theme))
    if url_count >= 2:
        return '複数URLを一次資料として扱い、共通点、違い、重要論点、実践上の意味を整理して話す。URL文字列は読み上げない。'
    if url_count == 1:
        return 'URL先の本文を一次資料として扱い、内容を読んで要点、背景、使いどころ、注意点を考察して話す。URL文字列は読み上げない。'
    if extract_github_repo_label(theme) or re.search(r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', theme or ''):
        return 'GitHubリポジトリを一次資料として扱い、READMEとリポジトリ情報から重要点を判断して話す。資料にない文脈を勝手に足さない。'
    if re.search(r'入門|初心者|初級|はじめて|基礎', theme or ''):
        return '初心者向けに、専門用語を短く説明し、初めて聞く人が理解できる順番で話す。'
    if re.search(r'応用|実践', theme or ''):
        return '実践者向けに、具体的な手順、検証方法、失敗時の立て直しを中心に話す。'
    return '入力されたテーマの意図を保ち、一般論に薄めず、資料や指示に沿って話す。'


def seed_instruction_program(theme: str, instruction: str) -> list[dict[str, Any]]:
    ts = int(time.time())
    spoken = spoken_theme_title(theme, instruction)
    return [{
        'id': f'instruction-seed-{ts}-0', 'theme': theme, 'requested_theme': instruction,
        'title': spoken, 'text': f'{spoken}について、資料の内容から順に見ていきます。まずは全体像、次に重要なポイント、最後に使いどころを整理します。',
        'source': 'instruction-seed-opening', 'created_at': now_iso(),
    }]


def seed_url_program(urls: list[str]) -> list[dict[str, Any]]:
    ts = int(time.time())
    title = f'{len(urls)}本の資料' if len(urls) >= 2 else 'この資料'
    return [{
        'id': f'url-seed-{ts}-0', 'theme': '\n'.join(urls), 'requested_theme': '\n'.join(urls),
        'title': title,
        'text': f'{title}の内容を読み取りながら、要点、背景、共通点、違い、実践で役立つポイントを順番に考察します。',
        'source': 'url-seed-opening',
        'created_at': now_iso(),
    }]


def seed_profile_program(theme: str) -> list[dict[str, Any]]:
    ts = int(time.time())
    return [{
        'id': f'seed-{ts}-0', 'theme': theme, 'title': 'オープニング',
        'text': '今夜は、プロフィールから見えてくる関心に沿って話します。具体的な中身は、集めた情報と台本生成の結果をもとに、順番に深めていきます。',
        'source': 'profile-seed-opening', 'created_at': now_iso(),
    }]


def default_theme_from_profile(profile: dict[str, Any]) -> str:
    if (profile.get('description') or '').strip():
        return 'Xプロフィールに合わせて、編集者が関心を持つテーマを静かに深掘りする'
    return '編集者が選ぶテーマを静かに深掘りする'


def fetch_x_profile(username: str = ALLOWED_USER) -> dict[str, Any]:
    username = re.sub(r'[^A-Za-z0-9_]', '', username or ALLOWED_USER) or ALLOWED_USER
    cache = STORAGE / f'x_profile_{username}.json'
    cached = read_json(cache, {})
    if cached.get('username') and cached.get('description') and time.time() - int(cached.get('cached_at') or 0) < 3600:
        return cached
    profile = {'username': username, 'name': username, 'description': '', 'source': 'fxtwitter'}
    try:
        data = requests.get(f'https://api.fxtwitter.com/{username}', headers={'User-Agent': 'KurageAIRadio/0.1'}, timeout=12).json()
        user = data.get('user') or {}
        desc = (user.get('raw_description') or {}).get('text') or user.get('description') or ''
        if user:
            profile = {
                'username': user.get('screen_name') or username, 'name': user.get('name') or username,
                'description': desc, 'followers': int(user.get('followers') or 0), 'following': int(user.get('following') or 0),
                'tweets': int(user.get('tweets') or 0), 'likes': int(user.get('likes') or 0),
                'url': user.get('url') or f'https://x.com/{username}', 'source': 'fxtwitter', 'cached_at': int(time.time()),
            }
            write_json(cache, profile)
    except Exception:
        if cached:
            return cached
    return profile


def auth_from_header(auth_header: str | None) -> dict[str, Any]:
    if not auth_header:
        return {'logged_in': False, 'allowed': False, 'session_user': '', 'is_admin': False}
    try:
        auth = json.loads(auth_header)
        if isinstance(auth, dict):
            return auth
    except Exception:
        pass
    return {'logged_in': False, 'allowed': False, 'session_user': '', 'is_admin': False}


def require_admin(auth: dict[str, Any]) -> None:
    if not auth.get('is_admin'):
        raise HTTPException(403, 'admin_required')


def reset_program_memory() -> None:
    write_json(QUEUE, {'items': [], 'updated_at': now_iso()})
    write_current(None)
    write_json(MEMORY, {'fingerprints': [], 'topics': [], 'recent_texts': [], 'updated_at': now_iso()})
    old = state()
    for key in ['last_error', 'last_research', 'last_segments', 'current_research_theme', 'bridge_count', 'tts_status', 'tts_cached', 'tts_failed', 'tts_prefetch_reason']:
        old.pop(key, None)
    old.update({'status': 'idle', 'loop_state': 'waiting', 'research_status': 'idle', 'now_talking': '', 'updated_at': now_iso()})
    write_json(STATE, old)


def start_worker(theme: str, profile: dict[str, Any], reason: str, extra: dict[str, Any] | None = None) -> int:
    payload = {'theme': theme, 'profile': profile, 'reason': reason, 'created_at': now_iso()}
    payload.update(extra or {})
    write_json(WORKER_PAYLOAD, payload)
    env = os.environ.copy()
    env['AIRADIO_DISABLE_SERVER_TTS_PREFETCH'] = '1'
    log = LOG.open('ab')
    proc = subprocess.Popen([sys.executable, str(SRC / 'airadio_worker.py'), '--payload', str(WORKER_PAYLOAD)], cwd=str(ROOT), stdout=log, stderr=log, start_new_session=True, env=env)
    append_log('worker_started', {'pid': proc.pid, 'theme': theme, 'reason': reason})
    return proc.pid


def audio_for_text(text: str) -> bytes:
    text = (text or '').strip()
    if not text:
        raise HTTPException(400, 'tts_text_required')
    TTS_CACHE.mkdir(parents=True, exist_ok=True)
    import hashlib
    h = hashlib.sha256((TTS_ENDPOINT + '\n' + TTS_VOICE + '\n' + TTS_RATE + '\n' + TTS_PITCH + '\n' + text).encode('utf-8')).hexdigest()
    path = TTS_CACHE / f'{h}.mp3'
    if path.exists() and path.stat().st_size > 1000:
        return path.read_bytes()
    res = requests.post(TTS_ENDPOINT, json={'input': text, 'voice': TTS_VOICE, 'speed': TTS_SPEED}, timeout=60)
    content_type = res.headers.get('content-type', '').lower()
    if res.status_code >= 400 or not content_type.startswith('audio/') or len(res.content) <= 1000:
        raise HTTPException(502, 'tts_failed')
    path.write_bytes(res.content)
    return res.content


def default_stream_key() -> str:
    env_key = os.environ.get('YOUTUBE_STREAM_KEY', '').strip()
    if env_key:
        return env_key
    for path in [KVTUBER_YOUTUBE_CONFIG, KVTUBER_LEGACY_YOUTUBE_CONFIG]:
        config = read_json(path, {})
        if isinstance(config, dict):
            key = str(config.get('streamKey') or '').strip()
            if key:
                return key
    return ''


def has_default_stream_key() -> bool:
    return bool(default_stream_key())


def broadcast_viewer_url(url: str) -> str:
    url = (url or PUBLIC_BASE_URL).strip() or PUBLIC_BASE_URL
    if 'airadio.php' not in url:
        return url
    separator = '&' if '?' in url else '?'
    if 'broadcast=1' not in url:
        url = f'{url}{separator}broadcast=1'
    return url.replace('airadio_login=1', '').replace('airadio_logout=1', '')


@app.get('/health')
def health() -> dict[str, Any]:
    return {'ok': True, 'service': 'airadio-app', 'time': now_iso(), 'storage': str(STORAGE)}


@app.api_route('/api/{action}', methods=['GET', 'POST'])
async def api_action(action: str, request: Request, x_airadio_auth: str | None = Header(default=None)):
    auth = auth_from_header(x_airadio_auth)
    if not auth.get('allowed'):
        raise HTTPException(401, 'not_allowed')
    body: dict[str, Any] = {}
    if request.method == 'POST':
        try:
            body = await request.json()
            if not isinstance(body, dict):
                body = {}
        except Exception:
            body = {}

    if action == 'status':
        return {'ok': True, 'auth': auth, 'state': state(), 'queue': queue(), 'current': current(), 'comments': comments(), 'youtube': {'has_default_stream_key': has_default_stream_key()}}
    if action == 'profile':
        return {'ok': True, 'profile': fetch_x_profile(ALLOWED_USER)}
    if action == 'current':
        return {'ok': True, 'state': state(), 'current': current(), 'comments': comments()}
    if action == 'comments':
        return {'ok': True, 'comments': comments()}
    if action == 'comment':
        item = add_comment(str(auth.get('session_user') or ''), str(body.get('text') or ''), bool(auth.get('is_admin')))
        return {'ok': True, 'comment': item, 'comments': comments()}
    if action == 'tts':
        audio = audio_for_text(str(body.get('text') or ''))
        return Response(content=audio, media_type='audio/mpeg', headers={'Cache-Control': 'private, max-age=86400'})
    if action == 'start':
        require_admin(auth)
        raw_theme = str(body.get('theme') or '').strip()
        urls = extract_urls(raw_theme)
        has_instruction = bool(raw_theme)
        profile = fetch_x_profile(ALLOWED_USER)
        profile['listener_username'] = ALLOWED_USER
        profile['logged_in_user'] = str(auth.get('session_user') or '')
        theme = normalize_url_list(raw_theme) if urls else (normalize_theme_request(raw_theme) if raw_theme else default_theme_from_profile(profile))
        guidance = theme_guidance(theme)
        hours = max(1, min(6, int(body.get('duration_hours') or 1)))
        ts = int(time.time())
        reset_program_memory()
        new_state = update_state({'status': 'on_air', 'theme': theme, 'duration_hours': hours, 'started_at': now_iso(), 'ends_at': time.strftime('%Y-%m-%dT%H:%M:%S%z', time.localtime(ts + hours * 3600)), 'loop_state': 'speaking', 'research_status': 'queued', 'broadcaster': auth.get('session_user') or ALLOWED_USER, 'requested_theme': raw_theme, 'theme_guidance': guidance})
        opening_title = (spoken_theme_title(theme, raw_theme) + 'を始めます') if has_instruction else 'オープニング'
        opening_text = 'こんばんは。Kurage AI VTuber Radioです。' + (spoken_theme_title(theme, raw_theme) if has_instruction else spoken_theme_title(theme)) + 'について話します。'
        opening = {'id': f'opening-{ts}', 'theme': theme, 'requested_theme': raw_theme, 'title': opening_title, 'text': opening_text, 'source': 'opening', 'created_at': now_iso()}
        items = [opening] + (seed_url_program(urls) if urls else (seed_instruction_program(theme, raw_theme) if has_instruction else seed_profile_program(theme)))
        write_json(QUEUE, {'items': items, 'updated_at': now_iso()})
        pid = start_worker(theme, profile, 'start', {'instruction': '\n'.join(urls) if urls else raw_theme, 'theme_guidance': guidance, 'ignore_profile_script': has_instruction, 'duration_hours': hours})
        return {'ok': True, 'state': new_state, 'worker_pid': pid, 'tts_prefetch_pid': '', 'prefetch_items': items[:TTS_PREFETCH_LIMIT]}
    if action == 'stop':
        require_admin(auth)
        write_current(None)
        write_json(QUEUE, {'items': [], 'updated_at': now_iso()})
        return {'ok': True, 'state': update_state({'status': 'idle', 'loop_state': 'stopped', 'now_talking': '', 'research_status': 'idle'})}
    if action == 'interrupt':
        require_admin(auth)
        raw_theme = str(body.get('theme') or '').strip()
        urls = extract_urls(raw_theme)
        if not urls:
            raise HTTPException(400, 'url_required')
        theme = '\n'.join(urls)
        guidance = theme_guidance(theme)
        q = queue()
        item = {'id': f'interrupt-{int(time.time())}', 'theme': theme, 'requested_theme': theme, 'title': spoken_theme_title(theme, theme) + 'へ切り替え', 'text': spoken_theme_title(theme, theme) + 'を読み込み、要点と考察をラジオとして伝えます。', 'source': 'url-interrupt', 'created_at': now_iso()}
        q['items'].insert(0, item)
        q['updated_at'] = now_iso()
        write_json(QUEUE, q)
        new_state = update_state({'theme': theme, 'requested_theme': raw_theme, 'theme_guidance': guidance, 'research_status': 'queued', 'loop_state': 'theme_interrupt'})
        profile = fetch_x_profile(ALLOWED_USER)
        pid = start_worker(theme, profile, 'interrupt', {'instruction': theme, 'theme_guidance': guidance, 'ignore_profile_script': True, 'duration_hours': int(state().get('duration_hours') or 1)})
        return {'ok': True, 'state': new_state, 'worker_pid': pid, 'tts_prefetch_pid': '', 'queue': q}
    if action in {'next', 'broadcast_next'}:
        if action == 'broadcast_next':
            if not (auth.get('broadcast') or auth.get('is_admin')):
                raise HTTPException(403, 'broadcast_required')
        else:
            require_admin(auth)
        s = state()
        if s.get('status') != 'on_air':
            raise HTTPException(status_code=409, detail={'error': 'radio_not_on_air', 'state': s, 'current': current()})
        q = queue()
        items = q.get('items') or []
        item = items.pop(0) if items else None
        bridge_count = int(s.get('bridge_count') or 0)
        if not item:
            bridge_count += 1
            spoken = spoken_theme_title(str(s.get('theme') or 'AI思考'))
            texts = [
                f'{spoken}について、次の台本を待つあいだに全体像を短く整理します。資料にあることと、まだ分からないことを分けて聞くと理解しやすくなります。',
                f'{spoken}を別の角度から見ます。大事なのは、名前の印象ではなく、何を説明しようとしているのかを押さえることです。',
                f'{spoken}の話を聞くときは、背景、仕組み、使いどころ、注意点に分けると、内容がほどけていきます。',
            ]
            item = {'id': f'bridge-{int(time.time())}', 'theme': s.get('theme'), 'title': f'補助線 {bridge_count}', 'text': texts[(bridge_count - 1) % len(texts)], 'source': 'bridge', 'created_at': now_iso()}
            if s.get('research_status') not in {'collecting', 'scripting'}:
                start_worker(str(s.get('theme') or 'AI思考'), fetch_x_profile(ALLOWED_USER), 'queue_empty')
        q['items'] = items
        q['updated_at'] = now_iso()
        write_json(QUEUE, q)
        cur = write_current(item)
        patch = {'now_talking': item.get('title') or '', 'loop_state': 'speaking'}
        if bridge_count:
            patch['bridge_count'] = bridge_count
        update_state(patch)
        upcoming = items[:TTS_PREFETCH_LIMIT]
        return {'ok': True, 'item': item, 'current': cur, 'queue_remaining': len(items), 'prefetch_items': upcoming, 'state': state()}
    if action in {'youtube_start', 'youtube_stop'}:
        require_admin(auth)
        if not KVTUBER_ADMIN_TOKEN:
            raise HTTPException(500, 'kvtuber_admin_token_not_configured')
        headers = {'X-Admin-Token': KVTUBER_ADMIN_TOKEN}
        if action == 'youtube_stop':
            r = requests.post(f'{KVTUBER_CONTROL_BASE}/control/youtube-live/stop', headers=headers, timeout=30)
            result = safe_json_response(r)
            if r.status_code >= 400 or (isinstance(result, dict) and result.get('ok') is False):
                raise HTTPException(502, {'error': 'kvtuber_youtube_stop_failed', 'result': result})
            return {'ok': True, 'mode': 'kvtuber-control-api', 'result': result}
        stream_key = str(body.get('stream_key') or '').strip()
        if not stream_key:
            stream_key = default_stream_key()
        if not stream_key:
            raise HTTPException(400, 'stream_key_required')
        viewer_url = broadcast_viewer_url(str(body.get('viewer_url') or PUBLIC_BASE_URL).strip())
        config = {'viewerUrl': viewer_url}
        config['streamKey'] = stream_key
        r1 = requests.post(f'{KVTUBER_CONTROL_BASE}/control/youtube-live', json=config, headers=headers, timeout=30)
        config_result = safe_json_response(r1)
        if r1.status_code >= 400 or (isinstance(config_result, dict) and config_result.get('ok') is False):
            raise HTTPException(502, {'error': 'kvtuber_youtube_config_failed', 'result': config_result})
        r2 = requests.post(f'{KVTUBER_CONTROL_BASE}/control/youtube-live/start', headers=headers, timeout=30)
        start_result = safe_json_response(r2)
        if r2.status_code >= 400 or (isinstance(start_result, dict) and start_result.get('ok') is False):
            raise HTTPException(502, {'error': 'kvtuber_youtube_start_failed', 'result': start_result})
        return {'ok': True, 'mode': 'kvtuber-control-api', 'viewer_url': viewer_url, 'config': config_result, 'result': start_result}
    raise HTTPException(404, 'unknown_action')


def safe_json_response(res: requests.Response) -> Any:
    try:
        return res.json()
    except Exception:
        return {'status_code': res.status_code, 'text': res.text[-1000:]}

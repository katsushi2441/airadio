#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import unquote

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
PREVIEW_CACHE = STORAGE / 'previews'
ALLOWED_USER = os.environ.get('AIRADIO_ALLOWED_USER', 'xb_bittensor')
TTS_ENDPOINT = os.environ.get('AIRADIO_TTS_ENDPOINT', 'http://exbridge.ddns.net:18308/kurage-tts/v1/audio/speech')
PUBLIC_BASE_URL = os.environ.get('AIRADIO_PUBLIC_BASE_URL', 'https://airadio.exbridge.jp/airadio.php')
TTS_VOICE = os.environ.get('AIRADIO_TTS_VOICE', 'ja-JP-NanamiNeural')
TTS_RATE = os.environ.get('AIRADIO_TTS_RATE', '+10%')
TTS_PITCH = os.environ.get('AIRADIO_TTS_PITCH', '-15Hz')
TTS_SPEED = float(os.environ.get('AIRADIO_TTS_SPEED', '1.1'))
TTS_PREFETCH_LIMIT = int(os.environ.get('AIRADIO_TTS_PREFETCH_LIMIT', '4'))
SCRIPT_QUEUE_REFILL_THRESHOLD = int(os.environ.get('AIRADIO_SCRIPT_QUEUE_REFILL_THRESHOLD', '2'))
SCRIPT_REFILL_MIN_INTERVAL = int(os.environ.get('AIRADIO_SCRIPT_REFILL_MIN_INTERVAL', '90'))
KVTUBER_CONTROL_BASE = os.environ.get('AIRADIO_KVTUBER_CONTROL_BASE', 'http://127.0.0.1:18308').rstrip('/')
KVTUBER_ADMIN_TOKEN = os.environ.get('AIRADIO_KVTUBER_ADMIN_TOKEN', os.environ.get('KURAGE_ADMIN_TOKEN', ''))
KVTUBER_ROOT = Path(os.environ.get('AIRADIO_KVTUBER_ROOT', '/home/kojima/work/kvtuber'))
KVTUBER_YOUTUBE_SCRIPT = Path(os.environ.get('AIRADIO_KVTUBER_YOUTUBE_SCRIPT', str(KVTUBER_ROOT / 'scripts/youtube-live-rtmp.mjs')))
KVTUBER_YOUTUBE_CONFIG = Path(os.environ.get('AIRADIO_KVTUBER_YOUTUBE_CONFIG', '/home/kojima/work/kvtuber/storage/youtube-live.json'))
KVTUBER_LEGACY_YOUTUBE_CONFIG = Path(os.environ.get('AIRADIO_KVTUBER_LEGACY_YOUTUBE_CONFIG', '/home/kojima/work/kvtuber/aituber-onair/storage/youtube-live.json'))
DURATION_GUARD = SRC / 'airadio_duration_guard.py'

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


def parse_state_time(value: Any) -> float:
    text = str(value or '').strip()
    if not text:
        return 0.0
    for fmt in ('%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(text, fmt).timestamp()
        except Exception:
            pass
    return 0.0


def program_expired(s: dict[str, Any] | None = None) -> bool:
    s = s or state()
    end_ts = parse_state_time(s.get('ends_at'))
    return bool(end_ts and time.time() >= end_ts)


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


def preroll_program(theme: str, raw_theme: str, urls: list[str]) -> list[dict[str, Any]]:
    ts = int(time.time())
    topic = spoken_theme_title(theme, raw_theme)
    source_note = (
        f'今回指定された資料は{len(urls)}本です。' if len(urls) >= 2
        else ('今回指定された資料を読み込みながら進めます。' if urls else '今回は編集者のプロフィールから番組の方向を組み立てます。')
    )
    rows = [
        (
            'Kurage Radioへようこそ',
            f'こんばんは。Kurage AI VTuber Radioです。{source_note}最初の本編台本を裏側で作っているあいだ、まずはこの番組のことを短く紹介します。ここでは急がず、聞き流せるテンポで、AI時代の学び方や情報の見方をゆっくり整えていきます。',
        ),
        (
            '番組のコンセプト',
            'Kurage AI VTuber Radioのコンセプトは、聴きながらよく寝れる、AI思考のラジオです。画面をじっと見なくても、耳だけで学べること。難しい話題でも、眠りに入りやすい落ち着いた声と順番で、少しずつ理解できることを大切にしています。',
        ),
        (
            'AI VTuberとしてのKurage',
            'Kurageは、ただ台本を読むだけのアバターではありません。指定されたURL、プロフィール、ニュース、技術資料をもとに、裏側で情報を集め、要点を整理し、ラジオ番組として話すAI VTuberです。表では話し続け、裏では次の話題を準備する。この二重の流れがAIRadioの特徴です。',
        ),
        (
            'スポンサー紹介',
            'この番組は、株式会社エクスブリッジの技術開発から生まれました。エクスブリッジは、AI、OSS、動画生成、VTuber、SNS運用、業務自動化をつなげ、企業が情報発信と学習を継続できる仕組みを作っています。人が毎回がんばるのではなく、AIとシステムが支える発信基盤を形にしています。',
        ),
        (
            'Kurageシリーズ',
            'Kurageシリーズには、ブログやニュースを動画化するKurage、翻訳字幕や音声を扱うKurage Voice Pro、参照動画や記事を要約動画にするKurage Montage、ライブ配信を行うKurage AI VTuberなどがあります。AIRadioは、それらをラジオ体験としてつなぎ直したプロダクトです。',
        ),
        (
            'Kurage AgentReach',
            '情報収集では、Kurage AgentReachの考え方を使います。ひとつの資料だけをそのまま読むのではなく、必要に応じて関連するニュース、ブログ、SNS、技術情報を見に行きます。大切なのは、情報をたくさん並べることではなく、リスナーが理解しやすい順番に整理することです。',
        ),
        (
            '動画とライブ配信',
            'Kurageシリーズは、文章を動画にするだけでなく、ライブ配信や録画にもつながっています。話している内容は、そのままYouTube Liveのような配信にも使えます。つまり、学習ラジオを流しながら、あとで再利用できる長尺コンテンツも同時に作れるということです。',
        ),
        (
            '裏側で起きていること',
            f'いま裏側では、{topic}について、資料の取得、要点整理、台本生成を進めています。URLそのものを読み上げるのではなく、そこに書かれている内容、背景、使いどころ、注意点を読み解き、聞きやすい順番に並べ替えてから本編に入ります。',
        ),
        (
            '学びながら休む',
            'AIRadioが目指しているのは、情報を詰め込むことではありません。眠る前でも、作業中でも、散歩中でも、なんとなく聞いているうちに考え方が残る。そんな学び方です。重要なところはゆっくり繰り返し、細かすぎるところは無理に追わせません。',
        ),
        (
            '聞き方のコツ',
            'このラジオは、全部を覚えようとしなくて大丈夫です。気になった言葉だけ拾い、あとで必要なところを調べ直せば十分です。AI時代の学び方は、一度で完璧に理解することではなく、何度も触れながら自分の言葉にしていくことです。',
        ),
        (
            'エクスブリッジの役割',
            '株式会社エクスブリッジは、こうしたAI活用を実験で終わらせず、実際に動く業務システムや発信システムとして組み立てています。AIエージェント、動画生成、SNS投稿、ライブ配信、データ収集をつなぐことで、企業が継続的に学び、発信し、改善できる環境を作ります。',
        ),
        (
            '本編への入り口',
            'まもなく本編の台本が準備できたところから、Kurageがテーマに沿って話し始めます。もし最初の準備にもう少し時間がかかっても、この番組は止まらず、準備ができた順に自然につないでいきます。では、今夜のテーマを静かに始めていきましょう。',
        ),
    ]
    items: list[dict[str, Any]] = []
    for i, (title, text) in enumerate(rows):
        items.append({
            'id': f'preroll-{ts}-{i}',
            'theme': theme,
            'requested_theme': raw_theme,
            'title': title,
            'text': text,
            'source': 'preroll',
            'created_at': now_iso(),
        })
    return items


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


def maybe_start_refill_worker(s: dict[str, Any], reason: str, queue_len: int) -> int:
    """Start background script generation before the radio runs dry."""
    if s.get('research_status') in {'queued', 'collecting', 'scripting'}:
        return 0
    if queue_len > SCRIPT_QUEUE_REFILL_THRESHOLD:
        return 0
    last_refill = float(s.get('last_refill_started_at') or 0)
    if last_refill and time.time() - last_refill < SCRIPT_REFILL_MIN_INTERVAL:
        return 0
    theme = str(s.get('theme') or 'AI思考')
    requested = str(s.get('requested_theme') or '')
    profile = fetch_x_profile(ALLOWED_USER)
    pid = start_worker(theme, profile, reason, {
        'instruction': requested if requested else theme,
        'theme_guidance': str(s.get('theme_guidance') or theme_guidance(theme)),
        'ignore_profile_script': bool(requested),
        'duration_hours': int(s.get('duration_hours') or 1),
    })
    update_state({
        'research_status': 'queued',
        'last_refill_started_at': time.time(),
        'last_refill_reason': reason,
    })
    return pid


def start_duration_guard(s: dict[str, Any], reason: str = 'duration_elapsed') -> int:
    started_at = str(s.get('started_at') or '').strip()
    ends_at = str(s.get('ends_at') or '').strip()
    if not started_at or not ends_at:
        return 0
    log = LOG.open('ab')
    proc = subprocess.Popen(
        [
            sys.executable,
            str(DURATION_GUARD),
            '--started-at',
            started_at,
            '--ends-at',
            ends_at,
            '--reason',
            reason,
        ],
        cwd=str(ROOT),
        stdout=log,
        stderr=log,
        start_new_session=True,
        env=os.environ.copy(),
    )
    append_log('duration_guard_started', {'pid': proc.pid, 'started_at': started_at, 'ends_at': ends_at, 'reason': reason})
    return proc.pid


def prepare_program_start(body: dict[str, Any], auth: dict[str, Any], reason: str = 'start') -> dict[str, Any]:
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
    new_state = update_state({
        'status': 'on_air',
        'theme': theme,
        'duration_hours': hours,
        'started_at': now_iso(),
        'ends_at': time.strftime('%Y-%m-%dT%H:%M:%S%z', time.localtime(ts + hours * 3600)),
        'loop_state': 'preroll',
        'research_status': 'queued',
        'now_talking': 'Kurage Radioへようこそ',
        'broadcaster': auth.get('session_user') or ALLOWED_USER,
        'requested_theme': raw_theme,
        'theme_guidance': guidance,
        'program_source': 'url' if urls else ('instruction' if has_instruction else 'profile'),
    })
    # Use a prepared pre-roll instead of thin ad-lib bridge talk while the first
    # real script is generated in the background.
    items = preroll_program(theme, raw_theme, urls)
    write_json(QUEUE, {'items': items, 'updated_at': now_iso()})
    instruction = '\n'.join(urls) if urls else raw_theme
    pid = start_worker(theme, profile, reason, {
        'instruction': instruction,
        'theme_guidance': guidance,
        'ignore_profile_script': has_instruction,
        'duration_hours': hours,
    })
    return {'state': new_state, 'worker_pid': pid, 'prefetch_items': items[:TTS_PREFETCH_LIMIT]}


def stop_youtube_live(reason: str = 'stop') -> dict[str, Any]:
    api_result: dict[str, Any] | None = None
    if KVTUBER_ADMIN_TOKEN:
        headers = {'X-Admin-Token': KVTUBER_ADMIN_TOKEN}
        try:
            r = requests.post(f'{KVTUBER_CONTROL_BASE}/control/youtube-live/stop', headers=headers, timeout=30)
            result = safe_json_response(r)
            ok = r.status_code < 400 and not (isinstance(result, dict) and result.get('ok') is False)
            append_log('youtube_stop_requested', {'reason': reason, 'ok': ok})
            if ok:
                return {'ok': True, 'method': 'control-api', 'status_code': r.status_code, 'result': result}
            api_result = {'ok': False, 'status_code': r.status_code, 'result': result}
        except Exception as exc:
            api_result = {'ok': False, 'error': str(exc)}
            append_log('youtube_stop_failed', {'reason': reason, 'error': str(exc)})
    if KVTUBER_YOUTUBE_SCRIPT.exists():
        try:
            proc = subprocess.run(
                ['node', str(KVTUBER_YOUTUBE_SCRIPT), 'stop'],
                cwd=str(KVTUBER_ROOT),
                capture_output=True,
                text=True,
                timeout=45,
                check=False,
            )
            ok = proc.returncode == 0
            append_log('youtube_stop_local_fallback', {'reason': reason, 'ok': ok, 'returncode': proc.returncode})
            return {
                'ok': ok,
                'method': 'local-kvtuber-script',
                'api_result': api_result,
                'stdout': proc.stdout[-1200:],
                'stderr': proc.stderr[-1200:],
            }
        except Exception as exc:
            append_log('youtube_stop_local_fallback_failed', {'reason': reason, 'error': str(exc)})
            return {'ok': False, 'method': 'local-kvtuber-script', 'api_result': api_result, 'error': str(exc)}
    return {'ok': False, 'method': 'none', 'api_result': api_result, 'reason': 'no_stop_method_available'}


def stop_program(reason: str = 'stop', stop_youtube: bool = True) -> dict[str, Any]:
    write_current(None)
    write_json(QUEUE, {'items': [], 'updated_at': now_iso()})
    new_state = update_state({'status': 'idle', 'loop_state': 'stopped', 'now_talking': '', 'research_status': 'idle', 'stopped_reason': reason})
    youtube_result = stop_youtube_live(reason) if stop_youtube else {'ok': True, 'skipped': True}
    return {'state': new_state, 'youtube_stop': youtube_result}


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


def preview_for_url(url: str) -> bytes:
    url = unquote((url or '').strip())
    if not re.match(r'^https?://', url):
        raise HTTPException(400, 'preview_url_required')
    PREVIEW_CACHE.mkdir(parents=True, exist_ok=True)
    h = sha256(url.encode('utf-8')).hexdigest()
    path = PREVIEW_CACHE / f'{h}.png'
    if path.exists() and path.stat().st_size > 1000 and time.time() - path.stat().st_mtime < 3600:
        return path.read_bytes()
    chrome = os.environ.get('AIRADIO_CHROME_BIN') or '/usr/bin/google-chrome'
    if not Path(chrome).exists():
        raise HTTPException(500, 'chrome_not_found')
    tmp = path.with_suffix('.tmp.png')
    cmd = [
        chrome,
        '--headless=new',
        '--no-sandbox',
        '--disable-gpu',
        '--disable-dev-shm-usage',
        '--hide-scrollbars',
        '--window-size=960,540',
        f'--screenshot={tmp}',
        url,
    ]
    try:
        subprocess.run(cmd, cwd=str(ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=False)
    except subprocess.TimeoutExpired:
        raise HTTPException(504, 'preview_timeout')
    if not tmp.exists() or tmp.stat().st_size <= 1000:
        raise HTTPException(502, 'preview_failed')
    tmp.replace(path)
    return path.read_bytes()


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
    if action == 'preview':
        image = preview_for_url(str(request.query_params.get('url') or ''))
        return Response(content=image, media_type='image/png', headers={'Cache-Control': 'private, max-age=3600'})
    if action == 'start':
        require_admin(auth)
        started = prepare_program_start(body, auth, 'start')
        return {'ok': True, 'state': started['state'], 'worker_pid': started['worker_pid'], 'tts_prefetch_pid': '', 'prefetch_items': started['prefetch_items']}
    if action == 'stop':
        require_admin(auth)
        stopped = stop_program('manual_stop', stop_youtube=True)
        return {'ok': True, 'state': stopped['state'], 'youtube_stop': stopped['youtube_stop']}
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
        if program_expired(s):
            stopped = stop_program('duration_elapsed', stop_youtube=True)
            return {'ok': False, 'ended': True, 'reason': 'duration_elapsed', 'state': stopped['state'], 'youtube_stop': stopped['youtube_stop']}
        q = queue()
        items = q.get('items') or []
        item = items.pop(0) if items else None
        if not item:
            pid = maybe_start_refill_worker(s, 'queue_empty', 0)
            waiting_title = '台本作成中'
            waiting_text = '最初の台本を作成しています。音声は流さず、準備ができ次第そのまま話し始めます。'
            if current().get('item'):
                waiting_title = '次の台本を準備中'
                waiting_text = '次の台本をバックグラウンドで生成しています。準備でき次第、続きから再開します。'
            update_state({
                'now_talking': waiting_title,
                'loop_state': 'script_preparing',
                'research_status': 'queued' if pid else s.get('research_status', 'queued'),
            })
            return {
                'ok': True,
                'waiting': True,
                'item': None,
                'message': waiting_text,
                'title': waiting_title,
                'current': current(),
                'queue_remaining': 0,
                'prefetch_items': [],
                'state': state(),
                'worker_pid': pid,
            }
        q['items'] = items
        q['updated_at'] = now_iso()
        write_json(QUEUE, q)
        cur = write_current(item)
        refill_pid = maybe_start_refill_worker(s, 'queue_low', len(items))
        patch = {'now_talking': item.get('title') or '', 'loop_state': 'speaking'}
        if refill_pid:
            patch['research_status'] = 'queued'
        update_state(patch)
        upcoming = items[:TTS_PREFETCH_LIMIT]
        return {'ok': True, 'item': item, 'current': cur, 'queue_remaining': len(items), 'prefetch_items': upcoming, 'state': state()}
    if action in {'youtube_start', 'youtube_stop'}:
        require_admin(auth)
        if not KVTUBER_ADMIN_TOKEN:
            raise HTTPException(500, 'kvtuber_admin_token_not_configured')
        headers = {'X-Admin-Token': KVTUBER_ADMIN_TOKEN}
        if action == 'youtube_stop':
            stopped = stop_program('youtube_stop', stop_youtube=True)
            result = stopped['youtube_stop']
            if isinstance(result, dict) and result.get('ok') is False and not result.get('skipped'):
                raise HTTPException(502, {'error': 'kvtuber_youtube_stop_failed', 'result': result})
            return {'ok': True, 'mode': 'kvtuber-control-api', 'result': result, 'state': stopped['state']}
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
        started = prepare_program_start(body, auth, 'youtube_start')
        guard_pid = start_duration_guard(started['state'], 'duration_elapsed')
        return {'ok': True, 'mode': 'kvtuber-control-api', 'viewer_url': viewer_url, 'program': started, 'duration_guard_pid': guard_pid, 'config': config_result, 'result': start_result}
    raise HTTPException(404, 'unknown_action')


def safe_json_response(res: requests.Response) -> Any:
    try:
        return res.json()
    except Exception:
        return {'status_code': res.status_code, 'text': res.text[-1000:]}

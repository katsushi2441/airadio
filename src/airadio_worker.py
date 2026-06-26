#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
STORAGE = ROOT / 'storage'
QUEUE = STORAGE / 'script_queue.json'
STATE = STORAGE / 'radio_state.json'
LOCK = STORAGE / 'worker.lock'
MEMORY = STORAGE / 'talk_memory.json'
TTS_PREFETCH_SCRIPT = ROOT / 'src' / 'tts_prefetch.php'
KAGENTREACH = Path(os.environ.get('AIRADIO_KAGENTREACH_DIR', '/home/kojima/work/kagentreach'))
OLLAMA_URL = os.environ.get('AIRADIO_OLLAMA_URL', 'http://192.168.0.3:11434/api/generate')
OLLAMA_MODEL = os.environ.get('AIRADIO_OLLAMA_MODEL', 'gemma4:12b-it-qat')
CLAUDE_MODEL = os.environ.get('AIRADIO_CLAUDE_MODEL', 'haiku')
CLAUDE_TIMEOUT_SECONDS = int(os.environ.get('AIRADIO_CLAUDE_TIMEOUT', '90'))
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


def start_tts_prefetch(items: list[dict[str, Any]], reason: str) -> None:
    if not items or not TTS_PREFETCH_SCRIPT.exists():
        return
    payload_path = STORAGE / f'tts_prefetch_worker_{int(time.time())}_{os.getpid()}.json'
    limited = []
    for item in items[:4]:
        text = str(item.get('text') or '').strip()
        if not text:
            continue
        limited.append({
            'id': str(item.get('id') or ''),
            'title': str(item.get('title') or ''),
            'text': text,
        })
    if not limited:
        return
    write_json(payload_path, {
        'reason': reason,
        'items': limited,
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
    })
    php = os.environ.get('AIRADIO_PHP_BINARY', 'php')
    log_path = str(STORAGE / 'radio_loop.log')
    with open(log_path, 'ab', buffering=0) as log:
        subprocess.Popen(
            [php, str(TTS_PREFETCH_SCRIPT), '--payload', str(payload_path)],
            cwd=str(ROOT),
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    log_event('tts_prefetch_started', reason=reason, count=len(limited))


def normalize_text(text: str) -> str:
    text = re.sub(r'\s+', '', text or '')
    text = re.sub(r'[。、,.，．！？!?「」『』（）()【】\[\]…ー-]', '', text)
    return text.lower()


def text_fingerprint(text: str) -> str:
    normalized = normalize_text(text)
    return normalized[:140]


def load_memory() -> dict[str, Any]:
    memory = read_json(MEMORY, {'fingerprints': [], 'topics': [], 'recent_texts': []})
    if not isinstance(memory.get('fingerprints'), list):
        memory['fingerprints'] = []
    if not isinstance(memory.get('topics'), list):
        memory['topics'] = []
    if not isinstance(memory.get('recent_texts'), list):
        memory['recent_texts'] = []
    return memory


def remember_segments(items: list[dict[str, Any]]) -> None:
    memory = load_memory()
    for item in items:
        text = str(item.get('text') or '')
        fp = text_fingerprint(text)
        if fp:
            memory['fingerprints'].append(fp)
        if item.get('title'):
            memory['topics'].append(str(item.get('title')))
        memory['recent_texts'].append(text[:500])
    memory['fingerprints'] = memory['fingerprints'][-240:]
    memory['topics'] = memory['topics'][-120:]
    memory['recent_texts'] = memory['recent_texts'][-40:]
    memory['updated_at'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    write_json(MEMORY, memory)


def is_duplicate_text(text: str, memory: dict[str, Any]) -> bool:
    fp = text_fingerprint(text)
    if not fp:
        return True
    for old in memory.get('fingerprints', [])[-120:]:
        if fp == old or (len(fp) > 80 and (fp in old or old in fp)):
            return True
    return False


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



def extract_urls(text: str) -> list[str]:
    urls = re.findall(r'https?://[^\s「」『』"\'`<>]+', text or '')
    cleaned = []
    for url in urls:
        url = url.rstrip('。、.!！?)]）')
        if url and url not in cleaned:
            cleaned.append(url)
    return cleaned[:5]


def extract_github_repos(text: str) -> list[str]:
    repos = []
    for url in extract_urls(text):
        match = re.search(r'https?://github\.com/([^/\s]+)/([^/\s?#]+)', url)
        if not match:
            continue
        owner = match.group(1).strip()
        repo = re.sub(r'\.git$', '', match.group(2).strip())
        if owner and repo and repo not in {'issues', 'pulls', 'tree', 'blob'}:
            name = f'{owner}/{repo}'
            if name not in repos:
                repos.append(name)
    return repos[:3]


def http_get_text(url: str, timeout: int = 20, accept: str = 'text/plain') -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'KurageAIRadio/0.1',
            'Accept': accept,
        },
        method='GET',
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            body = res.read(600_000).decode('utf-8', errors='replace')
            return int(getattr(res, 'status', 200)), body
    except urllib.error.HTTPError as exc:
        body = exc.read(80_000).decode('utf-8', errors='replace') if exc.fp else ''
        return int(exc.code), body


def strip_markdown_noise(text: str) -> str:
    text = re.sub(r'<!--.*?-->', ' ', text or '', flags=re.S)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1 (\2)', text)
    text = re.sub(r'[`*_#>|~]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def summarize_readme_locally(readme: str, limit: int = 3600) -> str:
    clean = strip_markdown_noise(readme)
    lines = []
    keep_next = False
    for raw in clean.splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        important = (
            keep_next
            or any(key in low for key in ['why', 'who this is for', 'learning paths', 'study suggestions', 'run locally', 'stage', 'beginner', 'advanced', 'vibe', 'ai era'])
            or re.match(r'^(want|need|easy-vibe|complete beginners|product managers|students|junior|mid-level|best for|what you will learn|what you will get)', line, re.I)
        )
        if important:
            lines.append(line)
            keep_next = len(line) < 80 and len(lines) < 80
        elif len(lines) < 14 and len(line) > 30:
            lines.append(line)
        if sum(len(x) for x in lines) > limit:
            break
    return '\n'.join(lines)[:limit]


def fetch_github_repo(repo: str) -> dict[str, Any]:
    api_url = f'https://api.github.com/repos/{repo}'
    meta_status, meta_raw = http_get_text(api_url, timeout=18, accept='application/vnd.github+json')
    meta: dict[str, Any] = {}
    if meta_status < 400:
        try:
            parsed = json.loads(meta_raw)
            if isinstance(parsed, dict):
                meta = parsed
        except Exception:
            meta = {}
    branch = str(meta.get('default_branch') or 'main')
    readme = ''
    readme_status = 0
    candidates = [
        f'https://raw.githubusercontent.com/{repo}/{branch}/README.md',
        f'https://raw.githubusercontent.com/{repo}/{branch}/docs-readme/ja-JP/README.md',
        f'https://raw.githubusercontent.com/{repo}/{branch}/docs-readme/zh-CN/README.md',
    ]
    for url in candidates:
        readme_status, body = http_get_text(url, timeout=20)
        if readme_status < 400 and len(body.strip()) > 200:
            readme = body
            break
    return {
        'type': 'github_repo',
        'ok': bool(meta or readme),
        'repo': repo,
        'url': f'https://github.com/{repo}',
        'description': str(meta.get('description') or ''),
        'stars': int(meta.get('stargazers_count') or 0),
        'language': str(meta.get('language') or ''),
        'default_branch': branch,
        'license': ((meta.get('license') or {}).get('spdx_id') if isinstance(meta.get('license'), dict) else '') or '',
        'readme_summary': summarize_readme_locally(readme),
        'readme_excerpt': strip_markdown_noise(readme)[:5000],
        'fetched_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
    }


def run_github_research(text: str) -> list[dict[str, Any]]:
    results = []
    for repo in extract_github_repos(text):
        try:
            results.append(fetch_github_repo(repo))
        except Exception as exc:
            results.append({'type': 'github_repo', 'ok': False, 'repo': repo, 'url': f'https://github.com/{repo}', 'error': str(exc)})
    return results


def research_query_from_theme(theme: str, github_items: list[dict[str, Any]]) -> str:
    if github_items:
        repo = str(github_items[0].get('repo') or '')
        desc = str(github_items[0].get('description') or '')
        summary = str(github_items[0].get('readme_summary') or '')
        words = re.findall(r'[A-Za-z][A-Za-z0-9_-]{2,}|[\u3040-\u30ff\u3400-\u9fff]{2,}', f'{repo} {desc} {summary}')
        picked = []
        for word in words:
            if word.lower() in {'https', 'github', 'com', 'readme', 'assets', 'img', 'width'}:
                continue
            if word not in picked:
                picked.append(word)
            if len(picked) >= 8:
                break
        if picked:
            return ' '.join(picked)
    return theme


def collect_research(theme: str, instruction: str = '') -> dict[str, Any]:
    source_text = f'{instruction}\n{theme}'
    github_items = run_github_research(source_text)
    x_query = research_query_from_theme(theme, github_items)
    x_result = run_x_search(x_query)
    return {
        'ok': bool(github_items) or bool(x_result.get('ok')),
        'theme': theme,
        'instruction': instruction,
        'github': github_items,
        'x_query': x_query,
        'x': x_result,
        'notes': 'GitHub URLs are treated as primary source material; X search is supplemental signal only.',
    }

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


def find_claude_bin() -> Optional[str]:
    configured = os.environ.get('CLAUDE_BIN')
    if configured and Path(configured).exists():
        return configured
    which = shutil.which('claude')
    if which:
        return which
    ext_dir = Path('/home/kojima/.vscode-server/extensions')
    candidates = sorted(ext_dir.glob('anthropic.claude-code-*/resources/native-binary/claude'), reverse=True)
    return str(candidates[0]) if candidates else None


def claude_json(prompt: str, timeout: int = CLAUDE_TIMEOUT_SECONDS) -> dict[str, Any]:
    claude_bin = find_claude_bin()
    if not claude_bin:
        raise RuntimeError('claude binary not found')
    cmd = [
        claude_bin,
        '-p',
        '--input-format',
        'text',
        '--output-format',
        'json',
        '--model',
        CLAUDE_MODEL,
    ]
    proc = subprocess.run(cmd, input=prompt, cwd=str(ROOT), text=True, capture_output=True, timeout=timeout, check=False)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout)[-1200:])
    payload = json.loads(proc.stdout)
    structured = payload.get('structured_output') if isinstance(payload, dict) else None
    if isinstance(structured, dict):
        return structured
    result = payload.get('result') if isinstance(payload, dict) else payload
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        return parse_json_object(result)
    return {}


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


def normalize_theme_request(text: str) -> str:
    text = re.sub(r'[「」『』"\'`]', '', str(text or '').strip())
    text = re.sub(r'\s+', ' ', text)
    patterns = [
        r'^(.+?)(?:という|っていう|といった)?テーマで(?:話して|話す|解説して|教えて|お願いします|ください)?[。.!！]*$',
        r'^(.+?)(?:を|について)(?:テーマにして|話して|解説して|教えて|お願いします|ください)[。.!！]*$',
        r'^(.+?)(?:を|について)(?:初心者向けに|入門向けに)?(?:話して|解説して|教えて|お願いします|ください)[。.!！]*$',
    ]
    for pattern in patterns:
        match = re.match(pattern, text)
        if match and match.group(1).strip():
            text = match.group(1).strip()
            break
    text = re.sub(r'(?:という|っていう|といった)?テーマ$', '', text).strip()
    text = re.sub(r'(?:を|について)$', '', text).strip()
    return text.strip('。、.!！? ') or str(text or '').strip()


def theme_guidance(theme: str) -> str:
    if re.search(r'入門|初心者|初級|はじめて|基礎', theme):
        return 'このテーマは入門編として扱う。専門用語を短く説明し、なぜ必要か、最初に何をすればよいか、つまずきやすい点、今日できる小さな実践の順に話す。上級者向けの抽象論や収益化の話へ急がない。'
    if re.search(r'応用|実践|収益|稼', theme):
        return 'このテーマは実践編として扱う。具体的な手順、ツール選択、検証方法、失敗時の立て直し、収益化への接続を中心に話す。'
    return '入力されたテーマの意図を保ち、一般論に薄めず、具体例と実装・発信・検証の観点を入れて話す。'



def github_fallback_segments(theme: str, github_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not github_items:
        return []
    repo = github_items[0]
    name = str(repo.get('repo') or theme)
    desc = str(repo.get('description') or 'AI時代の学習教材')
    stars = int(repo.get('stars') or 0)
    license_name = str(repo.get('license') or '')
    summary = str(repo.get('readme_summary') or repo.get('readme_excerpt') or '')
    has_stage = 'Stage' in summary or 'stage' in summary.lower() or '学習' in summary
    star_text = f'GitHubで約{stars:,}スターを集めている' if stars else 'GitHubで公開されている'
    license_text = f'ライセンスは{license_name}です。' if license_name else 'ライセンスや再利用条件は、実際に使う前に確認しておきたい点です。'
    if 'easy-vibe' in name.lower():
        texts = [
            f'ここからは{name}を、GitHubリポジトリそのものを教材として見ていきます。説明には「{desc}」とあり、中心にあるのは、話せればアプリを作れるというAI時代の開発観です。これは単なる流行語ではなく、初心者が最初の成果物まで進むための学習設計として見ると価値が分かります。',
            f'{name}が面白いのは、{star_text}点です。READMEでは、完全な初心者、プロダクトマネージャー、学生、ジュニア開発者、そしてAIネイティブな開発者まで、対象者ごとに学習パスを分けています。つまり、バイブコーディングを感覚論ではなく、段階的な教育コースに落としているわけです。',
            '学習パスは、まず小さな成功体験から入り、次にアイデアをプロトタイプへ変え、さらにフルスタック開発へ進む流れです。ここが大事です。AIに丸投げするのではなく、目的を言葉にし、画面を作り、バックエンドや決済のような現実の部品へ接続していく順番があるからです。',
            '編集者がこの教材から学べる実践ポイントは、AIRadioやKurageの開発にもそのまま使えます。まず作りたい体験を言葉にする。次にAIに小さく実装させる。動作を見て、違和感を戻す。そしてログや手順を残す。この往復が、バイブコーディングを仕事の方法に変えます。',
            f'注意点もあります。{license_text}また、多言語教材や派手なデモを見るだけで満足すると、実装力にはつながりません。自分のプロジェクトで一画面、一機能、一投稿のように、小さく試すところまで持っていく必要があります。',
            f'まとめると、{name}はバイブコーディングを「なんとなくAIに頼む」から、「話す、作る、確認する、直す」という学習ループへ変える教材です。今夜の編集者への問いは一つです。この教材の考え方を使って、明日どの小さな機能をAIと一緒に作るか。そこから始めましょう。',
        ]
    else:
        texts = [
            f'ここからは{name}を、GitHubリポジトリを一次資料として見ていきます。説明は「{desc}」です。まず、何を解決するためのリポジトリなのか、誰に向いているのかを静かに整理します。',
            f'{name}は{star_text}公開プロジェクトです。スター数は万能ではありませんが、関心の強さや学習価値を見る入口になります。READMEの構成から、作者が何を最短で伝えたいのかを読み取ることができます。',
            '実務で見るべき点は、インストール手順、サンプル、対象読者、拡張方法、そしてライセンスです。AIに調べさせるだけではなく、自分のプロダクトに取り込める部分と、参考に留める部分を分けることが大切です。',
            f'{license_text}OSSを使うときは、商用利用、改変、再配布、クレジット表記の条件を先に見ます。ここを曖昧にすると、あとでプロダクト化するときに詰まりやすくなります。',
            '編集者が次にやることは、READMEを読むだけではなく、ひとつのユースケースへ翻訳することです。自分なら、この機能をKurageのどこに接続するか。どの作業を楽にするか。そこまで落とすと、情報収集が実装に変わります。',
            f'まとめると、{name}はURLではなく、設計思想、実装部品、学習導線のまとまりとして扱うべき資料です。Kurageはこの一次情報をもとに、静かなラジオとして、実装に使える形へほどいていきます。',
        ]
    now = int(time.time())
    return [{
        'id': f'github-fallback-{now}-{i}',
        'theme': theme,
        'title': f'{name} {i + 1}',
        'text': text,
        'source': 'github-fallback',
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
    } for i, text in enumerate(texts)]

def fallback_segments(theme: str) -> list[dict[str, Any]]:
    memory = load_memory()
    if re.search(r'入門|初心者|初級|はじめて|基礎', theme):
        base = [
            f'ここからは{theme}として、はじめての人にも分かる順番で話します。バイブコーディングは、雰囲気でコードを書くことではありません。作りたいものを言葉にし、AIに実装させ、動かして確かめ、違和感をまた言葉で返す開発の往復です。',
            '最初に大事なのは、完璧なプロンプトではなく、小さく頼むことです。たとえば、ログイン画面を全部作って、ではなく、まず入力欄とボタンだけ作って、次に保存、次にエラー表示、というように分けます。',
            '初心者がつまずきやすいのは、AIの返答をそのまま信じるところです。動いたか、画面で見たか、エラーは出ていないか、Gitに何が変わったか。この確認をセットにすると、バイブコーディングは急に実用的になります。',
            '使う道具は、最初は多くなくて大丈夫です。ブラウザで確認できる小さなWebページ、Gitで差分を見る習慣、そしてAIに直してほしい点を一文で伝えること。この三つが入門編の土台です。',
            '今日できる小さな実践は、ひとつの画面を決めて、ここをもう少し分かりやすくして、とAIに頼むことです。そのあと、どこが変わったかを自分の目で見る。ここからAIと一緒に作る感覚が育ちます。',
            'まとめると、バイブコーディング入門で覚えることは、AIに任せることではなく、AIとの往復を設計することです。目的を言う、作らせる、見る、直す。この四拍子を小さく回すところから始めましょう。',
        ]
    else:
        base = [
            f'ここからは{theme}を、AIエージェントを実際に動かす人の目線で見ていきます。今日はまず、情報収集、判断、実行の三つを分けて考えます。',
            'KurageがDJとして、いま見えている論点をゆっくり整理します。編集者もリスナーも、全部覚えようとしなくて大丈夫です。使えそうな一文だけ拾ってください。',
            f'{theme}で大切なのは、流行語を追うことではなく、明日の作業が一つ軽くなるかどうかです。小さな自動化を積み重ねると、やがて仕事の流れそのものが変わります。',
            '次の観点は、ツール選びです。Claude Code、Codex、ローカルLLM、browser-useのような操作エージェントは、それぞれ得意な待ち時間と失敗の仕方が違います。',
            'AIに仕事を任せるときは、成果物だけではなく、途中のログ、判断理由、やり直し方を残すことが価値になります。これは後から人に渡せる知識になるからです。',
            'ここまでを一度まとめます。テーマを小さく切り、AIに調べさせ、台本にし、実行し、ログを残す。この循環が、編集者向けのAI思考ラジオの基本形です。',
        ]
    items = []
    for i, text in enumerate(base):
        if is_duplicate_text(text, memory):
            continue
        items.append({'id': f'fallback-{int(time.time())}-{i}', 'theme': theme, 'title': f'{theme}の視点 {i + 1}', 'text': text, 'source': 'fallback-curated'})
    if not items:
        now = time.strftime('%H時%M分')
        items.append({
            'id': f'fallback-{int(time.time())}-fresh',
            'theme': theme,
            'title': f'{theme}の新しい切り口',
            'text': f'{now}の時点で、Kurageは{theme}を別の角度から見直します。今回は、情報収集の精度ではなく、集めた情報をどう行動に変えるかに絞って、編集者とリスナーへ話します。',
            'source': 'fallback-curated',
        })
    remember_segments(items)
    return items


def bridge_segments(theme: str) -> list[dict[str, Any]]:
    memory = load_memory()
    base = [
        f'次の資料を待つあいだに、{theme}の判断軸を一つだけ置いておきます。収益化につながるかどうかは、作業時間を減らすか、発信量を増やすかで見るとわかりやすいです。',
        '少し視点を変えます。AIエージェントの価値は、賢い返答だけではありません。調べる、試す、記録する、次に渡す。この地味な連携が積み上がるところにあります。',
        'ここでは結論を急ぎません。Kurageは、編集者があとで実装や発信に使えるように、話題を小さな部品へ分けていきます。',
        '次の台本を作っている間に、ひとつだけ実践の問いを置きます。このテーマで、今日すぐ自動化できる一手は何か。そこから考えると、話が現実に近づきます。',
    ]
    now = int(time.time())
    items = []
    for i, text in enumerate(base):
        if is_duplicate_text(text, memory):
            continue
        items.append({
            'id': f'bridge-{now}-{i}',
            'theme': theme,
            'title': f'{theme}の考え方 {i + 1}',
            'text': text,
            'source': 'bridge',
            'created_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        })
    remember_segments(items)
    return items


def build_segments(theme: str, profile: dict[str, Any], research: dict[str, Any], instruction: str = '', ignore_profile_script: bool = False) -> list[dict[str, Any]]:
    memory = load_memory()
    guidance = theme_guidance(theme)
    profile_text = json.dumps(enrich_profile(profile), ensure_ascii=False)[:1800]
    research_text = json.dumps(research, ensure_ascii=False)[:9000]
    github_items = research.get('github') if isinstance(research, dict) else []
    github_primary = bool(github_items)
    memory_text = json.dumps({
        'recent_topics': memory.get('topics', [])[-24:],
        'recent_texts': memory.get('recent_texts', [])[-10:],
    }, ensure_ascii=False)[:5000]
    prompt = f'''
あなたは「Kurage AI VTuber Radio」のメイン構成作家です。
KurageがDJで、編集者は聞き手であり番組を整える人です。ログインした他ユーザーは同じ番組を聞くリスナーです。
自由入力指示がある場合はその指示を最優先します。指示がない場合だけ、編集者のXプロフィールに合うテーマから入り、AI、Bittensor、分散AI、Web3、バイブコーディング、Claude Code/Codex、AI Agent、収益化の文脈を自然に接続してください。

テーマ: {theme}
編集者の自由入力指示: {instruction or 'なし'}
プロフィール台本を無視するか: {'はい' if ignore_profile_script else 'いいえ'}
GitHubリポジトリを主教材として扱うか: {'はい' if github_primary else 'いいえ'}
テーマ解釈: {guidance}
聞き手プロフィール: {profile_text}
情報収集メモ: {research_text}
直近で話した内容（絶対に繰り返さない）: {memory_text}

要件:
- 日本語。
- Kurageが編集者とリスナーへ話しかける口調。
- 内部アカウント名やユーザーIDは読み上げない。xb_bittensorのような名前は必ず「編集者」と呼ぶ。
- 英語の長い言い回しを混ぜず、自然な日本語で説明する。固有名詞以外は日本語にする。
- 編集者の学びを、他のリスナーにも役立つ解説へ変換する。
- 自由入力指示がある場合は、その文章の意図を最優先する。プロフィール起点の定番台本、Bittensor、Web3、収益化の話に勝手に戻らない。
- 自由入力指示はフォーマットなしの自然文として扱い、「何について」「どのレベルで」「どう話してほしいか」を推測して台本化する。
- GitHubリポジトリURLが入力された場合は、情報収集メモ内のgithub項目を一次資料として扱う。READMEの内容、対象読者、学習パス、特徴、ライセンスや注意点を具体的に話す。URL名だけを読み上げたり、一般的なバイブコーディング論へ薄めたりしない。
- GitHub主教材の場合、各segmentの角度は repository_overview, why_it_matters, learning_path, practical_use, caveats, editor_action のように、資料の中身に沿って分ける。
- 1本あたり60〜120秒程度で読める長さ。
- 同じ言い回し、同じ結論、同じブリッジトークは禁止。
- 抽象論だけで終わらせない。具体的なツール、実装、収益化、発信、検証、失敗回避を入れる。
- 眠りを促すラジオなので穏やか。ただし中身は濃く、薄い一般論にしない。
- テーマ解釈を最優先する。たとえば「入門編」なら、初めて聞く人が理解できる順番、用語説明、最初の実践、つまずき回避を中心にする。
- 各segmentは別の角度にする: profile_hook, current_signal, tool_workflow, monetization, implementation_note, closing_question。
- 「裏側で情報収集しています」「呼吸を整えましょう」のような待ち文句を繰り返さない。
- JSONだけで返す。shape: {{"segments":[{{"title":"...","text":"...","source":"..."}}]}}
- segmentsは6個。
'''.strip()
    model_errors = []
    providers = []
    if os.environ.get('AIRADIO_DISABLE_CLAUDE') != '1':
        providers.append(('claude', lambda p: claude_json(p)))
    providers.append(('ollama', lambda p: parse_json_object(ollama(p))))
    for provider, runner in providers:
        try:
            parsed = runner(prompt)
            out = normalize_segments(parsed, theme, provider, memory)
            if len(out) >= 4:
                if github_primary and len(out) < 6:
                    out.extend(github_fallback_segments(theme, github_items)[: 6 - len(out)])
                remember_segments(out[:6])
                return out[:6]
            if out:
                filler = github_fallback_segments(theme, github_items) if github_primary else bridge_segments(theme)
                out.extend(filler[: 6 - len(out)])
                remember_segments(out[:6])
                return out[:6]
            model_errors.append(f'{provider}: no valid segments')
        except Exception as exc:
            model_errors.append(f'{provider}: {str(exc)[-500:]}')
            update_state(research_status='fallback', last_error=' | '.join(model_errors)[-1000:])
    return fallback_segments(theme)


def enrich_profile(profile: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(profile or {})
    username = str(enriched.get('username') or enriched.get('username_from_session') or '')
    if not username:
        username = 'xb_bittensor'
    enriched.setdefault('username', username)
    if username == 'xb_bittensor' and not enriched.get('description'):
        enriched['description'] = 'Bittensor、分散AI、AI Agent、Claude Code/Codex、バイブコーディング、Web3収益化に関心がある編集者。'
    enriched['listener_role'] = 'The editor is the listener and curator; Kurage is the DJ and speaker for all listeners.'
    return enriched


def normalize_segments(parsed: dict[str, Any], theme: str, provider: str, memory: dict[str, Any]) -> list[dict[str, Any]]:
    segs = parsed.get('segments') if isinstance(parsed, dict) else []
    out = []
    seen = set()
    for i, seg in enumerate(segs[:10]):
        if not isinstance(seg, dict):
            continue
        text = re.sub(r'\s+', ' ', str(seg.get('text') or '')).strip()
        text = text.replace('xb_bittensorさん', '編集者さん').replace('xb_bittensor', '編集者')
        if len(text) < 120:
            continue
        if sum(1 for ch in text if '\u3040' <= ch <= '\u30ff' or '\u4e00' <= ch <= '\u9fff') < 60:
            continue
        fp = text_fingerprint(text)
        if fp in seen or is_duplicate_text(text, memory):
            continue
        seen.add(fp)
        out.append({
            'id': f'{int(time.time())}-{provider}-{i}',
            'theme': theme,
            'title': str(seg.get('title') or f'{theme} {i+1}').replace('xb_bittensor', '編集者'),
            'text': text,
            'source': str(seg.get('source') or provider),
            'created_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        })
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--payload', required=True)
    args = parser.parse_args()
    payload = read_json(Path(args.payload), {})
    instruction = str(payload.get('instruction') or '').strip()
    theme = normalize_theme_request(str(payload.get('theme') or instruction or 'AI思考とバイブコーディング'))
    profile = payload.get('profile') if isinstance(payload.get('profile'), dict) else {}
    ignore_profile_script = bool(payload.get('ignore_profile_script')) or bool(instruction)

    if not acquire_lock():
        return
    try:
        log_event('worker_started', pid=os.getpid(), theme=theme)
        update_state(research_status='collecting', loop_state='background_research', current_research_theme=theme)
        research = collect_research(theme, instruction=instruction)
        log_event(
            'research_finished',
            theme=theme,
            ok=research.get('ok'),
            github_count=len(research.get('github') or []),
            x_ok=(research.get('x') or {}).get('ok'),
        )
        update_state(research_status='scripting', last_research=research)
        segments = build_segments(theme, profile, research, instruction=instruction, ignore_profile_script=ignore_profile_script)
        append_queue(segments)
        start_tts_prefetch(segments, 'worker')
        log_event('segments_appended', theme=theme, count=len(segments), sources=sorted({str(s.get('source')) for s in segments}))
        update_state(research_status='ready', loop_state='queue_refilled', last_segments=len(segments), current_research_theme=theme)
    except Exception as exc:
        # The foreground radio must keep talking even if research or LLM generation fails.
        segments = fallback_segments(theme)
        append_queue(segments)
        start_tts_prefetch(segments, 'worker_fallback')
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

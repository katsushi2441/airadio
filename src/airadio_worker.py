#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
STORAGE = ROOT / 'storage'
QUEUE = STORAGE / 'script_queue.json'
STATE = STORAGE / 'radio_state.json'
LOCK = STORAGE / 'worker.lock'
MEMORY = STORAGE / 'talk_memory.json'
PROGRAM_CACHE = STORAGE / 'program_cache'
TTS_PREFETCH_SCRIPT = ROOT / 'src' / 'tts_prefetch.php'
KAGENTREACH = Path(os.environ.get('AIRADIO_KAGENTREACH_DIR', '/home/kojima/work/kagentreach'))
OLLAMA_URL = os.environ.get('AIRADIO_OLLAMA_URL', 'http://192.168.0.14:11434/api/generate')
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
    if os.environ.get('AIRADIO_DISABLE_SERVER_TTS_PREFETCH') == '1':
        log_event('tts_prefetch_skipped', reason=reason, mode='app_server')
        return
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
    return cleaned[:12]


def program_cache_key(text: str) -> str:
    urls = extract_urls(text)
    if not urls:
        return ''
    import hashlib
    return hashlib.sha256('\n'.join(urls).encode('utf-8')).hexdigest()


def write_program_cache(theme: str, instruction: str, research: dict[str, Any], segments: list[dict[str, Any]]) -> None:
    key = program_cache_key(f'{instruction}\n{theme}')
    if not key or not segments:
        return
    urls = extract_urls(f'{instruction}\n{theme}')
    PROGRAM_CACHE.mkdir(parents=True, exist_ok=True)
    safe_segments = []
    for item in segments:
        if not isinstance(item, dict):
            continue
        text = str(item.get('text') or '').strip()
        if not text:
            continue
        safe_segments.append({
            'title': str(item.get('title') or '').strip(),
            'text': text,
            'source': str(item.get('source') or '').strip(),
            'theme': theme,
        })
    if not safe_segments:
        return
    write_json(PROGRAM_CACHE / f'{key}.json', {
        'cache_key': key,
        'urls': urls,
        'theme': theme,
        'instruction': instruction,
        'segments': safe_segments[:20],
        'research': research,
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'updated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
    })
    log_event('program_cache_saved', key=key, url_count=len(urls), segment_count=len(safe_segments))


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
    return repos[:8]


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


def is_github_repo_url(url: str) -> bool:
    return bool(re.search(r'https?://github\.com/[^/\s]+/[^/\s?#]+', url or '', re.I))


def strip_html_noise(body: str) -> str:
    text = re.sub(r'(?is)<(script|style|noscript|svg|canvas|iframe)\b.*?</\1>', ' ', body or '')
    text = re.sub(r'(?is)<!--.*?-->', ' ', text)
    text = re.sub(r'(?i)<br\s*/?>', '\n', text)
    text = re.sub(r'(?i)</(p|div|section|article|li|h[1-6]|tr)>', '\n', text)
    text = re.sub(r'(?is)<[^>]+>', ' ', text)
    text = html.unescape(text)
    text = re.sub(r'https?://[^\s「」『』"\'`<>]+', ' ', text)
    text = re.sub(r'[ \t\r\f\v]+', ' ', text)
    text = re.sub(r'\n\s*\n+', '\n', text)
    return text.strip()


def extract_html_field(body: str, pattern: str) -> str:
    match = re.search(pattern, body or '', re.I | re.S)
    if not match:
        return ''
    return strip_html_noise(match.group(1))[:600]


def fetch_url_content(url: str) -> dict[str, Any]:
    status, body = http_get_text(url, timeout=20, accept='text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8')
    title = extract_html_field(body, r'<title[^>]*>(.*?)</title>')
    description = (
        extract_html_field(body, r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']')
        or extract_html_field(body, r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']')
        or extract_html_field(body, r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']')
        or extract_html_field(body, r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']')
    )
    og_title = (
        extract_html_field(body, r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']')
        or extract_html_field(body, r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']')
    )
    content = strip_html_noise(body)
    return {
        'type': 'web_page',
        'ok': status < 400 and bool(content),
        'url': url,
        'source_label': '参照URLのページ',
        'title': title or og_title,
        'description': description,
        'content_excerpt': content[:7000],
        'status': status,
        'fetched_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
    }


def run_url_research(text: str) -> list[dict[str, Any]]:
    results = []
    for url in extract_urls(text):
        if is_github_repo_url(url):
            continue
        try:
            results.append(fetch_url_content(url))
        except Exception as exc:
            results.append({'type': 'web_page', 'ok': False, 'source_label': '参照URLのページ', 'url': url, 'error': str(exc)})
    return results[:10]


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
            or re.match(r'^(want|need|complete beginners|product managers|students|junior|mid-level|best for|what you will learn|what you will get)', line, re.I)
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


def research_query_from_theme(theme: str, github_items: list[dict[str, Any]], web_pages: list[dict[str, Any]] | None = None) -> str:
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
    if web_pages:
        page = web_pages[0]
        text = f"{page.get('title') or ''} {page.get('description') or ''} {page.get('content_excerpt') or ''}"
        words = re.findall(r'[A-Za-z][A-Za-z0-9_-]{2,}|[\u3040-\u30ff\u3400-\u9fff]{2,}', text)
        picked = []
        for word in words:
            if word.lower() in {'https', 'http', 'www', 'com', 'html'}:
                continue
            if word not in picked:
                picked.append(word)
            if len(picked) >= 8:
                break
        if picked:
            return ' '.join(picked)
    return theme


def decode_bing_redirect(url: str) -> str:
    if 'bing.com/ck/' not in url or 'u=' not in url:
        return url
    try:
        parsed = urllib.parse.urlparse(url)
        value = urllib.parse.parse_qs(parsed.query).get('u', [''])[0]
        if value.startswith('a1'):
            encoded = value[2:]
            padded = encoded + '=' * (-len(encoded) % 4)
            decoded = base64.urlsafe_b64decode(padded.encode('ascii')).decode('utf-8', errors='replace')
            if decoded.startswith('http'):
                return decoded
    except Exception:
        return url
    return url


def search_result_urls(query: str) -> list[str]:
    urls: list[str] = []
    search_urls = [
        'https://duckduckgo.com/html/?q=' + urllib.parse.quote(query[:180]),
        'https://www.bing.com/search?q=' + urllib.parse.quote(query[:180]),
    ]
    for search_url in search_urls:
        try:
            status, body = http_get_text(search_url, timeout=18, accept='text/html,application/xhtml+xml,*/*;q=0.8')
        except Exception:
            continue
        if status >= 400:
            continue
        patterns = [
            r'<h2[^>]*>\s*<a[^>]+href=["\']([^"\']+)["\']',
            r'href=["\']([^"\']+)["\']',
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, body, re.I):
                href = html.unescape(match.group(1))
                if 'uddg=' in href:
                    parsed = urllib.parse.urlparse(href)
                    qs = urllib.parse.parse_qs(parsed.query)
                    href = qs.get('uddg', [''])[0]
                href = decode_bing_redirect(href)
                if not href.startswith('http'):
                    continue
                if any(blocked in href for blocked in ['duckduckgo.com', 'google.com/search', 'bing.com/search', 'r.bing.com', 'th.bing.com']):
                    continue
                href = href.rstrip('。、.!！?)]）')
                if href not in urls:
                    urls.append(href)
                if len(urls) >= 16:
                    return urls
    return urls


def search_related_pages(query: str, known_urls: list[str], limit: int = 4) -> list[dict[str, Any]]:
    if not query.strip() or os.environ.get('AIRADIO_DISABLE_RELATED_SEARCH') == '1':
        return []
    candidates = [url for url in search_result_urls(query) if url not in known_urls]
    pages: list[dict[str, Any]] = []
    for url in candidates:
        try:
            page = fetch_url_content(url)
            if page.get('ok'):
                page['source_label'] = '関連ページ'
                pages.append(page)
        except Exception:
            continue
        if len(pages) >= limit:
            break
    return pages


def collect_research(theme: str, instruction: str = '', duration_hours: int = 1) -> dict[str, Any]:
    source_text = f'{instruction}\n{theme}'
    github_items = run_github_research(source_text)
    web_pages = run_url_research(source_text)
    x_query = research_query_from_theme(theme, github_items, web_pages)
    urls = extract_urls(source_text)
    related_pages = []
    if urls and duration_hours >= 2:
        related_pages = search_related_pages(x_query, urls, limit=min(6, max(2, duration_hours)))
    if github_items or web_pages:
        x_result = {'ok': False, 'skipped': True, 'reason': 'primary_url_material_available'}
    else:
        x_result = run_x_search(x_query)
    return {
        'ok': bool(github_items) or bool(web_pages) or bool(related_pages) or bool(x_result.get('ok')),
        'theme': theme,
        'instruction': instruction,
        'github': github_items,
        'web_pages': web_pages,
        'related_pages': related_pages,
        'x_query': x_query,
        'x': x_result,
        'notes': 'URLs are fetched first and treated as primary source material; related pages are supplemental material for long-form radio.',
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
    cmd = [python_bin, str(script), query, '--limit', '6', '--mode', 'top', '--host', os.environ.get('BROWSER_USE_OLLAMA_HOST', 'http://192.168.0.14:11434')]
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
        return 'このテーマは入門編として扱う。専門用語を短く説明し、初めて聞く人が理解できる順番で話す。'
    if re.search(r'応用|実践|収益|稼', theme):
        return 'このテーマは実践編として扱う。具体的な手順、検証方法、失敗時の立て直しを中心に話す。'
    return '入力されたテーマの意図を保ち、一般論に薄めず、具体例と実装・発信・検証の観点を入れて話す。'




def sanitize_spoken_text(text: str, github_items: list[dict[str, Any]] | None = None) -> str:
    text = re.sub(r'https?://[^\s「」『』"\'`<>]+', '', text or '')
    text = text.replace('xb_bittensorさん', '編集者さん').replace('xb_bittensor', '編集者')
    patterns = [r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+']
    for item in github_items or []:
        repo = str(item.get('repo') or '')
        if repo:
            patterns.append(re.escape(repo))
            patterns.append(re.escape(repo.split('/')[-1]))
    for pattern in patterns:
        text = re.sub(pattern, 'このリポジトリ', text, flags=re.I)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'このリポジトリ(\s*このリポジトリ)+', 'このリポジトリ', text)
    text = re.sub(r'\s+([。、,.])', r'\1', text)
    return text.strip()



def sanitize_prompt_field(value: Any) -> str:
    text = str(value or '')
    text = re.sub(r'https?://[^\s「」『』"\'`<>]+', '', text)
    text = re.sub(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', 'このリポジトリ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def prompt_safe_research(research: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {
        'ok': bool(research.get('ok')),
        'notes': 'Raw URLs and owner/repo identifiers are intentionally omitted from prompt text. Use fetched page text, README, and metadata only.',
    }
    github = []
    for item in research.get('github') or []:
        if not isinstance(item, dict):
            continue
        raw_repo = str(item.get('repo') or '')
        raw_name = raw_repo.split('/')[-1] if raw_repo else ''
        def clean(value: Any) -> str:
            cleaned = sanitize_prompt_field(value)
            if raw_name:
                cleaned = re.sub(re.escape(raw_name), 'この教材', cleaned, flags=re.I)
            return cleaned
        github.append({
            'type': 'github_repo',
            'source_label': 'このGitHubリポジトリ',
            'description': clean(item.get('description')),
            'stars': item.get('stars') or 0,
            'language': clean(item.get('language')),
            'license': clean(item.get('license')),
            'readme_summary': clean(item.get('readme_summary')),
            'readme_excerpt': clean(item.get('readme_excerpt')),
        })
    if github:
        safe['github'] = github
    web_pages = []
    for item in research.get('web_pages') or []:
        if not isinstance(item, dict):
            continue
        web_pages.append({
            'type': 'web_page',
            'source_label': '参照URLのページ',
            'title': sanitize_prompt_field(item.get('title')),
            'description': sanitize_prompt_field(item.get('description')),
            'content_excerpt': sanitize_prompt_field(item.get('content_excerpt')),
            'status': item.get('status') or 0,
        })
    if web_pages:
        safe['web_pages'] = web_pages
    related_pages = []
    for item in research.get('related_pages') or []:
        if not isinstance(item, dict):
            continue
        related_pages.append({
            'type': 'related_page',
            'source_label': '関連ページ',
            'title': sanitize_prompt_field(item.get('title')),
            'description': sanitize_prompt_field(item.get('description')),
            'content_excerpt': sanitize_prompt_field(item.get('content_excerpt')),
            'status': item.get('status') or 0,
        })
    if related_pages:
        safe['related_pages'] = related_pages
    x = research.get('x')
    if isinstance(x, dict):
        safe['x'] = {k: v for k, v in x.items() if k not in {'query', 'url', 'raw'}}
    return safe



def theme_for_speech(theme: str) -> str:
    if extract_urls(theme or ''):
        return 'この資料'
    if re.search(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', theme or ''):
        return 'このリポジトリ'
    cleaned = re.sub(r'https?://[^\s「」『』"\'`<>]+', '', theme or '')
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned or 'このテーマ'

def fallback_segments(theme: str) -> list[dict[str, Any]]:
    memory = load_memory()
    spoken_theme = theme_for_speech(theme)
    base = [
        f'{spoken_theme}について、まず全体像から静かに整理します。いま分かっていること、重要な背景、聞く側が押さえるべきポイントを順番に見ていきます。',
        f'次に、{spoken_theme}の中で特に大事な論点を一つ選びます。名前や流行ではなく、何ができるようになるのか、どんな場面で役に立つのかを考えます。',
        f'{spoken_theme}を実際に使うなら、最初に確認するべきなのは目的です。何を知りたいのか、何を作りたいのか、何を判断したいのか。そこが決まると話が現実に近づきます。',
        f'注意点も見ておきます。{spoken_theme}は便利な言葉ほど、意味が広がりすぎます。資料に書かれていることと、自分で推測したことを分けて考える必要があります。',
        f'最後に、{spoken_theme}を次の行動へ変えるなら、小さな問いを一つ置くのがよさそうです。今日この話から、どの一文を持ち帰るか。そこから始めます。',
    ]
    items = []
    for i, text in enumerate(base):
        if is_duplicate_text(text, memory):
            continue
        items.append({'id': f'fallback-{int(time.time())}-{i}', 'theme': theme, 'title': f'{spoken_theme} {i + 1}', 'text': text, 'source': 'fallback-generic'})
    if not items:
        now_label = time.strftime('%H時%M分')
        text = f'{now_label}の時点で、{spoken_theme}についてもう一度整理します。次の台本では、資料に書かれている内容をもとに、重要な点から順に話します。'
        items.append({'id': f'fallback-{int(time.time())}-fresh', 'theme': theme, 'title': f'{spoken_theme}の続き', 'text': text, 'source': 'fallback-generic'})
    remember_segments(items)
    return items


def bridge_segments(theme: str) -> list[dict[str, Any]]:
    memory = load_memory()
    spoken_theme = theme_for_speech(theme)
    base = [
        f'{spoken_theme}について、次の台本を整えるあいだに、全体像を短く振り返ります。大事なのは、言葉の印象ではなく、資料が何を伝えようとしているかです。',
        '少しだけ視点を変えます。いま聞いている内容を、自分ならどこで使うか。そう考えると、抽象的な話も具体的になります。',
        f'{spoken_theme}を理解するときは、結論を急がず、背景、仕組み、使いどころ、注意点に分けると聞きやすくなります。',
    ]
    now = int(time.time())
    items = []
    for i, text in enumerate(base):
        if is_duplicate_text(text, memory):
            continue
        items.append({
            'id': f'bridge-{now}-{i}',
            'theme': theme,
            'title': f'{spoken_theme} {i + 1}',
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
    github_items = research.get('github') if isinstance(research, dict) else []
    web_items = research.get('web_pages') if isinstance(research, dict) else []
    related_items = research.get('related_pages') if isinstance(research, dict) else []
    github_primary = bool(github_items)
    web_primary = bool(web_items)
    url_count = len(extract_urls(f'{instruction}\n{theme}'))
    prompt_theme = '複数URL資料の内容' if url_count >= 2 else ('このGitHubリポジトリの内容' if github_primary else ('取得したWebページの内容' if web_primary else sanitize_spoken_text(theme)))
    prompt_instruction = '入力URL先の内容を読んで考察する' if (github_primary or web_primary) else sanitize_spoken_text(instruction)
    research_text = json.dumps(prompt_safe_research(research) if isinstance(research, dict) else {}, ensure_ascii=False)[:9000]
    memory_text = json.dumps({
        'recent_topics': memory.get('topics', [])[-24:],
        'recent_texts': memory.get('recent_texts', [])[-10:],
    }, ensure_ascii=False)[:5000]
    prompt = f'''
あなたは「Kurage AI VTuber Radio」のメイン構成作家です。
KurageがDJで、編集者とリスナーへ向けて静かに解説します。
自由入力指示がある場合は、そのテーマだけを主題にします。資料や指示に書かれていない文脈を勝手に足さないでください。
自由入力指示がない場合だけ、聞き手プロフィールを参考にテーマを広げてください。

テーマ: {prompt_theme}
編集者の自由入力指示: {prompt_instruction or 'なし'}
プロフィール台本を無視するか: {'はい' if ignore_profile_script else 'いいえ'}
GitHubリポジトリを主教材として扱うか: {'はい' if github_primary else 'いいえ'}
Webページを主教材として扱うか: {'はい' if web_primary else 'いいえ'}
関連ページを補助資料として使うか: {'はい' if related_items else 'いいえ'}
テーマ解釈: {guidance}
聞き手プロフィール: {profile_text}
情報収集メモ: {research_text}
直近で話した内容（絶対に繰り返さない）: {memory_text}

要件:
- 日本語。
- Kurageが編集者とリスナーへ話しかける口調。
- 内部アカウント名やユーザーIDは読み上げない。xb_bittensorのような名前は必ず「編集者」と呼ぶ。
- 英語の長い言い回しを混ぜず、自然な日本語で説明する。固有名詞以外は日本語にする。
- テーマと資料の内容を、リスナーにも分かる自然な解説へ変換する。
- 自由入力指示がある場合は、その文章の意図を最優先する。プロフィール起点の定番台本や別テーマに勝手に戻らない。
- 自由入力指示はフォーマットなしの自然文として扱い、「何について」「どのレベルで」「どう話してほしいか」を推測して台本化する。
- URLが入力された場合は、URL文字列ではなく、情報収集メモ内の取得済み本文、README、title、descriptionを一次資料として扱う。
- 複数URLが入力された場合は、各資料を別々に扱い、共通点、相違点、どの順番で理解するとよいかを整理する。
- 関連ページがある場合は補助資料として使い、一次URLの主張を広げる。ただし一次URLの内容と関係が薄い話へ逸れない。
- GitHubリポジトリURLが入力された場合は、情報収集メモ内のgithub項目を一次資料として扱う。READMEの内容を読んで、Claude自身が重要だと判断した点を話す。
- 通常WebページURLが入力された場合は、情報収集メモ内のweb_pages項目を一次資料として扱う。ページ本文と説明文から主題を理解して話す。
- URL、owner/repo、長い英数字識別子、ファイルパスは読み上げない。
- URL主教材の場合、各segmentの角度は overview, why_it_matters, key_points, practical_use, caveats, editor_action のように、資料の中身に沿って分ける。
- 1本あたり60〜120秒程度で読める長さ。
- 同じ言い回し、同じ結論、同じブリッジトークは禁止。
- 抽象論だけで終わらせない。ただし資料や指示にない話題を無理に足さない。
- 眠りを促すラジオなので穏やか。ただし中身は濃く、薄い一般論にしない。
- テーマ解釈を最優先する。たとえば「入門編」なら、初めて聞く人が理解できる順番にする。
- 各segmentは別の角度にする。角度は資料の内容からClaudeが決める。
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
            if github_primary or web_primary:
                for item in out:
                    item['text'] = sanitize_spoken_text(str(item.get('text') or ''), github_items)
                    item['title'] = sanitize_spoken_text(str(item.get('title') or ''), github_items)
            if len(out) >= 4:
                remember_segments(out[:6])
                return out[:6]
            if out:
                out.extend(bridge_segments(theme)[: 6 - len(out)])
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
        text = sanitize_spoken_text(text)
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
            'title': sanitize_spoken_text(str(seg.get('title') or f'{theme} {i+1}')),
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
    theme = normalize_theme_request(str(payload.get('theme') or instruction or '編集者が選ぶテーマ'))
    profile = payload.get('profile') if isinstance(payload.get('profile'), dict) else {}
    ignore_profile_script = bool(payload.get('ignore_profile_script')) or bool(instruction)

    if not acquire_lock():
        return
    try:
        log_event('worker_started', pid=os.getpid(), theme=theme)
        update_state(research_status='collecting', loop_state='background_research', current_research_theme=theme)
        duration_hours = max(1, min(6, int(payload.get('duration_hours') or 1)))
        research = collect_research(theme, instruction=instruction, duration_hours=duration_hours)
        log_event(
            'research_finished',
            theme=theme,
            ok=research.get('ok'),
            github_count=len(research.get('github') or []),
            web_count=len(research.get('web_pages') or []),
            related_count=len(research.get('related_pages') or []),
            x_ok=(research.get('x') or {}).get('ok'),
        )
        update_state(research_status='scripting', last_research=research)
        segments = build_segments(theme, profile, research, instruction=instruction, ignore_profile_script=ignore_profile_script)
        write_program_cache(theme, instruction, research, segments)
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

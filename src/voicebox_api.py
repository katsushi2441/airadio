from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests, uuid, subprocess
import requests.exceptions
import tempfile
import json
from typing import List
from fastapi import UploadFile, File, Form, HTTPException


from pathlib import Path
from datetime import datetime

VOICEVOX = "http://127.0.0.1:50021"
SPEAKER = 1  # 四国めたん

app = FastAPI()


# =========================
# AI / Ollama : Daily Summary
# =========================
class DailySummaryRequest(BaseModel):
    texts: list
    date: str | None = None


@app.post("/daily_summary")
def daily_summary(req: DailySummaryRequest):

    texts = req.texts
    date  = req.date or ""

    if not isinstance(texts, list) or not texts:
        raise HTTPException(status_code=400, detail="texts required")

    joined = "\n\n".join([t.strip() for t in texts if isinstance(t, str) and t.strip()])

    if not joined:
        raise HTTPException(status_code=400, detail="empty texts")

    prompt = f"""
あなたはナレッジエディターです。
以下は同一日の複数の知識レポートです。

内容を相互に関連づけて統合し、
「1日分の知識まとめ」を日本語の読み物として作成してください。

条件：
・600〜2200文字
・感想、評価、称賛、改善提案は禁止
・見出し、箇条書き、URLは禁止
・ニュースの羅列は禁止
・事実と論点のみを書く
・最後に、その日全体から読み取れることを短くまとめる
・必ず日本語で、外国語は禁止です。日本語で生成してください


# 日付
{date}


# 知識レポート一覧
{joined}

"""

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "seed": 12345,
            "top_p": 0.8
        }
    }

    try:
        r = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=240
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    text = data.get("response", "")
    if not isinstance(text, str):
        text = ""

    return {
        "ok": True,
        "summary": text.strip()
    }

# =========================
# AI / Ollama : News Analysis
# =========================
class NewsAnalysisRequest(BaseModel):
    keyword: str
    news: list

@app.post("/news_analysis")
def news_analysis(req: NewsAnalysisRequest):

    keyword = req.keyword.strip()
    news_items = req.news

    if not keyword or not isinstance(news_items, list) or not news_items:
        raise HTTPException(status_code=400, detail="invalid parameters")

    lines = []
    i = 1
    for n in news_items:
        title = n.get("title", "").strip()
        date  = n.get("pubDate", "").strip()
        if title:
            lines.append(f"{i}. {title} ({date})")
            i += 1

    news_text = "\n".join(lines)

    prompt = f"""
あなたはプロのリサーチャー兼ナレッジエディターです。
以下のニュース一覧をもとに、情報を整理・統合し、
後から読み返しても価値がある考察文章を日本語で作成してください。

# キーワード
{keyword}

# ニュース一覧
{news_text}

# 条件
- 600〜900文字
- 見出し・箇条書き・挨拶・URLは禁止
- 読み物として自然な文章のみ
- 主観的な感想は入れない
- 短期的な速報性より再読価値を重視

# 開始文（改変禁止）
- {keyword}に関する最近の動向について整理する。
"""

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.7
        }
    }

    try:
        r = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=180
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    text = data.get("response", "")
    if not isinstance(text, str):
        text = ""

    return {
        "ok": True,
        "analysis": text.strip()
    }


# =========================
# AI / Ollama : Keyword Seed
# =========================
from pydantic import BaseModel
import requests

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_MODEL = "gemma3:12b"

class KeywordSeedRequest(BaseModel):
    keyword: str

@app.post("/keyword_seed")
def keyword_seed(req: KeywordSeedRequest):

    keyword = req.keyword.strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="keyword required")

    prompt = f"""
あなたはWEBメディア編集者兼リサーチャーです。

以下のキーワードを起点に、
**ニュース記事・技術記事として継続的に扱いやすい**
関連キーワードを10個生成してください。

# 元キーワード
{keyword}

# 条件
- 名詞
- 技術・IT・AI・Web業界で実際に使われる用語
- **直近1年以内にニュースや記事が複数存在する語**
- **企業名・プロダクト名・技術名称・研究分野名は可**
- 単独で意味が広すぎる抽象概念は禁止
- 記事タイトルとして成立する
- 元キーワードと話題領域が明確に接続できる
- 3つだけ
- 番号・記号・説明は禁止
- 改行区切りのみで出力
"""

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.7
        }
    }

    try:
        r = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=120
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    text = data.get("response", "").strip()
    if not text:
        return {
            "ok": True,
            "keyword": keyword,
            "seeds": []
        }

    seeds = [line.strip() for line in text.split("\n") if line.strip()]

    return {
        "ok": True,
        "keyword": keyword,
        "seeds": seeds[:3]
    }

import requests
from fastapi import Body

import re

@app.post("/generate_story")
async def generate_story(data: dict = Body(...)):
    if "prompt" not in data:
        raise HTTPException(status_code=400, detail="prompt required")
    user_prompt = data["prompt"]
    try:
        res = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": user_prompt,
                "stream": False
            },
            timeout=120
        )
        if res.status_code != 200:
            raise HTTPException(status_code=500, detail="ollama error")
        result = res.json()
        
        # Ollamaのレスポンスからテキストを取得
        response_text = result.get("response", "")
        
        # マークダウンのコードブロックを除去
        import re
        clean_text = re.sub(r'```json\s*', '', response_text)
        clean_text = re.sub(r'```\s*', '', clean_text)
        clean_text = clean_text.strip()
        
        # JSONとしてパース
        import json
        parsed = json.loads(clean_text)
        
        return parsed  # JSONオブジェクトとして返す
        
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"JSON parse error: {str(e)}, response: {response_text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate_story2")
async def generate_story2(data: dict = Body(...)):

    user_script = data.get("script", "").strip()
    if not user_script:
        raise HTTPException(status_code=400, detail="script required")

    prompt = f"""
あなたは漫画脚本家です。

以下の原稿をもとに、
1～5コマの短い漫画シナリオを作成してください。

コマ数は内容に応じて判断してください。
（最小1、最大5）

必ず有効なJSONのみを出力してください。
マークダウンは禁止。
説明文は禁止。
ナレーション：説明文字は不要です。

形式:
{{
  "frames": [
    {{ "frame": 1, "text": "セリフ" }}
  ]
}}

原稿:
{user_script}
"""

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False
    }

    r = requests.post(OLLAMA_URL, json=payload, timeout=180)

    if r.status_code != 200:
        raise HTTPException(status_code=500, detail=r.text)

    result = r.json()
    output_text = result.get("response", "").strip()

    # ?? ここが重要：JSONだけ抽出
    match = re.search(r"\{.*\}", output_text, re.DOTALL)
    if not match:
        raise HTTPException(status_code=500, detail="Invalid JSON from LLM")

    json_text = match.group(0)

    try:
        parsed = json.loads(json_text)
    except Exception:
        raise HTTPException(status_code=500, detail="Broken JSON from LLM")

    # ?? frames保証
    if "frames" not in parsed or not isinstance(parsed["frames"], list):
        raise HTTPException(status_code=500, detail="frames missing")

    return parsed

@app.post("/audio_to_mp4_multi")
async def audio_to_mp4_multi(
    audio_url: str = Form(...),
    script_text: str = Form(""),
    images: List[UploadFile] = File(...,alias="images[]")
):

    if not images:
        raise HTTPException(status_code=400, detail="images required")


    saved_images = []

    for image in images:

        ext = Path(image.filename).suffix.lower()
        if ext not in [".png", ".jpg", ".jpeg", ".webp"]:
            raise HTTPException(status_code=400, detail="invalid image type")

        img_name = uuid.uuid4().hex + ext
        img_path = VIDEO_IMG_DIR / img_name

        with img_path.open("wb") as f:
            shutil.copyfileobj(image.file, f)

        saved_images.append(img_path)

    # 台本ファイル
    script_file = None
    if script_text.strip():
        tf = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8")
        tf.write(script_text)
        tf.close()
        script_file = tf.name

    base = Path(audio_url).stem
    out_mp4 = VIDEO_OUT_DIR / f"{base}.mp4"

    # 音声長取得
    probe = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "format=duration",
            "-of", "json",
            audio_url
        ],
        capture_output=True,
        text=True
    )

    try:
        duration = float(json.loads(probe.stdout)["format"]["duration"])
    except Exception:
        duration = 1.0

    # 1枚あたり表示時間
    per_image = duration / len(saved_images)

    # drawtext
    drawtext = ""
    if script_file:
        drawtext = (
            "drawtext="
            "fontfile=/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc:"
            f"textfile={script_file}:"
            "fontsize=36:"
            "fontcolor=white:"
            "borderw=2:"
            "bordercolor=black:"
            "line_spacing=10:"
            "x=(w-text_w)/2:"
            f"y=h-200-(t/{duration})*(h+text_h/2)"
        )

    cmd = [
        "ffmpeg",
        "-y"
    ]

    # 各画像を -loop 1 -t で追加
    for img in saved_images:
        cmd += [
            "-loop", "1",
            "-t", str(per_image),
            "-i", str(img)
        ]

    # 音声
    cmd += [
        "-i", audio_url
    ]

    # filter_complex で内部concat
    filter_inputs = "".join([f"[{i}:v]" for i in range(len(saved_images))])
    filter_complex = f"{filter_inputs}concat=n={len(saved_images)}:v=1:a=0,format=yuv420p[v]"

    if drawtext:
        filter_complex = f"{filter_complex};[v]{drawtext}[v2]"
        video_map = "[v2]"
    else:
        video_map = "[v]"

    cmd += [
        "-filter_complex", filter_complex,
        "-map", video_map,
        "-map", f"{len(saved_images)}:a",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(out_mp4)
    ]

    p = subprocess.run(cmd, capture_output=True, text=True)

    if p.returncode != 0:
        raise HTTPException(status_code=500, detail=p.stderr)

    return {
        "ok": True,
        "file": out_mp4.name,
        "mp4_url": f"https://exbridge.ddns.net/aidexx/video_mp4/{out_mp4.name}"
    }


@app.post("/audio_to_mp4_multi2")
async def audio_to_mp4_multi2(
    audio_url: str = Form(...),
    script_text: str = Form(""),
    images: List[UploadFile] = File(...)
):

    if not images:
        raise HTTPException(status_code=400, detail="images required")


    saved_images = []

    for image in images:

        ext = Path(image.filename).suffix.lower()
        if ext not in [".png", ".jpg", ".jpeg", ".webp"]:
            raise HTTPException(status_code=400, detail="invalid image type")

        img_name = uuid.uuid4().hex + ext
        img_path = VIDEO_IMG_DIR / img_name

        with img_path.open("wb") as f:
            shutil.copyfileobj(image.file, f)

        saved_images.append(img_path)

    # 台本ファイル
    script_file = None
    if script_text.strip():
        tf = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8")
        tf.write(script_text)
        tf.close()
        script_file = tf.name

    base = Path(audio_url).stem
    out_mp4 = VIDEO_OUT_DIR / f"{base}.mp4"

    # 音声長取得
    probe = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "format=duration",
            "-of", "json",
            audio_url
        ],
        capture_output=True,
        text=True
    )

    try:
        duration = float(json.loads(probe.stdout)["format"]["duration"])
    except Exception:
        duration = 1.0

    # 1枚あたり表示時間
    per_image = duration / len(saved_images)

    # concat用テキスト作成
    concat_file = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8")

    for img in saved_images:
        concat_file.write(f"file '{img}'\n")
        concat_file.write(f"duration {per_image}\n")

    # 最後の画像はduration不要（ffmpeg仕様）
    concat_file.write(f"file '{saved_images[-1]}'\n")
    concat_file.close()

    # drawtext
    drawtext = ""
    if script_file:
        drawtext = (
            "drawtext="
            "fontfile=/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc:"
            f"textfile={script_file}:"
            "fontsize=36:"
            "fontcolor=white:"
            "borderw=2:"
            "bordercolor=black:"
            "line_spacing=10:"
            "x=(w-text_w)/2:"
            f"y=h-200-(t/{duration})*(h+text_h/2)"
        )

    cmd = [
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_file.name,
        "-i", audio_url,
    ]

    if drawtext:
        cmd += ["-vf", drawtext]

    cmd += [
        "-vsync", "vfr",
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(out_mp4)
    ]

    p = subprocess.run(cmd, capture_output=True, text=True)

    if p.returncode != 0:
        raise HTTPException(status_code=500, detail=p.stderr)

    return {
        "ok": True,
        "file": out_mp4.name,
        "mp4_url": f"https://exbridge.ddns.net/aidexx/video_mp4/{out_mp4.name}"
    }

# =========================
# TTS サンプル用
# =========================
class TTSSample(BaseModel):
    text: str
    speaker: int = SPEAKER
    speed: float = 1.0
    pitch: float = 0.0
    intonation: float = 1.0
    volume: float = 1.0


# =========================
# TTS 生成
# =========================
class TTS(BaseModel):
    text: str
    speaker: int = SPEAKER

# =========================
# ラジオ + BGM ミックス保存
# =========================
class MixRequest(BaseModel):
    radio_url: str
    bgm_url: str
    bgm_volume: int = 30
    bgm_start: float = 0.0
    source_file: str   # ★ 追加

# =========================
# mp3 / wav + 画像 → mp4
# =========================
from fastapi import UploadFile, File, Form
import shutil

VIDEO_IMG_DIR = Path("../../video_img")
VIDEO_OUT_DIR = Path("../../video_mp4")

VIDEO_IMG_DIR.mkdir(exist_ok=True)
VIDEO_OUT_DIR.mkdir(exist_ok=True)

@app.post("/audio_to_mp4")
def audio_to_mp4(
    image: UploadFile = File(...),
    audio_url: str = Form(...),
    script_text: str = Form("")
):
    if not audio_url:
        raise HTTPException(status_code=400, detail="audio_url required")

    # 画像保存
    img_ext = Path(image.filename).suffix.lower()
    if img_ext not in [".png", ".jpg", ".jpeg", ".webp"]:
        raise HTTPException(status_code=400, detail="invalid image type")

    img_name = uuid.uuid4().hex + img_ext
    img_path = VIDEO_IMG_DIR / img_name

    with img_path.open("wb") as f:
        shutil.copyfileobj(image.file, f)

    # 台本テキストを一時ファイルへ
    script_file = None
    if script_text.strip():
        tf = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8")
        tf.write(script_text)
        tf.close()
        script_file = tf.name

    # 出力 mp4 名
    base = Path(audio_url).stem
    out_mp4 = VIDEO_OUT_DIR / f"{base}.mp4"

    # 音声の長さ（秒）取得
    probe = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "format=duration",
            "-of", "json",
            audio_url
        ],
        capture_output=True,
        text=True
    )

    try:
        duration = float(json.loads(probe.stdout)["format"]["duration"])
    except Exception:
        duration = 1.0

    # drawtext（エンドロール）
    drawtext = ""
    if script_file:
        drawtext = (
            "drawtext="
            "fontfile=/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc:"
            f"textfile={script_file}:"
            "fontsize=36:"
            "fontcolor=white:"
            "borderw=2:"
            "bordercolor=black:"
            "line_spacing=10:"
            "x=(w-text_w)/2:"
            f"y=h-200-(t/{duration})*(h+text_h/2)"
        )

    cmd = [
        "ffmpeg",
        "-fflags", "+genpts",
        "-y",
        "-loop", "1",
        "-i", str(img_path),
        "-i", audio_url,
    ]

    if drawtext:
        cmd += ["-vf", drawtext]

    cmd += [
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(out_mp4)
    ]

    p = subprocess.run(cmd, capture_output=True, text=True)

    if p.returncode != 0:
        raise HTTPException(status_code=500, detail=p.stderr)

    return {
        "ok": True,
        "file": out_mp4.name,
        "mp4_url": f"https://exbridge.ddns.net/aidexx/video_mp4/{out_mp4.name}"
    }


# =========================
# mp3 / wav + 動画(mp4) →mp4（背景動画用）
# =========================
@app.post("/audio_to_video_mp4")
def audio_to_video_mp4(
    image: UploadFile = File(...),
    audio_url: str = Form(...),
    script_text: str = Form("")
):
    if not audio_url:
        raise HTTPException(status_code=400, detail="audio_url required")

    # 動画のみ許可
    vid_ext = Path(image.filename).suffix.lower()
    if vid_ext != ".mp4":
        raise HTTPException(status_code=400, detail="mp4 only")

    vid_name = uuid.uuid4().hex + vid_ext
    vid_path = VIDEO_IMG_DIR / vid_name

    with vid_path.open("wb") as f:
        shutil.copyfileobj(image.file, f)

    # 台本一時ファイル
    script_file = None
    if script_text.strip():
        tf = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8")
        tf.write(script_text)
        tf.close()
        script_file = tf.name

    base = Path(audio_url).stem
    out_mp4 = VIDEO_OUT_DIR / f"{base}.mp4"

    # 音声長取得
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "format=duration",
            "-of", "json",
            audio_url
        ],
        capture_output=True,
        text=True
    )

    try:
        duration = float(json.loads(probe.stdout)["format"]["duration"])
    except Exception:
        duration = 1.0

    # 動画長取得
    video_probe = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "format=duration",
            "-of", "json",
            str(vid_path)
        ],
        capture_output=True,
        text=True
    )

    try:
        video_duration = float(json.loads(video_probe.stdout)["format"]["duration"])
    except Exception:
        video_duration = duration

    drawtext = ""

    if script_file:
        drawtext = (
            "drawtext="
            "fontfile=/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc:"
            f"textfile={script_file}:"
            "fontsize=16:"
            "fontcolor=white:"
            "borderw=2:"
            "bordercolor=black:"
            "line_spacing=10:"
            "x=(w-text_w)/2:"
            f"y=h-200-(t/{duration})*(h+text_h/2)"
        )

    vf_filter = None

    if video_duration < duration and video_duration > 0:

        head_tail = video_duration
        middle_duration = duration - (head_tail * 2)

        if middle_duration > 0:

            vf_filter = (
                f"[0:v]trim=0:{video_duration},setpts=PTS-STARTPTS[v1];"
                f"[0:v]trim=0:{video_duration},setpts=PTS-STARTPTS,"
                f"select='eq(n\\,last)',"
                f"tpad=stop_mode=clone:stop_duration={middle_duration}[v2];"
                f"[0:v]trim=0:{video_duration},setpts=PTS-STARTPTS[v3];"
                f"[v1][v2][v3]concat=n=3:v=1:a=0[vtmp]"
            )

            if script_file:
                vf_filter += f";[vtmp]{drawtext}[vout]"
            else:
                vf_filter += ";[vtmp]copy[vout]"

    vf_parts = []

    if video_duration < duration:
        vf_parts.append(
            f"tpad=stop_mode=clone:stop_duration={duration - video_duration}"
        )

    if script_file:
        vf_parts.append(
            "drawtext="
            "fontfile=/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc:"
            f"textfile={script_file}:"
            "fontsize=16:"
            "fontcolor=white:"
            "borderw=2:"
            "bordercolor=black:"
            "line_spacing=10:"
            "x=(w-text_w)/2:"
            f"y=h-200-(t/{duration})*(h+text_h/2)"
        )

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(vid_path),
        "-i", audio_url,
        "-map", "0:v:0",
        "-map", "1:a:0",
    ]

    if vf_parts:
        cmd += ["-vf", ",".join(vf_parts)]

    cmd += [
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", str(duration),
        str(out_mp4)
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)

    if p.returncode != 0:
        raise HTTPException(status_code=500, detail=p.stderr)

    return {
        "ok": True,
        "file": out_mp4.name,
        "mp4_url": f"https://exbridge.ddns.net/aidexx/video_mp4/{out_mp4.name}"
    }

# =========================
# mp3 / wav + 動画(mp4) → mp4（背景動画用）
# =========================
@app.post("/audio_to_video_mp4bk")
def audio_to_video_mp4(
    image: UploadFile = File(...),
    audio_url: str = Form(...),
    script_text: str = Form("")
):
    if not audio_url:
        raise HTTPException(status_code=400, detail="audio_url required")

    # 動画のみ許可
    vid_ext = Path(image.filename).suffix.lower()
    if vid_ext != ".mp4":
        raise HTTPException(status_code=400, detail="mp4 only")

    vid_name = uuid.uuid4().hex + vid_ext
    vid_path = VIDEO_IMG_DIR / vid_name

    with vid_path.open("wb") as f:
        shutil.copyfileobj(image.file, f)

    # 台本一時ファイル
    script_file = None
    if script_text.strip():
        tf = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8")
        tf.write(script_text)
        tf.close()
        script_file = tf.name

    base = Path(audio_url).stem
    out_mp4 = VIDEO_OUT_DIR / f"{base}.mp4"

    # 音声長取得
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "format=duration",
            "-of", "json",
            audio_url
        ],
        capture_output=True,
        text=True
    )

    try:
        duration = float(json.loads(probe.stdout)["format"]["duration"])
    except Exception:
        duration = 1.0

    drawtext = ""
    if script_file:
        drawtext = (
            "drawtext="
            "fontfile=/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc:"
            f"textfile={script_file}:"
            "fontsize=16:"
            "fontcolor=white:"
            "borderw=2:"
            "bordercolor=black:"
            "line_spacing=10:"
            "x=(w-text_w)/2:"
            f"y=h-200-(t/{duration})*(h+text_h/2)"
        )

    cmd = [
        "ffmpeg",
        "-y",
        "-stream_loop", "-1",
        "-i", str(vid_path),     # 背景動画（音声含まれていてもOK）
        "-i", audio_url,         # 使う音声
        "-map", "0:v:0",         # 動画は背景のみ
        "-map", "1:a:0",         # 音声は外部のみ
    ]

    if drawtext:
        cmd += ["-vf", drawtext]

    cmd += [
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-t", str(duration),
        str(out_mp4)
    ]

    p = subprocess.run(cmd, capture_output=True, text=True)

    if p.returncode != 0:
        raise HTTPException(status_code=500, detail=p.stderr)

    return {
        "ok": True,
        "file": out_mp4.name,
        "mp4_url": f"https://exbridge.ddns.net/aidexx/video_mp4/{out_mp4.name}"
    }


@app.post("/mix")
def mix_audio(req: MixRequest):
    radio_url = req.radio_url.strip()
    bgm_url   = req.bgm_url.strip()

    if not radio_url or not bgm_url:
        raise HTTPException(status_code=400, detail="invalid parameters")

    vol = max(0, min(100, req.bgm_volume))
    vol_f = vol / 100
    bgm_start = max(0.0, req.bgm_start)

    outdir = Path("../../mixed")
    outdir.mkdir(exist_ok=True)

    src = Path(req.source_file).name
    base = src.rsplit(".", 1)[0]
    outname = base + ".mp3"
    outpath = outdir / outname
    delay_ms = int(bgm_start * 1000)

    cmd = [
        "ffmpeg", "-y",
        "-i", radio_url,
        "-i", bgm_url,
        "-filter_complex",
        f"[1:a]volume={vol_f},adelay={delay_ms}|{delay_ms}[a1];[0:a][a1]amix=inputs=2",
        str(outpath)
    ]

    p = subprocess.run(cmd, capture_output=True, text=True)

    if p.returncode != 0:
        raise HTTPException(status_code=500, detail=p.stderr.strip())

    return {
        "ok": True,
        "file": outname,
        "url": f"https://exbridge.ddns.net/aidexx/mixed/{outname}"
    }


@app.post("/tts")
def tts(req: TTS):
    text = req.text.strip()
    if not text:
        return {"error": "empty"}

    try:
        r = requests.post(
            f"{VOICEVOX}/audio_query",
            params={
                "speaker": req.speaker,
                "text": text
            },
            timeout=110
        )
        r.raise_for_status()

        q = r.json()

        r2 = requests.post(
            f"{VOICEVOX}/synthesis",
            params={"speaker": req.speaker},
            json=q,
            timeout=130
        )
        r2.raise_for_status()

    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=str(e))

    audio = r2.content

    outdir = Path("../../tts")
    outdir.mkdir(exist_ok=True)
    fname = f"{uuid.uuid4().hex}.wav"
    path = outdir / fname
    path.write_bytes(audio)

    return {
        "audio_url": f"https://exbridge.ddns.net/aidexx/tts/{fname}"
    }

# =========================
# TTS ファイル管理
# =========================
AUDIO_DIR = Path("../../tts").resolve()

class DeleteRequest(BaseModel):
    file: str

@app.get("/files")
def list_files():
    if not AUDIO_DIR.exists():
        return []

    result = []
    for f in AUDIO_DIR.glob("*.wav"):
        stat = f.stat()
        result.append({
            "file": f.name,
            "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "size": stat.st_size
        })
    return result

@app.post("/delete")
def delete_file(req: DeleteRequest):
    name = Path(req.file).name
    target = (AUDIO_DIR / name).resolve()

    if not str(target).startswith(str(AUDIO_DIR)):
        raise HTTPException(status_code=400, detail="invalid path")

    if not target.exists():
        raise HTTPException(status_code=404, detail="file not found")

    if target.suffix != ".wav":
        raise HTTPException(status_code=400, detail="invalid file type")

    target.unlink()
    return {"status": "ok", "deleted": name}

# =========================
# Blogger 投稿（TTSサーバ側で python 実行）
# =========================
@app.post("/blogger")
def blogger(req: dict):
    file = req.get("file")
    script = req.get("script")

    if not file or not script:
        return {"ok": False, "error": "file or script missing"}

    p = subprocess.run(
        ["python3", "tts2blog.py", file],
        input=script,
        text=True,
        capture_output=True
    )

    return {
        "ok": p.returncode == 0,
        "stdout": p.stdout,
        "stderr": p.stderr
    }

@app.post("/tts_sample")
def tts_sample(req: TTSSample):
    text = req.text.strip()
    if not text:
        return {"error": "empty"}

    try:
        r = requests.post(
            f"{VOICEVOX}/audio_query",
            params={
                "speaker": req.speaker,
                "text": text
            },
            timeout=60
        )
        r.raise_for_status()

        q = r.json()

        # ---- パラメータ上書き（UI対応）----
        q["speedScale"] = req.speed
        q["pitchScale"] = req.pitch
        q["intonationScale"] = req.intonation
        q["volumeScale"] = req.volume

        r2 = requests.post(
            f"{VOICEVOX}/synthesis",
            params={"speaker": req.speaker},
            json=q,
            timeout=120
        )
        r2.raise_for_status()

    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=str(e))

    audio = r2.content

    outdir = Path("../../tts_sample")
    outdir.mkdir(exist_ok=True)

    fname = "sample.wav"
    path = outdir / fname
    path.write_bytes(audio)

    return {
        "audio_url": f"https://exbridge.ddns.net/aidexx/tts_sample/{fname}"
    }


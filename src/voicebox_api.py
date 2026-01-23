from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests, uuid, subprocess
import requests.exceptions
import tempfile
import json

from pathlib import Path
from datetime import datetime

VOICEVOX = "http://127.0.0.1:50021"
SPEAKER = 1  # 四国めたん

app = FastAPI()

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
            "line_spacing=10:"
            "x=(w-text_w)/2+72:"
            f"y=h-230-(t/{duration})*(h+text_h)"
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


#!/usr/bin/env python3
import glob
import subprocess
import os

img_path = "../../airadio_aespa2.png"
tts_dir = "../../mixed"

if not os.path.isfile(img_path):
    raise FileNotFoundError(img_path)

wav_files = glob.glob(os.path.join(tts_dir, "*.wav"))
mp3_files = glob.glob(os.path.join(tts_dir, "*.mp3"))
audio_files = wav_files + mp3_files

if not audio_files:
    raise RuntimeError("tts ディレクトリに wav / mp3 がありません")

for audio_path in audio_files:
    mp4_path = os.path.splitext(audio_path)[0] + ".mp4"

    if os.path.isfile(mp4_path):
        print("既に存在するためスキップ:", mp4_path)
        continue

    cmd = [
        "ffmpeg",
        "-fflags", "+genpts",
        "-y",
        "-loop", "1",
        "-i", img_path,
        "-i", audio_path,
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        mp4_path
    ]

    cmdorg = [
        "ffmpeg",
        "-y",
        "-loop", "1",
        "-i", img_path,
        "-i", audio_path,
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        mp4_path
    ]

    print("変換中:", audio_path)
    subprocess.run(cmd, check=True)

print("完了: wav / mp3 → mp4 変換終了")


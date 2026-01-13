#!/usr/bin/env python3
import glob
import subprocess
import os

img_path = "../../airadio_simpsons.png"
tts_dir = "../../tts"

if not os.path.isfile(img_path):
    raise FileNotFoundError(img_path)

wav_files = glob.glob(os.path.join(tts_dir, "*.wav"))
if not wav_files:
    raise RuntimeError("tts ディレクトリに wav がありません")

for wav_path in wav_files:
    mp4_path = wav_path[:-4] + ".mp4"

    if os.path.isfile(mp4_path):
        print("既に存在するためスキップ:", mp4_path)
        continue

    cmd = [
        "ffmpeg",
        "-y",
        "-loop", "1",
        "-i", img_path,
        "-i", wav_path,
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        mp4_path
    ]

    print("変換中:", wav_path)
    subprocess.run(cmd, check=True)

print("完了: wav → mp4 変換終了")


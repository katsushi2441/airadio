#!/usr/bin/env python3
# =====================================================
# tts2blog.py
# TTS音声ファイル + 台本 → Blogger メール投稿
# ※ 台本は stdin から受け取る（PHPサーバから送信）
# =====================================================

import json
import sys
import smtplib
from email.mime.text import MIMEText
from email.header import Header

# =====================================================
# Blogger メール設定（y2blog.py と同一）
# =====================================================
CONFIG_FILE = __file__.replace("tts2blog.py", "blogger_config.json")

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    cfg = json.load(f)

FROM = cfg["FROM"]
PASSWORD = cfg["PASSWORD"]
TO = cfg["TO"]
SMTP_HOST = cfg["SMTP_HOST"]
SMTP_PORT = cfg["SMTP_PORT"]


AUDIO_BASE_URL = "https://exbridge.ddns.net/aidexx/tts"

# =====================================================
# 引数チェック
# =====================================================
if len(sys.argv) < 2:
    print("Usage: tts2blog.py <tts_file.wav>")
    sys.exit(1)

tts_file = sys.argv[1]

# =====================================================
# 台本取得（stdin）
# =====================================================
script = sys.stdin.read().strip()

if script == "":
    print("❌ script is empty")
    sys.exit(1)

# =====================================================
# Blogger 投稿処理
# =====================================================
def send_to_blogger(title, html_body):
    msg = MIMEText(html_body, "html", "utf-8")
    msg["Subject"] = Header("【AIラジオ】" + title, "utf-8")
    msg["From"] = FROM
    msg["To"] = TO

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as s:
        s.login(FROM, PASSWORD)
        s.send_message(msg)

    print("✅ Blogger投稿完了")

# =====================================================
# 投稿内容生成
# =====================================================
title = script[:50].replace("\n", "").strip()
audio_url = AUDIO_BASE_URL + "/" + tts_file

script_html = script.replace("\n", "<br>")

html_body = """
<p>
""" + script_html + """
</p>

<hr>

<p>
🔊 音声再生<br>
<a href=\"""" + audio_url + """\" target=\"_blank\">""" + audio_url + """</a>
</p>

<audio controls style="width:100%;">
  <source src=\"""" + audio_url + """\">
</audio>

<hr>

<p>
AI時代の技術と知識のまとめ - AIDexx<br>
<a href="https://exbridge.jp/aidexx/" target="_blank">
https://exbridge.jp/aidexx/
</a>
</p>
"""

# =====================================================
# 実行
# =====================================================
send_to_blogger(title, html_body)


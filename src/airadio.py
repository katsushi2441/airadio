#!/usr/bin/env python3
# =========================================
# airadio.py
# ニュース → ラジオ台本生成（Ollama）→ 音声生成（TTS API）
# CLI版 / PHP側ログAPI連携版
# =========================================

import sys
import json
import requests
import feedparser
from datetime import datetime
from pathlib import Path

# -------------------------
# 設定（airadio.php準拠）
# -------------------------
NEWS_RSS = "https://news.google.com/rss?hl=ja&gl=JP&ceid=JP:ja"
OLLAMA_URL = "https://exbridge.ddns.net/api/generate"
OLLAMA_MODEL = "gemma3:12b"
TTS_URL = "http://exbridge.ddns.net:8002/tts"

# ★ PHPサーバ（ttsfile.php）
LOG_API_URL = "https://exbridge.jp/aidexx/ttsfile.php"

NEWS_LIMIT = 8


# -------------------------
# ニュース取得
# -------------------------
def fetch_news(keyword):
    rss = NEWS_RSS
    if keyword:
        rss = (
            "https://news.google.com/rss/search?q="
            + requests.utils.quote(keyword)
            + "&hl=ja&gl=JP&ceid=JP:ja"
        )

    feed = feedparser.parse(rss)
    if feed.bozo:
        raise RuntimeError("RSS解析失敗")

    items = []
    for entry in feed.entries[:NEWS_LIMIT]:
        items.append({
            "title": entry.title,
            "link": entry.link,
            "pubDate": entry.get("published", "")
        })
    return items

# -------------------------
# プロンプト生成（PHP版と同一思想）
# -------------------------
def build_prompt(news_items,keyword):
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []
    i = 1
    for n in news_items:
        lines.append(f"{i}. {n['title']} ({n['pubDate']})")
        lines.append(f"   {n['link']}")
        i += 1
    news_text = "\n".join(lines)

    prompt = f"""
あなたはプロのラジオ構成作家です。
以下のニュース一覧を参考に、約5分番組用の
【実際にそのまま読み上げる日本語のセリフ本文】だけを作ってください。

# 今日の日時
{today}

# ニュース一覧（参考）
{news_text}

# 条件
- 尺は約5分。文字数の目安は1200〜1700文字。
- 口語で、聞き取りやすい短文を中心にする。
- 構成は「自然な導入 → 今日の注目トピック3本 → 小ネタ1本 → まとめ」の流れにする。
- ニュース内容は断定しすぎず、「〜と報じられています」「〜の可能性があります」など慎重な表現を使う。
- 一般の日本語話者に分かるよう、専門用語は噛み砕いて説明する。

# 出力形式に関する最重要ルール
- あなたは質問に答えたり、指示に返事をする存在ではない。
- これから出力する文章は「完成済みのラジオ原稿」であり、会話ではない。
- 読者や依頼者、指示内容に言及してはいけない。
- 出力の冒頭で、挨拶、返答、前置き、断り書き、確認文を一切書いてはいけない。

# 冒頭文に関する絶対ルール
- 冒頭に挨拶を入れてはいけない。
- 聞き手の感情や思考を推測する表現を書いてはいけない。
- 「お伝えします」「ご紹介します」など説明者視点の文を冒頭に使ってはいけない。
- 冒頭の一文は、番組のテーマを端的に示す事実ベースの文にすること。

# 出力に関する厳格な制限（最重要）
- 説明文、演出指示、ト書きは一切書かない。
- 「オープニング」「エンディング」「BGM」「SE」「パーソナリティ」などの語を使わない。
- 括弧（ ）やコロン「：」を使わない。
- 見出し、箇条書き、記号、強調表現を使わない。
- URLや注釈を書かない。
- 出力は【人がそのまま音声で読み上げるセリフ本文のみ】に限定する。

# 絶対禁止事項
- 「はい」「承知しました」「了解です」「わかりました」「以下が」「それでは」などの
  指示に対する返答・前置き・開始宣言を一切書いてはいけない。
- 「これから」「今回」「本日は」「ご紹介します」などのメタ的な導入表現を書いてはいけない。

# 開始条件（厳守）
- 出力は必ず、番組本文の最初のセリフから書き始めること。
- 先頭の一文は、すぐに内容に入る自然な日本語の文章にすること。
- 先頭の文字は必ず日本語の本文から始めること。

# 開始文（この一文から必ず書き始めること・改変禁止）
- {keyword}に関するニュースです。
"""

    return prompt

# -------------------------
# Ollama
# -------------------------
def ollama_generate(prompt):
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.7}
    }
    r = requests.post(OLLAMA_URL, json=payload, timeout=120)
    r.raise_for_status()
    return r.json()["response"].strip()

# -------------------------
# TTS
# -------------------------
def tts_generate(text):
    payload = {
        "text": text,
        "speaker": 2
    }
    r = requests.post(TTS_URL, json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()

    if "audio_url" in data:
        return data["audio_url"]
    if "url" in data:
        return data["url"]

    raise RuntimeError("TTS応答に audio_url がありません")

# -------------------------
# PHPサーバへログ送信（唯一の正本）
# -------------------------
def send_log_to_php(audio_url, keyword, script):
    payload = {
        "mode": "append_log",
        "audio_url": audio_url,
        "keyword": keyword,
        "script": script
    }
    r = requests.post(LOG_API_URL, json=payload, timeout=15)
    r.raise_for_status()

# -------------------------
# メイン
# -------------------------
def main():
    if len(sys.argv) < 2:
        print("使い方: python airadio.py キーワード")
        sys.exit(1)

    keyword = " ".join(sys.argv[1:])
    print("[INFO] keyword =", keyword)

    news = fetch_news(keyword)
    prompt = build_prompt(news,keyword)

    print("[INFO] generating script...")
    script = ollama_generate(prompt)

    print("[INFO] generating audio...")
    audio_url = tts_generate(script)

    print("[INFO] sending log to PHP server...")
    send_log_to_php(audio_url, keyword, script)

    print("\n=== 完了 ===")
    print("音声URL:", audio_url)

if __name__ == "__main__":
    main()


import sys
import os
import json
import re
from yt_dlp import YoutubeDL

def clean_vtt(vtt_text: str) -> str:
    lines = []
    for line in vtt_text.splitlines():
        if '-->' in line:
            continue
        if re.fullmatch(r'\d+', line.strip()):
            continue
        lines.append(line)
    text = '\n'.join(lines)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+\n', '\n', text)
    text = re.sub(r'\n{2,}', '\n\n', text)
    return text.strip()

def read_text_file(path: str) -> str:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return ""

def main():
    if len(sys.argv) < 3:
        print("Usage: python main.py <youtube_url> <output_json_path>")
        sys.exit(1)

    url = sys.argv[1].strip()
    out_json = sys.argv[2].strip()

    # 🔐 Reconstruction des cookies depuis les secrets GitHub (s'ils existent)
    cookie_parts = [os.getenv(f"COOKIES_PART_{i}") for i in range(1, 11)]
    cookie = ''.join([p for p in cookie_parts if p])
    cookies_file = os.environ.get("COOKIES_FILE", "").strip()

    if cookie:
        cookies_file = "cookies.txt"
        with open(cookies_file, "w", encoding="utf-8") as f:
            f.write(cookie)

    have_cookies = cookies_file and os.path.exists(cookies_file)

    tmp_dir = ".tmp_subs"
    os.makedirs(tmp_dir, exist_ok=True)

    ydl_opts = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitlesformat": "vtt",
        "subtitleslangs": ["fr", "fr.*", "en", "en.*", "live_chat"],
        "outtmpl": os.path.join(tmp_dir, "%(id)s.%(ext)s"),
        'cookiefile': 'cookies.txt',  # 👈 Indique à yt_dlp d’utiliser le fichier reconstitué

    }

    if have_cookies:
        ydl_opts["cookiefile"] = cookies_file

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    data = {
        "video_url": info.get("webpage_url") or url,
        "id": info.get("id"),
        "title": info.get("title"),
        "description": info.get("description"),
        "thumbnail": info.get("thumbnail") or info.get("thumbnails", [{}])[-1].get("url") if info.get("thumbnails") else None,
        "channel": info.get("channel"),
        "channel_id": info.get("channel_id"),
        "channel_url": info.get("channel_url"),
        "duration": info.get("duration"),
        "upload_date": info.get("upload_date"),
        "view_count": info.get("view_count"),
        "like_count": info.get("like_count"),
        "categories": info.get("categories"),
        "tags": info.get("tags"),
    }

    vtt_raw = ""
    chosen_path = ""
    candidates_order = []

    vid = data["id"] or "video"

    for lang in ["fr", "fr-FR", "fr-.*", "en", "en-US", "en-.*"]:
        candidates_order.append(os.path.join(tmp_dir, f"{vid}.{lang}.vtt"))

    for fname in os.listdir(tmp_dir):
        if fname.startswith(vid) and fname.endswith(".vtt"):
            candidates_order.append(os.path.join(tmp_dir, fname))

    for p in candidates_order:
        if os.path.exists(p):
            chosen_path = p
            break

    if chosen_path:
        vtt_raw = read_text_file(chosen_path)

    data["transcript_raw_srt"] = vtt_raw or None
    data["transcript_clean_text"] = clean_vtt(vtt_raw) if vtt_raw else None

    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Wrote JSON: {out_json}")

if __name__ == "__main__":
    main()



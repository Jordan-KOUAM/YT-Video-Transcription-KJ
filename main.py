import sys
import json
import re
import urllib.request
from yt_dlp import YoutubeDL

"""
Usage:
  python main.py <video_url> <output_json> [--cookies path/to/cookies.txt]

Sortie JSON (extrait):
{
  "video_url": "...",
  "title": "...",
  "description": "...",
  "thumbnail": "...",
  "metadata": { ... },
  "transcript": {
    "lang": "fr",
    "raw_srt": "..." | null,
    "clean_text": "..."
  }
}
"""

def pick_best_thumbnail(info):
    thumbs = info.get("thumbnails") or []
    if not thumbs and "thumbnail" in info:
        return info["thumbnail"]
    # prend la plus grande
    best = None
    best_area = -1
    for t in thumbs:
        w = t.get("width") or 0
        h = t.get("height") or 0
        a = w * h
        if a > best_area and t.get("url"):
            best = t["url"]
            best_area = a
    return best

def fetch_url(url: str) -> str:
    with urllib.request.urlopen(url) as r:
        return r.read().decode("utf-8", errors="replace")

def vtt_to_srt(vtt_text: str) -> str:
    # très simple conversion VTT -> SRT
    lines = vtt_text.splitlines()
    out = []
    idx = 1
    buf = []
    for line in lines:
        if line.strip().startswith("WEBVTT"):
            continue
        # convertir --> en --> (identique) mais VTT a . au lieu de , pour ms
        if "-->" in line:
            # "00:00:01.000 --> 00:00:02.000" -> "00:00:01,000 --> 00:00:02,000"
            line = re.sub(r"(\d{2}:\d{2}:\d{2})\.(\d{3})", r"\1,\2", line)
            if buf:
                out.append(str(idx))
                out.extend(buf)
                buf = []
                idx += 1
        if line.strip() == "":
            continue
        buf.append(line)
    if buf:
        out.append(str(idx))
        out.extend(buf)
    return "\n".join(out)

def srt_clean_text(srt_text: str) -> str:
    # enlève index, timestamps, balises, numéros…
    text_lines = []
    for line in srt_text.splitlines():
        if re.match(r"^\d+\s*$", line.strip()):
            continue
        if "-->" in line:
            continue
        # enlever balises HTML simples <i> <b> etc.
        line = re.sub(r"<[^>]+>", "", line)
        # enlever notes ({\an8}) style SSA/ASS
        line = re.sub(r"{\\.*?}", "", line)
        line = line.strip()
        if line:
            text_lines.append(line)
    # joindre et normaliser espaces
    text = " ".join(text_lines)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text

def choose_lang_track(tracks: dict, preferred=("fr","fr-FR","fr-FR.0","en","en-US","en-GB")):
    if not tracks:
        return None, None
    # tracks: {"fr":[{url:..., ext: vtt},{...}], "en":[...]}
    for lang in preferred:
        if lang in tracks and tracks[lang]:
            # préférer vtt puis srt
            # sinon première dispo
            cand = None
            for it in tracks[lang]:
                if it.get("ext") in ("vtt","webvtt","srv3","srt"):
                    cand = it
                    break
            if not cand:
                cand = tracks[lang][0]
            return lang, cand
    # fallback: première langue trouvée
    first_lang = next(iter(tracks.keys()))
    return first_lang, tracks[first_lang][0] if tracks[first_lang] else (None, None)

def download_caption_and_make_text(item) -> (str, str):
    """
    Télécharge la piste via URL, retourne (raw_srt, clean_text).
    Supporte vtt/srt/srv3 minimalement (srv3 traité comme vtt texte brut ici).
    """
    if not item or "url" not in item:
        return None, ""
    cap = fetch_url(item["url"])
    ext = (item.get("ext") or "").lower()
    if ext in ("srt",):
        raw = cap
    elif ext in ("vtt","webvtt","srv3","json3"):
        # convertir vtt→srt best effort
        raw = vtt_to_srt(cap)
    else:
        # inconnu, on garde brut
        raw = cap
    clean = srt_clean_text(raw)
    return raw, clean

def main():
    if len(sys.argv) < 3:
        print("Usage: python main.py <video_url> <output_json> [--cookies path/to/cookies.txt]")
        sys.exit(1)
    url = sys.argv[1]
    output_filename = sys.argv[2]
    cookies = None
    if len(sys.argv) >= 5 and sys.argv[3] == "--cookies":
        cookies = sys.argv[4]

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "noplaylist": True,
        "extract_flat": False,
        "writesubtitles": False,
        "writeautomaticsub": False,
        # On veut les liens des subs dans l'info (subtitles/automatic_captions)
        "subtitleslangs": ["fr","fr-FR","en","en-US","en-GB"],
    }
    if cookies:
        ydl_opts["cookiefile"] = cookies

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    # Métadonnées utiles
    title = info.get("title")
    description = info.get("description") or ""
    thumbnail = pick_best_thumbnail(info)
    duration = info.get("duration")
    upload_date = info.get("upload_date")
    channel = info.get("channel")
    channel_id = info.get("channel_id")
    view_count = info.get("view_count")
    like_count = info.get("like_count")

    # Sous-titres (priorité aux 'subtitles', sinon 'automatic_captions')
    lang, track = choose_lang_track(info.get("subtitles") or {})
    if not track:
        lang, track = choose_lang_track(info.get("automatic_captions") or {})

    raw_srt = None
    clean_text = ""
    if track:
        try:
            raw_srt, clean_text = download_caption_and_make_text(track)
        except Exception as e:
            raw_srt = None
            clean_text = ""

    out = {
        "video_url": url,
        "title": title,
        "description": description,
        "thumbnail": thumbnail,
        "metadata": {
            "duration": duration,
            "upload_date": upload_date,
            "channel": channel,
            "channel_id": channel_id,
            "view_count": view_count,
            "like_count": like_count,
            "id": info.get("id"),
            "webpage_url": info.get("webpage_url"),
        },
        "transcript": {
            "lang": lang,
            "raw_srt": raw_srt,        # colonne 1 (brute)
            "clean_text": clean_text    # colonne 2 (propre)
        }
    }

    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()

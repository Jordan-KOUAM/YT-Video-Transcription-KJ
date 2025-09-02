import sys
import os
import json
import re
from yt_dlp import YoutubeDL

def clean_vtt(vtt_text: str) -> str:
    # retire les horodatages + numéros + balises, garde seulement le texte
    # supprime les lignes avec --> (timestamps) et les numéros de séquence
    lines = []
    for line in vtt_text.splitlines():
        if '-->' in line:
            continue
        if re.fullmatch(r'\d+', line.strip()):
            continue
        lines.append(line)
    text = '\n'.join(lines)
    # enlever balises style <c> ou <i>
    text = re.sub(r'<[^>]+>', '', text)
    # compacter espaces
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

    url = sys.argv[1]
    out_json = sys.argv[2]
    cookies_file = os.environ.get("COOKIES_FILE", "").strip()
    have_cookies = cookies_file and os.path.exists(cookies_file)

    # Dossier temporaire pour sous-titres
    tmp_dir = ".tmp_subs"
    os.makedirs(tmp_dir, exist_ok=True)

    ydl_opts = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        # récupère sous-titres auto si dispos, en VTT
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitlesformat": "vtt",
        # priorité FR puis EN, sinon tout ce qui existe
        "subtitleslangs": ["fr", "fr.*", "en", "en.*", "live_chat"],
        # sauver les sous-titres dans tmp_dir
        "outtmpl": os.path.join(tmp_dir, "%(id)s.%(ext)s"),
    }

    if have_cookies:
        ydl_opts["cookiefile"] = cookies_file

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)  # download=True pour que les .vtt soient écrits

    # métadonnées utiles
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

    # Essayer de trouver un fichier .vtt dans tmp_dir (FR en priorité, puis EN, puis n'importe)
    vtt_raw = ""
    chosen_path = ""
    candidates_order = []

    vid = data["id"] or "video"
    # candidats typiques écrits par yt-dlp
    for lang in ["fr", "fr-FR", "fr-.*", "en", "en-US", "en-.*"]:
        candidates_order.append(os.path.join(tmp_dir, f"{vid}.{lang}.vtt"))
    # fallback: n’importe quel .vtt pour cette vidéo
    for fname in os.listdir(tmp_dir):
        if fname.startswith(vid) and fname.endswith(".vtt"):
            candidates_order.append(os.path.join(tmp_dir, fname))

    for p in candidates_order:
        if os.path.exists(p):
            chosen_path = p
            break

    if chosen_path:
        vtt_raw = read_text_file(chosen_path)

    # Deux colonnes: brut (VTT) + nettoyé
    data["transcript_raw_srt"] = vtt_raw or None
    data["transcript_clean_text"] = clean_vtt(vtt_raw) if vtt_raw else None

    # Sauver
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Wrote JSON: {out_json}")

if __name__ == "__main__":
    main()

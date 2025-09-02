import sys
import json
import os
import tempfile
import glob
import re

from yt_dlp import YoutubeDL

def read_vtt_as_srt_and_clean(vtt_path: str):
    """Retourne (raw_srt_like, clean_text) depuis un .vtt."""
    if not os.path.isfile(vtt_path):
        return "", ""

    with open(vtt_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.read().splitlines()

    raw_parts = []
    text_parts = []

    idx = 1
    cur_text_block = []

    ts_re = re.compile(r"\d{2}:\d{2}:\d{2}\.\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}\.\d{3}")
    for line in lines:
        # ignore entêtes STYLE/NOTE etc.
        if line.strip().upper().startswith(("WEBVTT", "STYLE", "NOTE", "REGION")):
            continue
        if "-->" in line and ts_re.search(line):
            # flush bloc précédent
            if cur_text_block:
                text = " ".join(cur_text_block).strip()
                if text:
                    text_parts.append(text)
                cur_text_block = []
            # démarre un nouveau bloc avec index + timestamp en SRT-like
            raw_parts.append(str(idx))
            raw_parts.append(line.replace(".", ","))  # SRT utilise la virgule
            idx += 1
        elif line.strip() == "":
            # fin de bloc -> flush
            if cur_text_block:
                text = " ".join(cur_text_block).strip()
                if text:
                    raw_parts.append(text)
                    text_parts.append(text)
                raw_parts.append("")  # ligne vide entre blocs
                cur_text_block = []
        else:
            # une ligne de texte
            cur_text_block.append(line)

    # flush final
    if cur_text_block:
        text = " ".join(cur_text_block).strip()
        if text:
            raw_parts.append(text)
            text_parts.append(text)

    raw_srt_like = "\n".join(raw_parts).strip()
    clean_text = " ".join(text_parts).strip()
    return raw_srt_like, clean_text


def pick_best_vtt(tmp_dir, video_id):
    """Essaie de trouver le meilleur .vtt pour la vidéo dans tmp_dir."""
    # exemples générés par yt-dlp: <id>.<lang>.vtt  (ex: abc123.en.vtt / abc123.fr.vtt)
    patterns = [
        f"{video_id}.fr.vtt",
        f"{video_id}.fr-FR.vtt",
        f"{video_id}.en.vtt",
        f"{video_id}.en-US.vtt",
        f"{video_id}.en-GB.vtt",
        f"{video_id}.*.vtt",
        f"{video_id}.vtt",
    ]
    for pat in patterns:
        found = glob.glob(os.path.join(tmp_dir, pat))
        if found:
            return found[0]
    return None


def main():
    if len(sys.argv) < 3:
        print("Usage: python main.py <youtube_url> <output_json_path>")
        sys.exit(1)

    url = sys.argv[1]
    output_filename = sys.argv[2]

    with tempfile.TemporaryDirectory() as tmpd:
        ydl_opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["fr", "fr-FR", "en", "en-US", "en-GB"],
            "subtitlesformat": "vtt",
            "outtmpl": os.path.join(tmpd, "%(id)s.%(ext)s"),
            "quiet": True,
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)  # download=True pour récupérer les .vtt

        # Compose nos champs utiles
        video_id = info.get("id")
        title = info.get("title")
        description = info.get("description")
        uploader = info.get("uploader")
        uploader_id = info.get("uploader_id")
        channel = info.get("channel")
        channel_id = info.get("channel_id")
        duration = info.get("duration")
        upload_date = info.get("upload_date")
        view_count = info.get("view_count")
        like_count = info.get("like_count")
        thumbnails = info.get("thumbnails") or []
        # miniature “par défaut”
        thumb = None
        if thumbnails:
            # on prend la dernière (souvent la plus grande)
            thumb = thumbnails[-1].get("url") or thumbnails[0].get("url")

        # détection du meilleur .vtt
        vtt_path = pick_best_vtt(tmpd, video_id) if video_id else None
        raw_srt, clean_text = ("", "")
        if vtt_path:
            raw_srt, clean_text = read_vtt_as_srt_and_clean(vtt_path)

        result = {
            "video_url": url,
            "video_id": video_id,
            "title": title,
            "description": description,
            "thumbnail_url": thumb,
            "uploader": uploader,
            "uploader_id": uploader_id,
            "channel": channel,
            "channel_id": channel_id,
            "duration": duration,
            "upload_date": upload_date,
            "view_count": view_count,
            "like_count": like_count,
            # transcript
            "transcript_raw_srt": raw_srt or None,
            "transcript_clean_text": clean_text or None,
            # métadonnées brutes (utile si tu veux tout)
            "_meta": {
                "original_info": info,
            },
        }

        os.makedirs(os.path.dirname(output_filename), exist_ok=True)
        with open(output_filename, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()

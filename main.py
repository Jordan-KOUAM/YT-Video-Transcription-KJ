import os, re, json, sys, base64, tempfile, shutil, datetime
from pathlib import Path
from yt_dlp import YoutubeDL

URL = sys.argv[1]
OUTFILE = sys.argv[2] if len(sys.argv) > 2 else "outputs/out.json"

# --- helpers ---
def slugify_url(u: str) -> str:
    return re.sub(r'[^a-zA-Z0-9]+', '_', u).strip('_')

def read_file_text(p: Path) -> str:
    try:
        return p.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return ""

def srt_to_clean_text(srt: str) -> str:
    # retire numéros + timecodes + balises
    lines = []
    for line in srt.splitlines():
        if re.match(r'^\s*\d+\s*$', line):  # index
            continue
        if re.search(r'\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}', line):
            continue
        line = re.sub(r'<[^>]+>', '', line)     # tags html
        line = re.sub(r'\s+', ' ', line).strip()
        if line:
            lines.append(line)
    # fusionne proprement
    text = ' '.join(lines)
    # supprime répétitions banales
    text = re.sub(r'(.\s*)\1{2,}', r'\1', text)
    return text

def best_thumbnail(info: dict) -> str:
    if info.get("thumbnail"):
        return info["thumbnail"]
    vid = info.get("id")
    if vid:
        # maxres → fallback hq
        return f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg"
    return None

# --- cookies optionnels depuis variable d'environnement (secrets) ---
cookies_path = None
if os.getenv("COOKIES_B64"):
    tmpdir = tempfile.mkdtemp()
    cookies_path = os.path.join(tmpdir, "cookies.txt")
    with open(cookies_path, "wb") as f:
        f.write(base64.b64decode(os.environ["COOKIES_B64"]))

# --- répertoire de travail pour sous-titres ---
workdir = Path(tempfile.mkdtemp())
subs_dir = workdir / "subs"
subs_dir.mkdir(parents=True, exist_ok=True)

# fichiers srt attendus
outtmpl = str(subs_dir / "%(id)s.%(ext)s")

ydl_opts = {
    "skip_download": True,
    "quiet": True,
    "nocheckcertificate": True,
    "outtmpl": outtmpl,
    # sous-titres
    "writesubtitles": True,
    "writeautomaticsub": True,
    "subtitlesformat": "srt",
    "subtitleslangs": ["fr", "fr.*,live_chat", "en", "en.*", "de", "es", "*"],
}

if cookies_path:
    ydl_opts["cookiefile"] = cookies_path

# 1) Extraire les métadonnées
with YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(URL, download=False)

# 2) Télécharger UNIQUEMENT les sous-titres (skip_download True)
#    (en API, il faut quand même appeler download pour que yt-dlp écrive les .srt)
with YoutubeDL(ydl_opts) as ydl:
    ydl.download([URL])

# 3) Chercher le .srt écrit
video_id = info.get("id")
raw_srt_text = ""
clean_text = ""
srt_lang = None

if video_id:
    # trouve le premier .srt correspondant
    srt_files = sorted(subs_dir.glob(f"{video_id}*.srt"))
    if srt_files:
        srt_path = srt_files[0]
        raw_srt_text = read_file_text(srt_path)
        clean_text = srt_to_clean_text(raw_srt_text)
        # langue approximative dans le nom
        m = re.search(rf"{re.escape(video_id)}\.([^.]+)\.srt$", srt_path.name)
        if m:
            srt_lang = m.group(1)

# 4) Construire le JSON final
payload = {
    "videoUrl": URL,
    "id": info.get("id"),
    "title": info.get("title"),
    "description": info.get("description"),
    "channel": info.get("channel") or info.get("uploader"),
    "channel_id": info.get("channel_id") or info.get("uploader_id"),
    "duration": info.get("duration"),
    "viewCount": info.get("view_count"),
    "uploadDate": info.get("upload_date"),
    "thumbnailUrl": best_thumbnail(info),
    "subtitle": {
        "lang": srt_lang,
        "raw_srt": raw_srt_text or None,
        "clean_text": clean_text or None,
        "has_subtitles": bool(raw_srt_text),
    },
    "dump": info,  # full dump en secours
    "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
}

# 5) Écriture du JSON de sortie
Path(OUTFILE).parent.mkdir(parents=True, exist_ok=True)
with open(OUTFILE, "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)

# 6) Nettoyage
if cookies_path:
    shutil.rmtree(Path(cookies_path).parent, ignore_errors=True)
shutil.rmtree(workdir, ignore_errors=True)

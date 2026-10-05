"""Retro konsol kartındaki (R36S vb., EmulationStation) oyunları resimleriyle gösterip ayıklamak için yerel sunucu.

Kullanım:  python sunucu.py [OYUN_KLASORU]  ->  http://127.0.0.1:8736
(klasör verilmezse son seçilen, o da yoksa takılı kartlardan ilki; arayüzdeki "Klasör seç" ile değiştirilir)

Silme kalıcı değildir: oyun, aynı adlı yan dosyaları (.srm, .state...) ve resmi/videosu
kartta KART\\_cop\\<sistem>\\... altına taşınır. Geri alınabilir, "Çöpü boşalt" ile kalıcı silinir.
gamelist.xml'e dokunulmaz; EmulationStation dosyası olmayan kaydı zaten atlar.
"""
import difflib
import json
import os
import re
import shutil
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET
import zipfile
import zlib
from collections import Counter, defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse
from urllib.request import Request, urlopen

PAKET = getattr(sys, "frozen", False)  # PyInstaller ile tek dosya .exe
BURASI = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
WINDOWS = os.name == "nt"
MAC = sys.platform == "darwin"


def veri_klasoru() -> Path:
    """Uygulama verisi (işaretler, önbellekler, son seçilen klasör): kaynak koddan çalışırken deponun kökündeki
    veri/, .exe'de exe'nin yanındaki veri/; oraya yazılamıyorsa (Program Files vb.) kullanıcı klasörü."""
    if os.environ.get("OYUN_VERI"):
        return Path(os.environ["OYUN_VERI"])
    aday = (Path(sys.executable).resolve().parent if PAKET else BURASI.parent) / "veri"
    try:
        aday.mkdir(parents=True, exist_ok=True)
        (aday / ".yazilabilir").touch()
        return aday
    except OSError:
        return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "ROM Sorter"


VERI = veri_klasoru()
VERI.mkdir(parents=True, exist_ok=True)
SECILMEDI = "(?)"  # klasör henüz seçilmedi: var olmayan bir yol, arayüz seçiciyi açar
VARSAYILAN_KOK = os.environ.get("OYUN_KOK", SECILMEDI)
AYAR_DOSYASI = VERI / "ayarlar.json"
# Oyun klasörü: komut satırı > son seçilen (ayarlar.json) > OYUN_KOK > takılı kartlardan ilki (bkz. __main__).
KOK = Path(sys.argv[1] if len(sys.argv) > 1
           else json.loads(AYAR_DOSYASI.read_text(encoding="utf-8")).get("kok", VARSAYILAN_KOK) if AYAR_DOSYASI.is_file()
           else VARSAYILAN_KOK)
if KOK.is_dir():  # kısa (8.3) ve uzun yol karışmasın: tüm yollar tek biçimde
    KOK = KOK.resolve()
COP = KOK / "_cop"
KAYIT = COP / "_kayit.json"
ISARET_DOSYASI = VERI / "isaretler.json"
HOST = os.environ.get("OYUN_HOST", "127.0.0.1")
PORT = int(os.environ.get("OYUN_PORT", 8736))

SISTEM_DISI = {
    "_cop", "bgm", "bgmusic", "bezels", "bios", "cheats", "launchimages", "tools", "backup",
    "build", "system volume information", "ports", "pico-8", "themes", "screenshots",
}
KLASOR_DISI = {
    "downloaded_images", "downloaded_videos", "media", "images", "snap", "boxart", "videos",
    "manuals", "ppsspp", "flycast", "jdk", "nestopia", "nvram", "cfg", "hi", "diff", "inp",
    "memcard", "saves", "states", "savestates",
}
ROM_UZANTI = {
    "zip", "7z", "nes", "fds", "unf", "gb", "gbc", "gba", "smc", "sfc", "fig", "swc", "n64",
    "z64", "v64", "md", "gen", "smd", "bin", "sms", "gg", "sg", "32x", "pce", "ngp", "ngc",
    "ws", "wsc", "pbp", "cso", "iso", "chd", "cue", "m3u", "gdi", "cdi", "nds", "a26", "a52",
    "a78", "lnx", "col", "rom", "mx1", "mx2", "dsk", "j64", "jag", "vec", "int", "adf", "d64",
    "t64", "tap", "crt", "st", "msa", "cpc", "svm", "p8", "jar", "sc", "ri",
}
RESIM_UZANTI = (".png", ".jpg", ".jpeg", ".webp", ".gif")
RESIM_KLASOR = ["downloaded_images", "media/images", "media/box2dfront", "media/screenshots",
                "images", "boxart", "snap"]
VIDEO_KLASOR = ["downloaded_videos", "media/videos", "videos"]
RESIM_EKLERI = ("-image", "-thumb", "-boxart", "-snap", "-screenshot", "-marquee")

LIBRETRO = "https://thumbnails.libretro.com"
LIBRETRO_TURLER = {"Named_Boxarts": "Kapak", "Named_Snaps": "Ekran", "Named_Titles": "Başlık"}
LIBRETRO_SISTEM = {
    "nes": ["Nintendo - Nintendo Entertainment System"],
    "famicom": ["Nintendo - Nintendo Entertainment System"],
    "fds": ["Nintendo - Family Computer Disk System"],
    "snes": ["Nintendo - Super Nintendo Entertainment System"],
    "sfc": ["Nintendo - Super Nintendo Entertainment System"],
    "gb": ["Nintendo - Game Boy"],
    "gbc": ["Nintendo - Game Boy Color"],
    "gba": ["Nintendo - Game Boy Advance"],
    "n64": ["Nintendo - Nintendo 64"],
    "nds": ["Nintendo - Nintendo DS"],
    "megadrive": ["Sega - Mega Drive - Genesis"],
    "gamegear": ["Sega - Game Gear"],
    "sega32x": ["Sega - 32X"],
    "sg-1000": ["Sega - SG-1000"],
    "dreamcast": ["Sega - Dreamcast"],
    "pcengine": ["NEC - PC Engine - TurboGrafx 16"],
    "ngp": ["SNK - Neo Geo Pocket", "SNK - Neo Geo Pocket Color"],
    "wonderswancolor": ["Bandai - WonderSwan Color"],
    "atari2600": ["Atari - 2600"],
    "psx": ["Sony - PlayStation"],
    "psp": ["Sony - PlayStation Portable"],
    "msx2": ["Microsoft - MSX2"],
    "gameandwatch": ["Handheld Electronic Game"],
    "neogeo": ["SNK - Neo Geo", "FBNeo - Arcade Games"],
    **{s: ["MAME", "FBNeo - Arcade Games"] for s in ("mame", "mame2003", "cps1", "cps2", "cps3")},
}
LIBRETRO_ONBELLEK = VERI / "libretro_onbellek"

kilit = threading.Lock()
onbellek: dict[str, dict] = {}  # sistem -> {id: oyun}
dizin_kilitleri: dict[str, threading.Lock] = {}
libretro_dizin: dict[str, dict[str, list[str]]] = {}  # "Sistem/Tür" -> {norm ad: [dosya adları]}


def json_oku(yol: Path, varsayilan):
    try:
        return json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return varsayilan


def json_yaz(yol: Path, veri):
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(".tmp")
    gecici.write_text(json.dumps(veri, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(gecici, yol)


def sade(ad: str) -> str:
    ad = ad.lower()
    for ek in RESIM_EKLERI:
        if ad.endswith(ek):
            return ad[: -len(ek)]
    return ad


def norm(ad: str) -> str:
    """Bölge/sürüm etiketlerini ve baştaki sıra numarasını atıp karşılaştırma anahtarı üretir."""
    ad = re.sub(r"[\(\[].*?[\)\]]", "", sade(ad))
    ad = re.sub(r"^\d{1,4}[\s._-]+", "", ad.strip())
    ad = re.sub(r"^the\s+|,\s*the$", "", ad.strip())
    ad = re.sub(r"\b(ii|iii|iv|vi|vii|viii)\b", lambda m: ROMA[m.group(1)], ad)
    return re.sub(r"[^a-z0-9]", "", ad)


ROMA = {"ii": "2", "iii": "3", "iv": "4", "vi": "6", "vii": "7", "viii": "8"}


genel_resim: dict[str, Path] | None = None


def genel_resimler() -> dict[str, Path]:
    """Tüm karttaki resimler, sadeleşmiş ada göre (başka sistemdeki aynı oyun için yedek)."""
    global genel_resim
    if genel_resim is None:
        genel_resim = {}
        for s in sistemler():
            for k, p in medya_dizini(KOK / s, RESIM_KLASOR, RESIM_UZANTI).items():
                if norm(k):
                    genel_resim.setdefault(norm(k), p)
    return genel_resim


def medya_dizini(sistem_yol: Path, klasorler, uzantilar) -> dict[str, Path]:
    """Sistem altındaki resim/video klasörlerinde sade(dosya kökü) -> yol."""
    dizin: dict[str, Path] = {}
    for k in klasorler:
        d = sistem_yol / k
        if not d.is_dir():
            continue
        for kok, _, dosyalar in os.walk(d):
            if "folders" in Path(kok).parts:
                continue
            for f in dosyalar:
                p = Path(kok) / f
                if p.suffix.lower() in uzantilar:
                    dizin.setdefault(sade(p.stem), p)
    return dizin


def gamelist_oku(sistem_yol: Path) -> dict[str, dict]:
    gl = sistem_yol / "gamelist.xml"
    if not gl.is_file():
        return {}
    try:
        agac = ET.parse(gl)
    except ET.ParseError:
        return {}
    sonuc = {}
    for g in agac.getroot().iter("game"):
        yol = (g.findtext("path") or "").strip()
        if not yol:
            continue
        rel = os.path.normpath(yol.removeprefix("./")).replace("\\", "/")
        sonuc[rel.lower()] = {e.tag: (e.text or "").strip() for e in g}
    return sonuc


def medya_yolu(sistem_yol: Path, deger: str) -> Path | None:
    if not deger:
        return None
    p = (sistem_yol / deger.removeprefix("./")).resolve()
    return p if p.is_file() and str(p).startswith(str(KOK.resolve())) else None


def sistem_tara(sistem: str) -> dict:
    sistem_yol = KOK / sistem
    gl = gamelist_oku(sistem_yol)
    resimler = medya_dizini(sistem_yol, RESIM_KLASOR, RESIM_UZANTI)
    resim_norm = {}
    for k, p in resimler.items():
        if norm(k):
            resim_norm.setdefault(norm(k), p)
    genel = genel_resimler()
    videolar = medya_dizini(sistem_yol, VIDEO_KLASOR, (".mp4", ".mkv", ".avi"))
    oyunlar = {}
    for kok, klasorler, dosyalar in os.walk(sistem_yol):
        klasorler[:] = [k for k in klasorler if k.lower() not in KLASOR_DISI and not k.startswith(".")]
        for f in dosyalar:
            p = Path(kok) / f
            rel = p.relative_to(sistem_yol).as_posix()
            bilgi = gl.get(rel.lower())
            if bilgi is None and p.suffix.lower().lstrip(".") not in ROM_UZANTI:
                continue
            if f.lower() == "gamelist.xml":
                continue
            bilgi = bilgi or {}
            resim = (medya_yolu(sistem_yol, bilgi.get("image", ""))
                     or medya_yolu(sistem_yol, bilgi.get("thumbnail", ""))
                     or resimler.get(sade(p.stem))
                     or resim_norm.get(norm(p.stem)) or resim_norm.get(norm(bilgi.get("name", "")))
                     or genel.get(norm(p.stem)) or genel.get(norm(bilgi.get("name", ""))))
            video = medya_yolu(sistem_yol, bilgi.get("video", "")) or videolar.get(sade(p.stem))
            try:
                boyut = p.stat().st_size
            except OSError:
                boyut = 0
            puan = bilgi.get("rating")
            oyunlar[rel] = {
                "id": rel,
                "ad": bilgi.get("name") or p.stem,
                "dosya": f,
                "klasor": str(Path(rel).parent.as_posix()) if "/" in rel else "",
                "boyut": boyut,
                "puan": float(puan) or None if puan not in (None, "") else None,  # ScreenScraper: 0 = puansız
                "yil": (bilgi.get("releasedate") or "")[:4],
                "tur": bilgi.get("genre", ""),
                "gelistirici": bilgi.get("developer", ""),
                "oyuncu": bilgi.get("players", ""),
                "oynama": int(bilgi.get("playcount") or 0),
                "aciklama": bilgi.get("desc", ""),
                "_resim": str(resim) if resim else None,
                "_video": str(video) if video else None,
            }
    # Bazı gamelist'ler puanı 0–1 yerine 0–10 yazıyor; sistemde 1'i aşan varsa hepsi 10 üzerinden.
    if any((o["puan"] or 0) > 1 for o in oyunlar.values()):
        for o in oyunlar.values():
            if o["puan"] is not None:
                o["puan"] /= 10
    return oyunlar


def sistem_oyunlari(sistem: str) -> dict:
    with kilit:
        if sistem not in onbellek:
            onbellek[sistem] = sistem_tara(sistem)
        return onbellek[sistem]


BILINEN_SISTEM = {
    "nes", "snes", "sfc", "famicom", "gb", "gbc", "gba", "n64", "nds", "megadrive", "genesis",
    "mastersystem", "gamegear", "psx", "psp", "dreamcast", "mame", "mame2003", "fbneo", "neogeo",
    "pcengine", "atari2600", "cps1", "cps2", "arcade", "segacd", "sega32x", "ngp", "wonderswancolor",
}


def kok_degistir(yol: str) -> Path:
    global KOK, COP, KAYIT, genel_resim
    yeni = Path(yol.strip().strip('"'))
    if not yeni.is_dir():
        raise OSError(f"Klasör bulunamadı: {yeni}")
    yeni = yeni.resolve()
    with kilit:
        KOK, COP = yeni, yeni / "_cop"
        KAYIT = COP / "_kayit.json"
        onbellek.clear()
        genel_resim = None
    json_yaz(AYAR_DOSYASI, {"kok": str(KOK)})
    return KOK


def aday_klasorler() -> list[dict]:
    """Yerel/çıkarılabilir disklerde (ağ ve CD hariç) oyun kartına benzeyen klasörler."""
    if not WINDOWS:  # macOS/Linux: takılı birimler
        sonuc, gorulen = [], set()
        kullanici = os.environ.get("USER", "")
        for taban in (Path("/Volumes"), Path("/media") / kullanici, Path("/run/media") / kullanici,
                      Path("/media"), Path("/mnt")):
            try:
                birimler = sorted(d for d in taban.iterdir() if d.is_dir())
            except OSError:
                continue
            for birim in birimler:
                for aday in (birim, birim / "roms", birim / "ROMS"):
                    try:
                        ortak = {d.name.lower() for d in aday.iterdir() if d.is_dir()} & BILINEN_SISTEM
                    except OSError:
                        continue
                    if len(ortak) >= 3 and str(aday) not in gorulen:
                        gorulen.add(str(aday))
                        sonuc.append({"yol": str(aday), "sistem": len(ortak), "cikarilabilir": True})
                        break
        return sonuc
    import ctypes
    sonuc = []
    for harf in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        kok = f"{harf}:\\"
        if ctypes.windll.kernel32.GetDriveTypeW(kok) not in (2, 3):  # 2 çıkarılabilir, 3 sabit disk
            continue
        for aday in (Path(kok), Path(kok) / "roms", Path(kok) / "ROMS"):
            try:
                adlar = {d.name.lower() for d in aday.iterdir() if d.is_dir()}
            except OSError:
                continue
            ortak = adlar & BILINEN_SISTEM
            if len(ortak) >= 3:
                sonuc.append({"yol": str(aday), "sistem": len(ortak),
                              "cikarilabilir": ctypes.windll.kernel32.GetDriveTypeW(kok) == 2})
                break
    return sonuc


def klasor_gozat() -> str | None:
    """İşletim sisteminin klasör seçme penceresini açar (uygulama bu bilgisayarda çalıştığı için pencere burada çıkar)."""
    import subprocess
    if MAC:
        r = subprocess.run(["osascript", "-e", 'POSIX path of (choose folder with prompt "ROM folder")'],
                           capture_output=True, timeout=600, encoding="utf-8")
        return r.stdout.strip() or None
    if not WINDOWS:  # Linux: zenity ya da kdialog varsa; yoksa yol elle yazılır
        for komut in (["zenity", "--file-selection", "--directory"], ["kdialog", "--getexistingdirectory"]):
            if shutil.which(komut[0]):
                r = subprocess.run(komut, capture_output=True, timeout=600, encoding="utf-8")
                return r.stdout.strip() or None
        return None
    betik = (
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$d=New-Object System.Windows.Forms.FolderBrowserDialog;"
        "$d.Description='ROM folder (contains nes, snes, gba... folders)';"
        f"$d.SelectedPath='{str(KOK).replace(chr(39), chr(39) * 2)}';"
        "$f=New-Object System.Windows.Forms.Form -Property @{TopMost=$true};"
        "if($d.ShowDialog($f) -eq 'OK'){$d.SelectedPath}"
    )
    r = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", betik],
                       capture_output=True, timeout=600, encoding="utf-8")
    return r.stdout.strip() or None


def sistemler() -> list[str]:
    return sorted(
        d.name for d in KOK.iterdir()
        if d.is_dir() and d.name.lower() not in SISTEM_DISI and not d.name.startswith(".")
    )


def libretro_listesi(lsistem: str, tur: str) -> dict[str, list[str]]:
    """libretro sunucusundaki bir klasörün dosya listesi, sadeleşmiş ada göre gruplu (30 gün diskte saklanır)."""
    anahtar = f"{lsistem}/{tur}"
    with kilit:
        kl = dizin_kilitleri.setdefault(anahtar, threading.Lock())
    with kl:
        if anahtar in libretro_dizin:
            return libretro_dizin[anahtar]
        dosya = LIBRETRO_ONBELLEK / (re.sub(r"[^\w-]+", "_", anahtar) + ".json")
        if dosya.is_file() and time.time() - dosya.stat().st_mtime < 30 * 86400:
            adlar = json_oku(dosya, [])
        else:
            url = f"{LIBRETRO}/{quote(lsistem)}/{tur}/"
            html = urlopen(Request(url, headers={"User-Agent": "oyun-ayikla"}), timeout=60).read().decode("utf-8", "replace")
            adlar = [unquote(h) for h in re.findall(r'href="([^"?/][^"]*\.png)"', html)]
            json_yaz(dosya, adlar)
        gruplu: dict[str, list[str]] = {}
        for ad in adlar:
            gruplu.setdefault(norm(ad[:-4]), []).append(ad)
        libretro_dizin[anahtar] = gruplu
        return gruplu


def internet_resimleri(sistem: str, oyun_id: str) -> dict:
    o = sistem_oyunlari(sistem).get(oyun_id)
    if not o:
        return {"resimler": [], "hatalar": ["oyun bulunamadı"]}
    arananlar = [a for a in {norm(Path(o["dosya"]).stem), norm(o["ad"])} if len(a) >= 3]
    resimler, hatalar = [], []
    for lsistem in LIBRETRO_SISTEM.get(sistem, []):
        for tur, etiket in LIBRETRO_TURLER.items():
            try:
                gruplu = libretro_listesi(lsistem, tur)
            except OSError as e:
                hatalar.append(f"{lsistem}/{etiket}: {e}")
                continue
            bulunan = [ad for a in arananlar for ad in gruplu.get(a, [])]
            if not bulunan:  # tam eşleşme yoksa: aranan adla başlayanlar (ör. alt başlıklı sürümler)
                bulunan = [ad for a in arananlar if len(a) >= 5 for k, l in gruplu.items() if k.startswith(a) for ad in l]
            benzer = not bulunan
            if benzer:  # o da yoksa benzer adlar (çevrilmiş/kısaltılmış adlar için), "≈" ile işaretlenir
                bulunan = [ad for a in arananlar if len(a) >= 5
                           for k in difflib.get_close_matches(a, gruplu.keys(), n=2, cutoff=0.8) for ad in gruplu[k]]
            # Temiz No-Intro adları önce; [h] hack, [b] bozuk döküm gibi etiketliler sona.
            bulunan = sorted(dict.fromkeys(bulunan), key=lambda a: (
                a.count("["), not re.search(r"\((USA|World|Europe|Japan)", a), len(a)))
            for ad in bulunan[:6]:
                resimler.append({"tur": etiket, "kaynak": lsistem, "ad": ad[:-4], "benzer": benzer,
                                 "url": f"{LIBRETRO}/{quote(lsistem)}/{tur}/{quote(ad)}"})
    return {"resimler": resimler, "hatalar": hatalar, "desteklenmiyor": sistem not in LIBRETRO_SISTEM}


TUR_ONCELIK = {"Kapak": 0, "Ekran": 1, "Başlık": 2}
gamelist_kilitleri: dict[str, threading.Lock] = {}
toplu_durum: dict = {"calisiyor": False}


def resim_indir(url: str, hedef: Path):
    """libretro resmini indirir, konsol ekranına (640×480) sığacak şekilde küçültüp JPG kaydeder (~40 KB)."""
    from io import BytesIO
    from PIL import Image
    veri = urlopen(Request(url, headers={"User-Agent": "oyun-ayikla"}), timeout=60).read()
    im = Image.open(BytesIO(veri))
    im.thumbnail((640, 480))
    if im.mode != "RGB":  # saydam kısımlar siyah zemine
        im = im.convert("RGBA")
        zemin = Image.new("RGB", im.size, (0, 0, 0))
        zemin.paste(im, mask=im.getchannel("A"))
        im = zemin
    hedef.parent.mkdir(parents=True, exist_ok=True)
    im.save(hedef, "JPEG", quality=88, optimize=True)


def gamelist_resim_yaz(sistem: str, resimler: dict[str, Path]):
    """{oyun id: resim yolu} -> gamelist.xml'de <image> yazar."""
    sistem_yol = KOK / sistem
    gamelist_guncelle(sistem, {i: {"image": "./" + r.relative_to(sistem_yol).as_posix()} for i, r in resimler.items()})
    oyun_haritasi = sistem_oyunlari(sistem)
    for oyun_id, resim in resimler.items():
        if oyun_id in oyun_haritasi:
            oyun_haritasi[oyun_id]["_resim"] = str(resim)


def gamelist_guncelle(sistem: str, degisiklikler: dict[str, dict[str, str]]):
    """{oyun id: {etiket: değer}} -> gamelist.xml'e yazar; kaydı olmayan oyuna kayıt ekler. Önce yedek alır."""
    sistem_yol = KOK / sistem
    gl = sistem_yol / "gamelist.xml"
    with kilit:
        kl = gamelist_kilitleri.setdefault(sistem, threading.Lock())
    with kl:
        if gl.is_file():
            shutil.copy2(gl, gl.with_name(f"gamelist.xml.yedek-{time.strftime('%Y%m%d-%H%M%S')}"))
            agac = ET.parse(gl)
        else:
            agac = ET.ElementTree(ET.Element("gameList"))
        kok = agac.getroot()
        oyunlar = {os.path.normpath((g.findtext("path") or "").strip().removeprefix("./")).replace("\\", "/").lower(): g
                   for g in kok.iter("game")}
        for oyun_id, alanlar in degisiklikler.items():
            g = oyunlar.get(oyun_id.lower())
            if g is None:
                g = ET.SubElement(kok, "game")
                ET.SubElement(g, "path").text = "./" + oyun_id
                ET.SubElement(g, "name").text = Path(oyun_id).stem
            for etiket, deger in alanlar.items():
                el = g.find(etiket)
                if el is None:
                    el = ET.SubElement(g, etiket)
                el.text = deger
        ET.indent(agac, "\t")
        gecici = gl.with_suffix(".tmp")
        agac.write(gecici, encoding="utf-8", xml_declaration=True)
        os.replace(gecici, gl)


def resim_hedefi(sistem: str, oyun_id: str, ayrilan: set | None = None) -> Path:
    rel = Path(oyun_id)
    hedef = KOK / sistem / "downloaded_images" / rel.parent / (rel.stem + ".jpg")
    n = 2
    while hedef.exists() or (ayrilan is not None and hedef in ayrilan):
        hedef = hedef.with_name(f"{rel.stem}-{n}.jpg")
        n += 1
    return hedef


def resim_kaydet(sistem: str, oyun_id: str, url: str) -> dict:
    """Büyüteçte seçilen resmi karta kaydeder (varsa eski resmin yerine gamelist'te bu geçer)."""
    if not url.startswith(LIBRETRO + "/"):
        raise OSError("Yalnızca libretro-thumbnails adresleri kabul edilir")
    if oyun_id not in sistem_oyunlari(sistem):
        raise OSError("Oyun bulunamadı")
    hedef = resim_hedefi(sistem, oyun_id)
    resim_indir(url, hedef)
    gamelist_resim_yaz(sistem, {oyun_id: hedef})
    return {"resim": str(hedef)}


def toplu_resim(sistemler_: list[str]):
    """Resmi olmayan oyunlara tam eşleşen libretro resmini indirir (kapak > ekran > başlık)."""
    from concurrent.futures import ThreadPoolExecutor
    d = toplu_durum
    d.update(calisiyor=True, asama="Eksikler sayılıyor", toplam=0, bakilan=0, kaydedilen=0,
             bulunamayan=0, hatalar=[], sistem="", baslangic=time.time())
    try:
        isler = [(s, i) for s in sistemler_ for i, o in sistem_oyunlari(s).items() if not o["_resim"]]
        d["toplam"] = len(isler)
        for s in sistemler_:
            d.update(sistem=s, asama="İnternette aranıyor")
            kendi = [i for ss, i in isler if ss == s]
            secilen: dict[str, str] = {}
            for i in kendi:
                r = [x for x in internet_resimleri(s, i)["resimler"] if not x["benzer"]]
                r.sort(key=lambda x: TUR_ONCELIK[x["tur"]])
                if r:
                    secilen[i] = r[0]["url"]
                else:
                    d["bulunamayan"] += 1
                    d["bakilan"] += 1
            if not secilen:
                continue
            d["asama"] = "İndiriliyor"
            kaydedilen: dict[str, Path] = {}
            ayrilan: set[Path] = set()
            hedefler = {}
            for i in secilen:  # aynı adlı iki oyun aynı dosyayı kapmasın diye adlar önce sırayla ayrılır
                hedefler[i] = resim_hedefi(s, i, ayrilan)
                ayrilan.add(hedefler[i])

            def indir(i):
                hedef = hedefler[i]
                try:
                    resim_indir(secilen[i], hedef)
                    kaydedilen[i] = hedef
                    d["kaydedilen"] += 1
                except Exception as e:  # noqa: BLE001 — tek resmin hatası işi durdurmasın
                    d["hatalar"].append(f"{s}/{i}: {e}")
                finally:
                    d["bakilan"] += 1

            with ThreadPoolExecutor(8) as havuz:
                list(havuz.map(indir, secilen))
            if kaydedilen:
                d["asama"] = "gamelist.xml yazılıyor"
                try:
                    gamelist_resim_yaz(s, kaydedilen)
                except (OSError, ET.ParseError) as e:
                    d["hatalar"].append(f"{s}/gamelist.xml: {e}")
        d["asama"] = "Bitti"
    except Exception as e:  # noqa: BLE001
        d["hatalar"].append(str(e))
        d["asama"] = "Hata"
    finally:
        d["calisiyor"] = False


# ---- Birebir aynı dosya kopyaları -------------------------------------------------------------
# Aynı ROM (zip içi CRC + boyut, ya da dosya CRC'si) birden çok yerdeyse biri tutulur, diğerleri çöpe.
kopya_durum: dict = {"calisiyor": False}
kopya_sonuc: dict = {}
IMZA_DOSYASI = VERI / "imza_onbellek.json"
JAPON = re.compile(r"\((?:J|JP|JPN|Japan)[,)]", re.I)
BOLGE_CIFTI = {  # aynı donanım, iki klasör: Japon sürümü soldakinde, diğerleri sağdakinde
    frozenset({"famicom", "nes"}): ("famicom", "nes"),
    frozenset({"sfc", "snes"}): ("sfc", "snes"),
}
AKTARILMAZ = {"path", "image", "video", "thumbnail", "marquee", "playcount", "lastplayed", "favorite", "hidden"}


def dosya_imzasi(p: Path):
    if p.suffix.lower() == ".zip":
        with zipfile.ZipFile(p) as z:
            return sorted([x.CRC, x.file_size] for x in z.infolist() if not x.is_dir())
    if p.stat().st_size < 64 * 2**20:
        b = p.read_bytes()
        return [[zlib.crc32(b), len(b)]]
    return None


def gb_renkli(p: Path) -> bool | None:
    """Game Boy başlığındaki 0x143 baytı: 0x80 renk destekli, 0xC0 yalnız renkli."""
    try:
        if p.suffix.lower() == ".zip":
            with zipfile.ZipFile(p) as z:
                ic = [x for x in z.infolist() if not x.is_dir()]
                bas = z.open(ic[0]).read(0x150) if ic else b""
        else:
            with open(p, "rb") as f:
                bas = f.read(0x150)
    except (OSError, zipfile.BadZipFile):
        return None
    return bas[0x143] in (0x80, 0xC0) if len(bas) > 0x143 else None


def kopya_grubu(g: list, kayitli) -> dict:
    kopyalar = []
    for s, i, o in g:
        kopyalar.append({
            "s": s, "id": i, "ad": o["ad"], "dosya": o["dosya"], "klasor": o["klasor"], "boyut": o["boyut"],
            "resim": bool(o["_resim"]), "puan": o["puan"], "oynama": o["oynama"], "kayit": kayitli(KOK / s / i),
            "japon": bool(JAPON.search(o["dosya"]) or JAPON.search(o["ad"])),
        })
    ss_hepsi = sorted({k["s"] for k in kopyalar})
    tur = " ↔ ".join(ss_hepsi) if len(ss_hepsi) > 1 else f"{ss_hepsi[0]} içinde alt klasör kopyası"
    adaylar, neden = list(range(len(kopyalar))), []
    kayitlilar = [n for n, k in enumerate(kopyalar) if k["kayit"] or k["oynama"]]
    karar_sende = sum(kopyalar[n]["kayit"] for n in kayitlilar) > 1
    if kayitlilar:
        adaylar = kayitlilar
        neden.append("kayıt/oynanma geçmişi olan kopya")
    ss = {kopyalar[n]["s"] for n in adaylar}
    hedef = None
    if {"gb", "gbc"} <= ss:
        renk = gb_renkli(KOK / kopyalar[adaylar[0]]["s"] / kopyalar[adaylar[0]]["id"])
        if renk is not None:
            hedef = "gbc" if renk else "gb"
            neden.append("renkli oyun → gbc" if renk else "siyah-beyaz oyun → gb")
    elif frozenset(ss) in BOLGE_CIFTI:
        jp_sis, diger = BOLGE_CIFTI[frozenset(ss)]
        jp = any(kopyalar[n]["japon"] for n in adaylar)
        hedef = jp_sis if jp else diger
        neden.append(f"Japon sürümü → {jp_sis}" if jp else f"USA/Avrupa sürümü → {diger}")
    elif "mame2003" in ss:
        hedef = "mame2003"
        neden.append("R36S'te çalışan çekirdek → mame2003")
    if hedef:
        adaylar = [n for n in adaylar if kopyalar[n]["s"] == hedef] or adaylar
    if len(adaylar) > 1:
        neden.append("kök klasörde / resmi ve puanı olan")
    adaylar.sort(key=lambda n: (kopyalar[n]["klasor"] != "", not kopyalar[n]["resim"],
                                kopyalar[n]["puan"] is None, len(kopyalar[n]["id"])))
    return {"tur": tur, "neden": ", ".join(neden) or "ilk kopya", "karar_sende": karar_sende,
            "kopyalar": kopyalar, "tut": adaylar[0]}


def kopya_tara():
    from concurrent.futures import ThreadPoolExecutor
    d = kopya_durum
    d.update(calisiyor=True, asama="Oyunlar listeleniyor", toplam=0, bakilan=0, hatalar=[])
    try:
        onb = json_oku(IMZA_DOSYASI, {})
        isler = [(s, i, o) for s in sistemler() for i, o in list(sistem_oyunlari(s).items())]
        d.update(toplam=len(isler), asama="Dosya imzaları okunuyor")
        yeni_onb = {}

        def imzala(is_):
            s, i, _ = is_
            p = KOK / s / i
            try:
                st = p.stat()
                k = onb.get(str(p))
                im = k[2] if k and k[0] == st.st_size and k[1] == int(st.st_mtime) else dosya_imzasi(p)
                yeni_onb[str(p)] = [st.st_size, int(st.st_mtime), im]
                return im
            except (OSError, zipfile.BadZipFile, ValueError):
                return None
            finally:
                d["bakilan"] += 1

        with ThreadPoolExecutor(8) as havuz:
            imzalar = list(havuz.map(imzala, isler))
        json_yaz(IMZA_DOSYASI, yeni_onb)
        d["asama"] = "Gruplanıyor"
        gruplar = defaultdict(list)
        for is_, im in zip(isler, imzalar):
            if im:  # boş zip gruplanmasın
                gruplar[json.dumps(im)].append(is_)
        dizinler: dict[Path, list[str]] = {}

        def kayitli(p: Path) -> bool:
            if p.parent not in dizinler:
                dizinler[p.parent] = [f.lower() for f in os.listdir(p.parent)]
            kok = p.stem.lower() + "."
            return any(f.startswith(kok) and (f.endswith((".srm", ".sav")) or ".state" in f) for f in dizinler[p.parent])

        sonuc = [kopya_grubu(g, kayitli) for g in gruplar.values() if len(g) > 1]
        sonuc.sort(key=lambda x: (not x["karar_sende"], x["tur"], x["kopyalar"][x["tut"]]["ad"].lower()))
        for n, x in enumerate(sonuc):
            x["no"] = n
        kopya_sonuc.clear()
        kopya_sonuc.update(kok=str(KOK), gruplar=sonuc)
        d["asama"] = "Bitti"
    except Exception as e:  # noqa: BLE001
        d["hatalar"].append(str(e))
        d["asama"] = "Hata"
    finally:
        d["calisiyor"] = False


def kopya_uygula(kararlar: list[dict]):
    """[{no, tut: [s, id], sil: [[s, id], ...]}] — silinenin resmi/bilgisi tutulana aktarılır, sonra silinen çöpe."""
    d = kopya_durum
    d.update(calisiyor=True, asama="Resim ve bilgiler aktarılıyor", toplam=len(kararlar), bakilan=0,
             tasinan=0, aktarilan=0, hatalar=[])
    try:
        gl_onb: dict[str, dict] = {}

        def gl(s):
            if s not in gl_onb:
                gl_onb[s] = gamelist_oku(KOK / s)
            return gl_onb[s]

        def aktar(k) -> dict:
            """Silinecek kopyalardaki resim/bilgiden tutulanın gamelist'ine yazılacakları hazırlar."""
            ts, ti = k["tut"]
            tut_o = sistem_oyunlari(ts).get(ti)
            if not tut_o:
                raise OSError(f"{ts}/{ti}: tutulacak oyun bulunamadı")
            tut_bilgi, ekle = gl(ts).get(ti.lower(), {}), {}
            # Konsolun göreceği resim = tutulanın kendi gamelist'indeki <image>. Uygulamanın başka
            # sistemden ödünç gösterdiği resim sayılmaz; o durumda silinen kopyanın resmi aktarılır.
            kendi_resmi = bool(tut_bilgi.get("image")) and medya_yolu(KOK / ts, tut_bilgi["image"]) is not None
            if not kendi_resmi and tut_o["_resim"] and Path(tut_o["_resim"]).is_relative_to(KOK / ts):
                ekle["image"] = "./" + Path(tut_o["_resim"]).relative_to(KOK / ts).as_posix()
                kendi_resmi = True  # kendi klasöründe adıyla duran resim: yalnızca gamelist'e yazılır
            for ss, si in k["sil"]:
                o = sistem_oyunlari(ss).get(si)
                if not o:
                    continue
                for etiket, deger in gl(ss).get(si.lower(), {}).items():
                    if etiket not in AKTARILMAZ and deger and not tut_bilgi.get(etiket):
                        ekle.setdefault(etiket, deger)
                if not kendi_resmi and o["_resim"]:
                    kendi_resmi = True
                    kaynak = Path(o["_resim"])
                    if kaynak.is_relative_to(KOK / ts):  # resim zaten tutulanın sisteminde: yolu yazılır
                        hedef = kaynak
                    else:  # başka sistemdeki (ödünç dahil) resim: tutulanın klasörüne kopyala
                        hedef = resim_hedefi(ts, ti).with_suffix(kaynak.suffix.lower())
                        while hedef.exists():
                            hedef = hedef.with_name(hedef.stem + "~" + uuid.uuid4().hex[:4] + hedef.suffix)
                        hedef.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(kaynak, hedef)
                    ekle["image"] = "./" + hedef.relative_to(KOK / ts).as_posix()
                    tut_o["_resim"] = str(hedef)  # paylaşım denetimi silinirken bunu görsün
            return ekle

        # Bir grupta hata olursa yalnız o grup atlanır (kopyası silinmez), iş sürer.
        guncelle: dict[str, dict] = defaultdict(dict)
        gecerli = []
        for k in kararlar:
            d["bakilan"] += 1
            try:
                ekle = aktar(k)
            except Exception as e:  # noqa: BLE001
                d["hatalar"].append(f"{k['tut'][0]}/{k['tut'][1]}: {e} — grup atlandı")
                continue
            if ekle:
                guncelle[k["tut"][0]][k["tut"][1]] = ekle
                d["aktarilan"] += 1
            gecerli.append(k)
        d["asama"] = "gamelist.xml yazılıyor"
        for s, deg in guncelle.items():
            try:
                gamelist_guncelle(s, deg)
            except (OSError, ET.ParseError) as e:
                # Aktarım kaydedilemediyse o sistemde bilgi alan grupların kopyaları silinmesin.
                d["hatalar"].append(f"{s}/gamelist.xml: {e} — bu sistemdeki {len(deg)} grup atlandı")
                gecerli = [k for k in gecerli if not (k["tut"][0] == s and k["tut"][1] in deg)]
        kararlar = gecerli
        sil_sis: dict[str, list] = defaultdict(list)
        for k in kararlar:
            for ss, si in k["sil"]:
                sil_sis[ss].append(si)
        d.update(asama="Kopyalar çöpe taşınıyor", toplam=sum(map(len, sil_sis.values())), bakilan=0)
        for s, ids in sil_sis.items():
            for parca in range(0, len(ids), 100):
                r = cope_tasi(s, ids[parca:parca + 100])
                d["tasinan"] += len(r["tasinan"])
                d["hatalar"] += r["hatalar"]
                d["bakilan"] += len(ids[parca:parca + 100])
        for s in guncelle:  # puan/açıklama aktarılanlar yeniden okunsun
            onbellek.pop(s, None)
        uygulanan = {k.get("no") for k in kararlar}
        kopya_sonuc["gruplar"] = [g for g in kopya_sonuc.get("gruplar", []) if g["no"] not in uygulanan]
        d["asama"] = "Bitti"
    except Exception as e:  # noqa: BLE001
        d["hatalar"].append(str(e))
        d["asama"] = "Hata"
    finally:
        d["calisiyor"] = False


def disa(o: dict, isaretler: dict, sistem: str) -> dict:
    d = {k: v for k, v in o.items() if not k.startswith("_")}
    d["resim"] = bool(o["_resim"])
    if o["_resim"]:  # resim değişince tarayıcı önbelleği eskisini göstermesin
        try:
            d["v"] = int(os.path.getmtime(o["_resim"]))
        except OSError:
            pass
    d["video"] = bool(o["_video"])
    d["tut"] = bool(isaretler.get(f"{sistem}/{o['id']}"))
    return d


def yan_dosyalar(p: Path, dizinler: dict | None = None) -> list[Path]:
    """Aynı klasörde aynı köke sahip dosyalar (kayıt, save state...).
    dizinler: toplu işte klasör listesini bir kez okumak için paylaşılan sözlük."""
    kok, ad = p.stem.lower(), p.name.lower()
    try:
        if dizinler is None:
            adlar = os.listdir(p.parent)
        else:
            if p.parent not in dizinler:
                dizinler[p.parent] = os.listdir(p.parent)
            adlar = dizinler[p.parent]
    except OSError:
        return []
    sonuc = []
    for f in adlar:  # önce ada bak; dosya sistemine yalnız eşleşenler için sor (SD kartta stat pahalı)
        fl = f.lower()
        if fl == ad or fl.rsplit(".", 1)[-1] in ROM_UZANTI:
            continue
        if fl.rsplit(".", 1)[0] == kok or fl.startswith(ad + "."):
            q = p.parent / f
            if q.is_file():  # toplu işte başka oyunla birlikte taşınmış olabilir
                sonuc.append(q)
    return sonuc


def cope_tasi(sistem: str, ids: list[str]) -> dict:
    oyunlar = sistem_oyunlari(sistem)
    kayit = json_oku(KAYIT, [])
    tasinan, kids, hatalar = [], [], []
    dizinler: dict = {}
    with kilit:
        # Resim/video başka oyunca da kullanılıyorsa (aynı ad, başka sistem) yerinde kalır.
        kullanim = Counter(x[alan] for s in onbellek.values() for x in s.values()
                           for alan in ("_resim", "_video") if x[alan])
        for i in ids:
            o = oyunlar.get(i)
            if not o:
                hatalar.append(f"{i}: bulunamadı")
                continue
            ana = KOK / sistem / i
            parcalar = [ana, *yan_dosyalar(ana, dizinler)]
            for alan in ("_resim", "_video"):
                m = o[alan]
                if m and kullanim[m] < 2 and Path(m).exists():
                    parcalar.append(Path(m))
            hareketler = []
            try:
                for p in parcalar:
                    hedef = COP / p.relative_to(KOK)
                    if hedef.exists():
                        hedef = hedef.with_name(f"{hedef.stem}~{uuid.uuid4().hex[:6]}{hedef.suffix}")
                    hedef.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(p), str(hedef))
                    hareketler.append([str(p), str(hedef)])
            except OSError as e:
                hatalar.append(f"{o['ad']}: {e}")
                for kaynak, hedef in reversed(hareketler):
                    shutil.move(hedef, kaynak)
                continue
            kids.append(uuid.uuid4().hex)
            kayit.append({
                "kid": kids[-1], "zaman": time.strftime("%Y-%m-%d %H:%M"),
                "sistem": sistem, "ad": o["ad"], "id": i,
                "boyut": sum(Path(h).stat().st_size for _, h in hareketler),
                "hareketler": hareketler,
                # Çöpte göstermek için: taşındıysa yeni yeri, paylaşımlı olup yerinde kaldıysa eski yeri.
                "resim": next((h for k, h in hareketler if k == o["_resim"]), o["_resim"]),
            })
            del oyunlar[i]
            tasinan.append(i)
        json_yaz(KAYIT, kayit)
    return {"tasinan": tasinan, "kids": kids, "hatalar": hatalar}


def geri_al(kids: list[str]) -> dict:
    kayit = json_oku(KAYIT, [])
    kalan, geri, hatalar = [], [], []
    with kilit:
        for k in kayit:
            if k["kid"] not in kids:
                kalan.append(k)
                continue
            try:
                for kaynak, hedef in k["hareketler"]:
                    if Path(kaynak).exists():
                        raise OSError(f"yerinde başka dosya var: {kaynak}")
                for kaynak, hedef in k["hareketler"]:
                    Path(kaynak).parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(hedef, kaynak)
                geri.append(k["kid"])
                onbellek.pop(k["sistem"], None)
            except OSError as e:
                hatalar.append(f"{k['ad']}: {e}")
                kalan.append(k)
        json_yaz(KAYIT, kalan)
    return {"geri": geri, "hatalar": hatalar}


def copu_bosalt() -> dict:
    with kilit:
        kayit = json_oku(KAYIT, [])
        boyut = sum(k.get("boyut", 0) for k in kayit)
        for d in COP.iterdir() if COP.exists() else []:
            if d.is_dir():
                shutil.rmtree(d, ignore_errors=True)
        json_yaz(KAYIT, [])
    return {"silinen": len(kayit), "boyut": boyut}


class Isleyici(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def gonder(self, kod, govde: bytes, tur="application/json; charset=utf-8", ek=None):
        self.send_response(kod)
        self.send_header("Content-Type", tur)
        self.send_header("Content-Length", str(len(govde)))
        for k, v in (ek or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(govde)

    def json(self, veri, kod=200):
        self.gonder(kod, json.dumps(veri, ensure_ascii=False).encode("utf-8"))

    def dosya(self, yol: str | None):
        if not yol or not Path(yol).is_file():
            return self.gonder(404, b"")
        tur = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
               ".gif": "image/gif", ".mp4": "video/mp4"}.get(Path(yol).suffix.lower(), "application/octet-stream")
        self.gonder(200, Path(yol).read_bytes(), tur, {"Cache-Control": "max-age=3600"})

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/":
                return self.gonder(200, (BURASI / "index.html").read_bytes(), "text/html; charset=utf-8")
            if u.path == "/api/sistemler":
                if not KOK.is_dir():
                    return self.json({"kok": "" if str(KOK) == SECILMEDI else str(KOK), "gecerli": False, "sistemler": {}})
                sayilar = {s: len(sistem_oyunlari(s)) for s in sistemler()}
                return self.json({"kok": str(KOK), "gecerli": True, "sistemler": {s: n for s, n in sayilar.items() if n}})
            if u.path == "/api/kopya":
                gecerli = kopya_sonuc.get("kok") == str(KOK)
                return self.json({"durum": kopya_durum, "gruplar": kopya_sonuc.get("gruplar") if gecerli else None})
            if u.path == "/api/toplu-durum":
                return self.json(toplu_durum)
            if u.path == "/api/adaylar":
                return self.json(aday_klasorler())
            if u.path == "/api/oyunlar":
                s = q["s"]
                isaretler = json_oku(ISARET_DOSYASI, {})
                return self.json([disa(o, isaretler, s) for o in sistem_oyunlari(s).values()])
            if u.path in ("/resim", "/video"):
                o = sistem_oyunlari(q["s"]).get(q["id"])
                return self.dosya(o and o["_resim" if u.path == "/resim" else "_video"])
            if u.path == "/cop-resim":
                k = next((k for k in json_oku(KAYIT, []) if k["kid"] == q["kid"]), None)
                # Eski kayıtlarda "resim" alanı yok: taşınan dosyalar arasından resmi bul.
                yol = k and (k.get("resim") or next(
                    (h for _, h in k["hareketler"] if Path(h).suffix.lower() in RESIM_UZANTI), None))
                return self.dosya(yol)
            if u.path == "/api/internet":
                return self.json(internet_resimleri(q["s"], q["id"]))
            if u.path == "/api/cop":
                return self.json(json_oku(KAYIT, []))
            self.gonder(404, b"")
        except (KeyError, OSError) as e:
            self.json({"hata": str(e)}, 400)

    def do_POST(self):
        u = urlparse(self.path)
        uzunluk = int(self.headers.get("Content-Length") or 0)
        v = json.loads(self.rfile.read(uzunluk) or b"{}")
        try:
            if u.path == "/api/sil":
                return self.json(cope_tasi(v["s"], v["ids"]))
            if u.path in ("/api/kopya-tara", "/api/kopya-uygula"):
                if kopya_durum.get("calisiyor"):
                    return self.json({"hata": "Zaten çalışıyor"}, 409)
                is_ = (kopya_tara, ()) if u.path == "/api/kopya-tara" else (kopya_uygula, (v["kararlar"],))
                threading.Thread(target=is_[0], args=is_[1], daemon=True).start()
                return self.json({"basladi": True})
            if u.path == "/api/resim-kaydet":
                return self.json(resim_kaydet(v["s"], v["id"], v["url"]))
            if u.path == "/api/toplu-resim":
                if toplu_durum.get("calisiyor"):
                    return self.json({"hata": "Zaten çalışıyor"}, 409)
                hedef = v.get("sistemler") or [s for s in sistemler() if sistem_oyunlari(s)]
                threading.Thread(target=toplu_resim, args=(hedef,), daemon=True).start()
                return self.json({"basladi": True})
            if u.path == "/api/kok":
                return self.json({"kok": str(kok_degistir(v["yol"]))})
            if u.path == "/api/gozat":
                return self.json({"yol": klasor_gozat()})
            if u.path == "/api/geri":
                return self.json(geri_al(v["kids"]))
            if u.path == "/api/cop-bosalt":
                return self.json(copu_bosalt())
            if u.path == "/api/isaret":
                with kilit:
                    isaretler = json_oku(ISARET_DOSYASI, {})
                    for i in v["ids"]:
                        anahtar = f"{v['s']}/{i}"
                        if v["deger"]:
                            isaretler[anahtar] = 1
                        else:
                            isaretler.pop(anahtar, None)
                    json_yaz(ISARET_DOSYASI, isaretler)
                return self.json({"tamam": True})
            self.gonder(404, b"")
        except (KeyError, OSError) as e:
            self.json({"hata": str(e)}, 400)


if __name__ == "__main__":
    if not KOK.is_dir():
        adaylar = aday_klasorler()
        if adaylar:  # ilk açılış ya da kart başka harfle takılı: bulunan ilk kartı kullan
            kok_degistir(adaylar[0]["yol"])
    adres = f"http://{HOST}:{PORT}"
    try:
        sunucu = ThreadingHTTPServer((HOST, PORT), Isleyici)
    except OSError:  # port dolu: büyük olasılıkla uygulama zaten açık; tarayıcıda onu aç
        print(f"Already running? / Zaten açık mı?  ->  {adres}", flush=True)
        if PAKET:
            import webbrowser
            webbrowser.open(adres)
            time.sleep(5)
        sys.exit(1)
    print(f"ROM folder / Oyun klasörü: {KOK if KOK.is_dir() else '-'}", flush=True)
    print(f"\n    Open / Aç:  {adres}\n", flush=True)
    if PAKET:  # .exe çift tıkla açıldı: tarayıcıyı da aç; pencere kapanınca uygulama kapanır
        print("    Close this window to quit. / Kapatmak için bu pencereyi kapatın.\n", flush=True)
        import webbrowser
        threading.Timer(1.0, webbrowser.open, (adres,)).start()
    sunucu.serve_forever()

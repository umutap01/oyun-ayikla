# ROM Sorter (Oyun Ayıkla)

A small local web app to **browse and clean up the games on a retro handheld's SD card**
(R36S, other ArkOS / EmulationStation devices) — with box art, ratings and year, so you can
decide quickly what to keep and what to delete.

![ROM Sorter](docs/screenshot.png)

**English · [Türkçe](#türkçe)**

## Features

- Grid of every game per system with image, rating, year and size (read from `gamelist.xml`)
- Select with click / Shift+click, **Del** = move to trash, **T** = keep (kept games can be hidden)
- **Trash is safe**: games (with save files, image, video) are moved to `_cop/` on the card and can be
  restored; nothing is deleted until you empty the trash
- **Zoom view** with ← / → navigation and online images from
  [libretro-thumbnails](https://github.com/libretro-thumbnails/libretro-thumbnails); save one to the card
  in a click (it is written to `gamelist.xml`, so the console shows it too)
- **Missing images**: download exact-name matches for every game without an image
- **Duplicates**: finds byte-identical ROMs across systems/folders and suggests which copy to keep
- Adjustable games per row, search, sort, filters; English and Turkish UI

![Zoom view](docs/zoom.png)

## Download & run

### Windows — no install needed

1. Download **ROM-Sorter.exe** from the [latest release](https://github.com/umutap01/oyun-ayikla/releases/latest).
2. Put the SD card in a card reader and double-click `ROM-Sorter.exe`.
3. Windows may show *"Windows protected your PC"* (the app is not code-signed):
   click **More info → Run anyway**.
4. Your browser opens **http://127.0.0.1:8736**. The inserted card is found automatically;
   otherwise click **Choose folder**.

A black window stays open while the app runs — **closing it quits the app**. Your marks and settings are
kept in a `veri` folder next to the exe.

### macOS / Linux (or Windows with Python)

1. Install **Python 3.10+** from [python.org](https://www.python.org/downloads/)
   (Windows: tick **"Add python.exe to PATH"** in the installer).
2. Download this project: green **Code** button → **Download ZIP**, then unzip it
   (or `git clone https://github.com/umutap01/oyun-ayikla.git`).
3. Start it:
   - **Windows:** double-click `baslat.bat`
   - **macOS:** open *Terminal*, type `sh ` (with a space), drag `baslat.sh` into the window, press Enter
   - **Linux:** `sh baslat.sh` (on Debian/Ubuntu install Pillow first: `sudo apt install python3-pil`)
4. Open **http://127.0.0.1:8736**.

Manual start: `pip install -r requirements.txt` then `python src/sunucu.py [ROM_FOLDER]`.

> **Back up your card first.** The app moves and writes files on the card (trash, images, `gamelist.xml`;
> each gamelist is backed up as `gamelist.xml.yedek-…` before writing). No ROMs are included or downloaded.
> The server listens on `127.0.0.1` only.

### Troubleshooting

- **Card not listed:** use *Choose folder → Browse…* and pick the folder that contains `nes`, `snes`, `gba`…
  If the card does not appear in Explorer/Finder at all, its game partition may be Linux-formatted (ext4)
  and your computer cannot read it.
- **Page does not open:** make sure the black window (or terminal) is still open, then go to
  http://127.0.0.1:8736 yourself.
- **Antivirus blocks the exe:** single-file Python apps are sometimes flagged by mistake. Use the
  Python way above, or build the exe yourself with `build_exe.bat`.

---

## Türkçe

Retro el konsolu kartındaki (R36S ve diğer ArkOS / EmulationStation cihazları) oyunları resim, puan ve
yılıyla gösterip **ayıklamaya** yarayan küçük yerel web uygulaması.

- Sistem başına tüm oyunlar ızgarada; tıkla/Shift+tıkla seç, **Del** çöpe, **T** tut
- Silme kalıcı değil: oyun kayıt dosyaları ve resmiyle kartta `_cop/` klasörüne taşınır, geri alınır
- Büyüteç: ← / → ile gezinme, libretro-thumbnails'ten resim önerisi, tek tıkla karta kaydetme
- Eksik resimleri toplu indirme, birebir aynı kopyaları bulma, yan yana oyun sayısı, arama/sıralama/süzme
- Arayüz Türkçe ve İngilizce (sağ üstteki TR/EN)

**Windows'ta kurulum gerekmez:** [son sürümden](https://github.com/umutap01/oyun-ayikla/releases/latest)
**ROM-Sorter.exe**'yi indir, kartı tak, çift tıkla. "Windows bilgisayarınızı korudu" çıkarsa
**Ek bilgi → Yine de çalıştır**. Tarayıcı kendiliğinden **http://127.0.0.1:8736** adresini açar;
siyah pencere kapanınca uygulama da kapanır.

**macOS / Linux:** Python 3.10+ kur, yeşil **Code → Download ZIP** ile indirip aç, `sh baslat.sh`.

> **Önce kartın yedeğini al.** Uygulama kartta dosya taşır ve yazar. ROM içermez, ROM indirmez.

## License

MIT — see [LICENSE](LICENSE).

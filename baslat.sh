#!/bin/sh
# ROM Sorter / Oyun Ayıkla — macOS / Linux
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "Python 3.10+ required: https://www.python.org/downloads/"; exit 1; }
python3 -c "import PIL" 2>/dev/null || python3 -m pip install --user -r requirements.txt
( sleep 2; (command -v open >/dev/null && open http://127.0.0.1:8736) || (command -v xdg-open >/dev/null && xdg-open http://127.0.0.1:8736) ) >/dev/null 2>&1 &
exec python3 src/sunucu.py "$@"

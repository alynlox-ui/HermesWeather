#!/usr/bin/env python3
"""Silent wrapper for refresh_hot_news_snapshot.py.

Schedule this with Task Scheduler (schtasks) to keep hot-news.json fresh
without console popups. Uses whichever interpreter runs this wrapper
(pythonw.exe suppresses the console window), so it is not pinned to one
machine's absolute path anymore.
"""
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
SCRIPT = str(BASE / "refresh_hot_news_snapshot.py")
LOG = str(BASE / "hot-news-refresh.log")

with open(LOG, "a", encoding="utf-8") as f:
    subprocess.run([sys.executable, SCRIPT], stdout=f, stderr=subprocess.STDOUT,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

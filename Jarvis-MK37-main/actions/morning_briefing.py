"""
Morning Briefing — déclenché par shortcut (ex: double clap).

Compose une instruction texte injectée dans Gemini Live. Gemini appelle ensuite
les tools nécessaires (youtube_video, web_search, weather_report) dans l'ordre.

Renvoie le prompt à envoyer. Le caller doit appeler `speak(prompt)` ou
`_on_text_command(prompt)` pour l'injecter dans la session.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


def _today_reminders() -> list[str]:
    """Liste les scripts de reminders planifiés pour aujourd'hui."""
    out = []
    try:
        d = Path.home() / ".jarvis" / "reminders"
        if not d.exists():
            return out
        today = datetime.now().strftime("%Y%m%d")
        for f in d.glob("JARVISReminder_*.py"):
            m = re.match(r"JARVISReminder_(\d{8})_(\d{6})", f.stem)
            if not m or m.group(1) != today:
                continue
            hhmm = f"{m.group(2)[:2]}:{m.group(2)[2:4]}"
            # Extrait le message depuis le script
            try:
                txt = f.read_text(encoding="utf-8", errors="ignore")
                mm = re.search(r'message\s*=\s*"([^"]*)"', txt)
                label = mm.group(1) if mm else f.stem
            except Exception:
                label = f.stem
            out.append(f"{hhmm} — {label}")
    except Exception:
        pass
    return sorted(out)


def build_morning_briefing_prompt(city: str = "Aix-en-Provence") -> str:
    todos = _today_reminders()
    todos_str = "\n".join(f"- {t}" for t in todos) if todos else "(none scheduled)"
    today = datetime.now().strftime("%A %B %d, %Y")

    return (
        "[SHORTCUT: double clap] — run my morning briefing NOW, in one go, "
        "without asking for confirmation:\n"
        "1. Play the Iron Man main theme on YouTube using the youtube_video tool "
        "(action=play, query=\"Iron Man main theme soundtrack\").\n"
        "2. Use web_search to fetch Bitcoin price today in USD.\n"
        f"3. Use weather_report for {city}.\n"
        "4. Here are today's scheduled reminders (no tool needed, just read them back):\n"
        f"{todos_str}\n\n"
        f"Today is {today}. After all tools return, give me ONE short spoken "
        "summary: Bitcoin price, weather in one sentence, and today's agenda. "
        "Keep it under 6 sentences, style MARK XXXVII, sir."
    )

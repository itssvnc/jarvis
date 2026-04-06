#!/usr/bin/env python3
"""
JARVIS Custom Skills
Add your own commands here — they're parsed before the LLM,
so they're instant and don't require GPU/CPU inference.
"""

import subprocess
import re


SKILLS = []


def skill(pattern: str):
    """Decorator to register a skill with a regex trigger pattern."""
    def decorator(fn):
        SKILLS.append((re.compile(pattern, re.IGNORECASE), fn))
        return fn
    return decorator


# ── Built-in skills ────────────────────────────────────────────────────────────

@skill(r"open (firefox|browser|web)")
def open_firefox(match):
    subprocess.Popen(["firefox"], start_new_session=True)
    return "Opening Firefox."


@skill(r"open (terminal|term|kitty|alacritty)")
def open_terminal(match):
    for term in ["kitty", "alacritty", "xterm"]:
        try:
            subprocess.Popen([term], start_new_session=True)
            return f"Opening {term}."
        except FileNotFoundError:
            continue
    return "No terminal emulator found."


@skill(r"(workspace|switch to workspace) (\d+)")
def switch_workspace(match):
    num = match.group(2)
    subprocess.run(["i3-msg", f"workspace {num}"])
    return f"Switching to workspace {num}."


@skill(r"volume (up|\d+)")
def set_volume(match):
    val = match.group(1)
    if val == "up":
        subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+10%"])
        return "Volume up."
    subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{val}%"])
    return f"Volume set to {val} percent."


@skill(r"volume down")
def volume_down(match):
    subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-10%"])
    return "Volume down."


@skill(r"(mute|unmute)")
def toggle_mute(match):
    subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])
    return "Toggled mute."


@skill(r"(lock|lock screen)")
def lock_screen(match):
    subprocess.Popen(["i3lock", "-c", "000000"])
    return "Locking screen."


@skill(r"(screenshot|take a screenshot)")
def screenshot(match):
    import datetime
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"~/Pictures/screenshot_{ts}.png"
    subprocess.Popen(["scrot", path])
    return f"Screenshot saved to Pictures."


@skill(r"what time is it|current time")
def what_time(match):
    import datetime
    now = datetime.datetime.now().strftime("%I:%M %p")
    return f"It's {now}."


@skill(r"what('s| is) (today|the date)")
def what_date(match):
    import datetime
    today = datetime.datetime.now().strftime("%A, %B %d")
    return f"Today is {today}."


def try_skills(text: str):
    """
    Try local skills before hitting the LLM.
    Returns response string if matched, None otherwise.
    """
    for pattern, fn in SKILLS:
        m = pattern.search(text)
        if m:
            return fn(m)
    return None

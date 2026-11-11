#!/usr/bin/env python3
"""zsh-autosuggestions style project picker for the `codium` command."""

import os
import select
import shutil
import sys
import termios
import tty

PROJECTS_DIR = os.environ.get("CODIUM_PROJECTS_DIR") or os.path.join(
    os.path.expanduser("~"), "The Porojects"
)

ESC = "\x1b"
CSI = ESC + "["
HIDE = CSI + "?25l"
SHOW = CSI + "?25h"
RESET = CSI + "0m"
DIM = CSI + "2m"
BOLD = CSI + "1m"
CYAN = CSI + "36m"
GREEN = CSI + "32m"
YELLOW = CSI + "33m"
RED = CSI + "31m"
GREY = CSI + "90m"

MAX_ROWS = 8


def vis_len(s):
    n = 0
    for ch in s:
        if unicodedata_wide(ch):
            n += 2
        elif unicodedata_combining(ch):
            n += 0
        else:
            n += 1
    return n


def unicodedata_wide(ch):
    return ord(ch) > 0x1100 and (
        unicodedata_east_asian(ch)
        or unicodedata_ambiguous_wide(ch)
    )


def unicodedata_east_asian(ch):
    import unicodedata

    return unicodedata.east_asian_width(ch) in ("W", "F")


def unicodedata_ambiguous_wide(ch):
    return False


def unicodedata_combining(ch):
    import unicodedata

    return unicodedata.combining(ch) != 0


def score(buf, name):
    lb = buf.lower()
    ln = name.lower()
    if not lb:
        return (0, 0, 0), []
    if ln == lb:
        return (0, len(name), 0), list(range(len(name)))
    if ln.startswith(lb):
        return (10, len(name), 0), list(range(len(lb)))
    idx = ln.find(lb)
    if idx >= 0:
        return (50 + idx, len(name), 0), list(range(idx, idx + len(lb)))
    pos = 0
    hits = []
    gaps = 0
    for i, ch in enumerate(ln):
        if pos < len(lb) and ch == lb[pos]:
            hits.append(i)
            pos += 1
        elif hits:
            gaps += 1
    if pos == len(lb):
        return (200 + gaps, len(name), hits[0] if hits else 0), hits
    return None, []


def match_positions(buf, name):
    s, hits = score(buf, name)
    return hits


def candidates(buf):
    out = []
    try:
        names = sorted(os.listdir(PROJECTS_DIR))
    except OSError:
        names = []
    for n in names:
        if n.startswith("."):
            continue
        s, hits = score(buf, n)
        if s is None:
            continue
        out.append((s, n, hits))
    out.sort(key=lambda t: t[0])
    return out


def highlight(name, hits, color):
    if not hits:
        return name
    hs = set(hits)
    res = []
    for i, ch in enumerate(name):
        res.append(color + ch + RESET if i in hs else ch)
    return "".join(res)


class Screen:
    def __init__(self, stream):
        self.stream = stream
        self.saved = None
        self.fd = stream.fileno()
        self.height = 0
        self.width = 80

    def __enter__(self):
        try:
            self.saved = termios.tcgetattr(self.fd)
            tty.setraw(self.fd)
        except termios.error:
            self.saved = None
        self.stream.write(HIDE)
        self.stream.flush()
        return self

    def __exit__(self, *a):
        if self.saved is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)
        self.stream.write(RESET + SHOW + "\n")
        self.stream.flush()

    def clear(self):
        if self.height:
            self.stream.write(CSI + "1G" + CSI + "0J")
        else:
            self.stream.write(CSI + "2J" + CSI + "H")
        self.stream.flush()
        self.height = 0

    def line(self, text=""):
        self.stream.write(text + "\r\n")
        self.height += 1

    def render(self, lines, prompt_active=True):
        size = shutil.get_terminal_size((80, 24))
        self.width = size.columns
        out = [CSI + "1G" + CSI + "0J"]
        n = 0
        for text in lines:
            out.append(CSI + str(n + 1) + ";1H" + text + CSI + "K")
            n += 1
        self.stream.write("".join(out))
        self.stream.flush()
        self.height = n


SIMPLE = {
    "\x7f": "BACKSPACE", "\x08": "BACKSPACE", "\r": "ENTER", "\n": "ENTER",
    "\x03": "CTRLC", "\x04": "EOF", "\t": "TAB", "\x15": "KILLSTART",
    "\x17": "KILLWORD", "\x01": "HOME", "\x05": "END", "\x0b": "KILLEND",
}

FINAL_KEYS = {"A": "UP", "B": "DOWN", "C": "RIGHT", "D": "LEFT", "H": "HOME", "F": "END"}
TILDE_KEYS = {"1": "HOME", "3": "DELETE", "4": "END", "7": "HOME", "8": "END"}


class KeyReader:
    def __init__(self, fd):
        self.fd = fd
        self.raw = b""
        self.s = ""
        self.eof = False

    def _fill(self, timeout):
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r:
            return False
        try:
            d = os.read(self.fd, 4096)
        except OSError:
            self.eof = True
            return False
        if not d:
            self.eof = True
            return False
        self.raw += d
        return True

    def _sync(self):
        if not self.raw:
            self.s = ""
            return
        try:
            self.s = self.raw.decode("utf-8")
            self.raw = b""
            return
        except UnicodeDecodeError as e:
            if e.start == 0 and len(self.raw) < 4 and not self.eof:
                if self._fill(0.05):
                    return self._sync()
        self.s = self.raw.decode("utf-8", "replace")
        self.raw = b""

    def get(self, timeout=0.4):
        self._sync()
        if not self.s:
            if not self._fill(timeout):
                return "EOF" if self.eof else None
            self._sync()
            if not self.s:
                return None
        ch = self.s[0]
        if ch != ESC:
            self.s = self.s[1:]
            if ch in SIMPLE:
                return SIMPLE[ch]
            if ord(ch) < 32:
                return None
            return ch
        if len(self.s) == 1:
            if not self._fill(0.05):
                self.s = ""
                return "ESC"
            self._sync()
            if len(self.s) == 1:
                self.s = ""
                return "ESC"
        self.s = self.s[1:]
        if not self.s or self.s[0] not in "[O":
            return "ESC"
        self.s = self.s[1:]
        seq = ""
        while self.s and (self.s[0].isalnum() or self.s[0] in "~;"):
            seq += self.s[0]
            self.s = self.s[1:]
        if seq.endswith("~"):
            return TILDE_KEYS.get(seq.split(";")[0], "ESC")
        letters = "".join(c for c in seq if c.isalpha())
        return FINAL_KEYS.get(letters[-1], "ESC") if letters else "ESC"



def ghost_for(buf, cands):
    if not buf or not cands:
        return None
    s, name, hits = cands[0]
    lb = buf.lower()
    ln = name.lower()
    if ln.startswith(lb):
        return name[len(buf):]
    return name


def draw_pick(scr, buf, cur, cands, msg, msgcolor):
    W = scr.width
    lines = []
    title = " VSCodium " + RESET + DIM + "  open or create a project in " + RESET + CYAN + PROJECTS_DIR + RESET
    lines.append(title)
    lines.append("")
    if msg:
        lines.append(" " + msgcolor + msg + RESET)
        lines.append("")

    ghost = ghost_for(buf, cands)
    left = " " + GREEN + "❯ " + RESET + BOLD
    pre = buf[:cur]
    post = buf[cur:]
    line = left + pre
    if ghost:
        line += DIM + ghost + RESET
    if post:
        line += post
    lines.append(line)

    if not buf:
        lines.append(
            "   " + GREY + "type a name  ·  ↑↓ browse  ·  → accept suggestion  ·  Ctrl-C quit" + RESET
        )
    else:
        lines.append("")

    shown = cands[:MAX_ROWS]
    if shown:
        for i, (s, name, hits) in enumerate(shown):
            sel = i == 0
            mark = GREEN + "❯" + RESET if sel else " "
            tag = GREEN + "open" + RESET if sel else GREY + "open" + RESET
            path = GREY + os.path.join(PROJECTS_DIR, name) + RESET
            lines.append("  " + mark + " " + highlight(name, hits, CYAN if sel else YELLOW) + "  " + tag + "  " + path)
        if len(cands) > MAX_ROWS:
            lines.append(GREY + "    … " + str(len(cands) - MAX_ROWS) + " more" + RESET)
    else:
        lines.append("  " + DIM + "no existing project matches" + RESET)
        lines.append("  " + DIM + "Enter to create " + RESET + YELLOW + buf + RESET + DIM + " as a new project" + RESET)

    lines.append("")
    lines.append(
        "  " + GREY + "Enter open/create · Tab complete · → accept · Enter again in list to open · Ctrl-C quit" + RESET
    )
    scr.render(lines)


def draw_browse(scr, cands, selected):
    lines = []
    lines.append(
        " " + RESET + BOLD + " VSCodium " + RESET + DIM + "projects in " + RESET + CYAN + PROJECTS_DIR + RESET
    )
    lines.append("")
    if not cands:
        lines.append("  " + DIM + "(empty — type a name and press Enter to create one)" + RESET)
    shown = cands[:MAX_ROWS]
    for i, (s, name, hits) in enumerate(shown):
        sel = i == selected
        mark = GREEN + "❯ " + RESET if sel else "  "
        col = BOLD + CYAN if sel else ""
        end = RESET if sel else ""
        lines.append("  " + mark + col + name + end + "  " + GREY + os.path.join(PROJECTS_DIR, name) + RESET)
    if len(cands) > MAX_ROWS:
        lines.append(GREY + "    … " + str(len(cands) - MAX_ROWS) + " more" + RESET)
    lines.append("")
    lines.append("  " + GREY + "↑↓ move · Enter open · Esc/Ctrl-C back · q quit" + RESET)
    scr.render(lines)


def draw_create(scr, name, close=None):
    lines = []
    lines.append(" " + RESET + BOLD + " VSCodium " + RESET + DIM + "new project" + RESET)
    lines.append("")
    lines.append("  " + YELLOW + "Create project " + RESET + BOLD + name + RESET + YELLOW + "?" + RESET)
    lines.append("  " + GREY + os.path.join(PROJECTS_DIR, name) + RESET)
    if close:
        lines.append("")
        lines.append(
            "  " + GREY + "close match: " + RESET + CYAN + close + RESET
            + GREY + "  (Esc to go back and open it)" + RESET
        )
    lines.append("")
    lines.append("  " + GREEN + "Enter/Y" + RESET + " create and open      " + GREY + "n/N/Esc" + RESET + " cancel")
    scr.render(lines)


def run_interactive():
    tty_out = sys.stderr
    if not (sys.stdin.isatty() and tty_out.isatty()):
        return fallback()
    buf = ""
    cur = 0
    msg = None
    msgcolor = DIM
    kr = KeyReader(sys.stdin.fileno())
    with Screen(tty_out) as scr:
        while True:
            cands = candidates(buf)
            draw_pick(scr, buf, cur, cands, msg, msgcolor)
            k = kr.get()
            if k is None:
                continue
            if k in ("CTRLC", "EOF", "q"):
                tty_out.write(RESET + "\n")
                return 130
            if k == "ESC":
                if not buf:
                    tty_out.write(RESET + "\n")
                    return 130
                buf = ""
                cur = 0
                msg = None
                continue
            if k == "ENTER":
                if not buf:
                    if not cands:
                        msg = "nothing to open — type a project name first"
                        msgcolor = YELLOW
                        continue
                    cands = candidates("")
                    sel = 0
                    while True:
                        draw_browse(scr, cands, sel)
                        k2 = kr.get()
                        if k2 is None:
                            continue
                        if k2 == "CTRLC":
                            tty_out.write(RESET + "\n")
                            return 130
                        if k2 == "ESC":
                            break
                        if k2 == "q":
                            tty_out.write(RESET + "\n")
                            return 130
                        if k2 == "UP":
                            sel = (sel - 1) % max(len(cands), 1)
                        elif k2 == "DOWN":
                            sel = (sel + 1) % max(len(cands), 1)
                        elif k2 == "ENTER":
                            if cands:
                                return ("open", cands[sel][1])
                    continue
                cands = candidates(buf)
                if os.path.isdir(os.path.join(PROJECTS_DIR, buf)):
                    return ("open", buf)
                if cands and cands[0][0][0] <= 10:
                    return ("open", cands[0][1])
                draw_create(scr, buf, cands[0][1] if cands else None)
                while True:
                    k2 = kr.get()
                    if k2 is None:
                        continue
                    if k2 in ("ENTER", "y", "Y"):
                        return ("create", buf)
                    if k2 in ("CTRLC", "ESC", "n", "N", "q"):
                        break
                msg = "cancelled"
                msgcolor = DIM
                continue
            if k == "TAB" or k == "RIGHT":
                cands = candidates(buf)
                g = ghost_for(buf, cands)
                if g:
                    buf = buf + g
                    cur = len(buf)
                continue
            if k == "BACKSPACE":
                if cur > 0:
                    buf = buf[: cur - 1] + buf[cur:]
                    cur -= 1
                continue
            if k == "DELETE":
                if cur < len(buf):
                    buf = buf[:cur] + buf[cur + 1:]
                continue
            if k == "LEFT":
                cur = max(0, cur - 1)
                continue
            if k == "HOME":
                cur = 0
                continue
            if k == "END":
                cur = len(buf)
                continue
            if k == "KILLSTART":
                buf = buf[cur:]
                cur = 0
                continue
            if k == "KILLEND":
                buf = buf[:cur]
                continue
            if k == "KILLWORD":
                i = cur
                while i > 0 and buf[i - 1] == " ":
                    i -= 1
                while i > 0 and buf[i - 1] != " ":
                    i -= 1
                buf = buf[:i] + buf[cur:]
                cur = i
                continue
            if len(k) == 1 and k.isprintable():
                buf = buf[:cur] + k + buf[cur:]
                cur += 1


def fallback():
    try:
        buf = input("project name: ").strip()
    except (EOFError, KeyboardInterrupt):
        return 130
    if not buf:
        return 130
    if os.path.isdir(os.path.join(PROJECTS_DIR, buf)):
        return ("open", buf)
    cands = candidates(buf)
    if cands:
        return ("open", cands[0][1])
    return ("create", buf)


def main():
    try:
        res = run_interactive()
    except KeyboardInterrupt:
        return 130
    if isinstance(res, int):
        return res
    action, name = res
    sys.stdout.write(action + "\t" + name + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())

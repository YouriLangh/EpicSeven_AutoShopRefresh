"""
Small always-on-top dashboard for the Secret Shop refresher.

Tkinter has to own the main thread, so the shop loop runs in a worker thread
and the dashboard polls it. A slow OCR call therefore never freezes the window.

    py -3.9 dashboard.py      # demo with fake numbers, no game needed
"""
import tkinter as tk

BG = "#0f1115"
LINE = "#232734"
TEXT = "#e6e8ee"
MUTED = "#7b8296"
LIME = "#cada37"
GOLD = "#e8b93a"
STONE = "#5cc8e8"
GOOD = "#7bd88f"
FAIR = "#e8b93a"
BAD = "#e06c75"

FONT = ("Segoe UI", 9)
FONT_TITLE = ("Segoe UI Semibold", 10)
FONT_NUM = ("Consolas", 10)
FONT_SMALL = ("Consolas", 8)

LABEL_WIDTH = 10
BAR_HEIGHT = 4
MIN_WIDTH = 300     # content is narrower than this; it just looks better


def hms(seconds):
    """ Seconds to HH:MM:SS. """
    seconds = int(seconds)
    return "%02d:%02d:%02d" % (seconds // 3600, (seconds // 60) % 60, seconds % 60)


def thousands(value):
    return "-" if value is None else "{:,}".format(int(value))


class Dashboard:
    """ The window itself. Feed it dicts from stats_snapshot(). """

    def __init__(self, on_stop=None, title="Secret Shop"):
        self.on_stop = on_stop
        self.stopping = False

        self.root = tk.Tk()
        self.root.title(title)
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", self._stop_and_close)
        self._build()
        self.root.update_idletasks()
        self.root.geometry("%dx%d" % (max(MIN_WIDTH, self.root.winfo_reqwidth()),
                                      self.root.winfo_reqheight()))

    # ---- layout ----
    def _separator(self, parent):
        tk.Frame(parent, bg=LINE, height=1).pack(fill="x", pady=6)

    def _section(self, parent, title):
        tk.Label(parent, text=title, bg=BG, fg=MUTED,
                 font=("Segoe UI Semibold", 8), anchor="w").pack(fill="x")

    def _row(self, parent, label, colour=TEXT, font=FONT_NUM):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=1)
        tk.Label(row, text=label, bg=BG, fg=MUTED, font=FONT,
                 width=LABEL_WIDTH, anchor="w").pack(side="left")
        value = tk.Label(row, text="-", bg=BG, fg=colour, font=font, anchor="e")
        value.pack(side="right")
        return value

    def _build(self):
        pad = tk.Frame(self.root, bg=BG)
        pad.pack(fill="both", expand=True, padx=12, pady=10)

        header = tk.Frame(pad, bg=BG)
        header.pack(fill="x")
        tk.Label(header, text="SECRET SHOP", bg=BG, fg=LIME,
                 font=FONT_TITLE).pack(side="left")
        self.w_status = tk.Label(header, text="starting", bg=BG, fg=MUTED, font=FONT)
        self.w_status.pack(side="right")

        self._separator(pad)

        self.w_refresh = self._row(pad, "Refresh")
        bar_row = tk.Frame(pad, bg=BG)
        bar_row.pack(fill="x", pady=(5, 7))
        # width=1 matters: a tk.Canvas otherwise requests its 378px default
        # and silently sets the whole window width.
        self.bar = tk.Canvas(bar_row, height=BAR_HEIGHT, width=1, bg=LINE,
                             highlightthickness=0, bd=0)
        self.bar.pack(side="left", fill="x", expand=True, pady=3)
        self.bar_fill = self.bar.create_rectangle(0, 0, 0, BAR_HEIGHT,
                                                  fill=LIME, width=0)
        self.w_percent = tk.Label(bar_row, text="0%", bg=BG, fg=LIME,
                                  font=FONT_SMALL, width=6, anchor="e")
        self.w_percent.pack(side="right")

        self._section(pad, "RESOURCES")
        self.w_gold = self._row(pad, "Gold", GOLD)
        self.w_stones = self._row(pad, "Skystones", STONE)
        self.w_burnt = self._row(pad, "Burnt", FAIR)

        self._separator(pad)

        self.w_bookmarks = self._row(pad, "Bookmarks", LIME)
        self.w_mystics = self._row(pad, "Mystics", LIME)
        self.w_ratio = self._row(pad, "vs average")
        self.w_luck = tk.Label(pad, text="waiting for data", bg=BG,
                               fg=MUTED, font=FONT_SMALL, anchor="w")
        self.w_luck.pack(fill="x", pady=(3, 0))

        self._separator(pad)

        footer = tk.Frame(pad, bg=BG)
        footer.pack(fill="x")
        self.w_elapsed = tk.Label(footer, text="00:00:00", bg=BG, fg=MUTED,
                                  font=FONT_NUM)
        self.w_elapsed.pack(side="left")
        self.w_button = tk.Button(footer, text="Stop", command=self._stop,
                                  bg=LINE, fg=TEXT, font=FONT, bd=0,
                                  activebackground=BAD, activeforeground=BG,
                                  padx=14, pady=2, cursor="hand2")
        self.w_button.pack(side="right")

    # ---- stopping ----
    def _stop(self):
        self.stopping = True
        self.w_button.configure(text="Stopping", state="disabled")
        if self.on_stop:
            self.on_stop()

    def _stop_and_close(self):
        self._stop()
        self.root.destroy()

    # ---- updating ----
    def _progress_text(self, s):
        done = s["refreshes"]
        target = s.get("max_refreshes")
        if target:
            return "%s / %s" % (thousands(done), thousands(target))
        return thousands(done)

    def _progress_fraction(self, s):
        target = s.get("max_refreshes")
        if target:
            return min(1.0, s["refreshes"] / float(target))
        limit = s.get("duration_seconds")
        if limit:
            return min(1.0, s["elapsed_seconds"] / float(limit))
        return 0.0

    def _luck(self, s):
        """ Observed hit rate against the community-average rate.
            Returns (ratio label, per-drop detail, colour). """
        n = s["refreshes"]
        if not n:
            return "-", "waiting for data", MUTED

        pairs = [("BM", s["covenant"], s["expected_covenant"]),
                 ("MM", s["mystic"], s["expected_mystic"])]
        parts, ratios = [], []
        for name, hits, expected in pairs:
            actual = hits / float(n)
            parts.append("%s %.2f%%/%.2f%%" % (name, actual * 100, expected * 100))
            if expected:
                ratios.append(actual / expected)

        overall = sum(ratios) / len(ratios) if ratios else 0.0
        colour = GOOD if overall >= 1.0 else (FAIR if overall >= 0.7 else BAD)
        return "%.2fx" % overall, "  ".join(parts), colour

    def update(self, s):
        """ Push one stats_snapshot() dict into the widgets. """
        self.w_status.configure(text=s["status"])
        # Once the worker has actually ended, confirm it on the button.
        # The window itself stays open for verification until X is clicked.
        if s["status"] not in ("running", "starting") and not s["status"].startswith("paused"):
            self.w_button.configure(text="Stopped", state="disabled")
        self.w_refresh.configure(text=self._progress_text(s))
        spent = s["skystones_spent"]
        self.w_burnt.configure(text="0" if not spent else "-%s" % thousands(spent))
        self.w_gold.configure(text=thousands(s["gold"]))
        self.w_stones.configure(text=thousands(s["skystones"]))
        self.w_bookmarks.configure(text=str(s["covenant"]))
        self.w_mystics.configure(text=str(s["mystic"]))
        self.w_elapsed.configure(text=hms(s["elapsed_seconds"]))

        ratio, detail, colour = self._luck(s)
        self.w_ratio.configure(text=ratio, fg=colour)
        self.w_luck.configure(text=detail, fg=MUTED)

        fraction = self._progress_fraction(s)
        self.w_percent.configure(text="%.1f%%" % (fraction * 100))
        width = self.bar.winfo_width()
        self.bar.coords(self.bar_fill, 0, 0, int(width * fraction), BAR_HEIGHT)

    def poll(self, snapshot, interval=250):
        """ Re-read the worker's stats every `interval` ms. """
        def tick():
            try:
                self.update(snapshot())
            except tk.TclError:
                return          # window closed mid-update
            self.root.after(interval, tick)
        self.root.after(0, tick)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    import itertools

    counter = itertools.count()

    def fake():
        i = next(counter)
        refreshes = min(2000, i * 7)
        return {
            "status": "running" if refreshes < 2000 else "refresh limit reached",
            "refreshes": refreshes,
            "max_refreshes": 2000,
            "duration_seconds": 3600,
            "elapsed_seconds": 754 + i,
            "skystones_spent": refreshes * 3,
            "gold": 157939842,
            "skystones": 56882,
            "covenant": refreshes // 100,
            "mystic": refreshes // 320,
            "expected_covenant": 0.042,
            "expected_mystic": 0.011,
        }

    dash = Dashboard()
    dash.poll(fake, interval=200)
    dash.run()

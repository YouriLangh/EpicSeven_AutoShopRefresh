import cv2
import numpy as np
import pytesseract
import mss
import pygetwindow as gw
import pyautogui
import time
from datetime import datetime, timedelta
import re
import os
import threading
from collections import deque

import dashboard

# Tesseract is installed but not on PATH, so point pytesseract at the exe directly.
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

BLUESTACKS = False
WINDOW_START_X = 0
WINDOW_START_Y = 0
CHECK_EVERY = 1000
MINIMUM_GOLD = 7_000_000
MINIMUM_SKYSTONES = 2_000
# Stop conditions. Set either to None to disable it; whichever is reached
# first ends the run. At least one of the two must be set.
RUN_DURATION = timedelta(hours=2)  # e.g. timedelta(minutes=30), or None
MAX_REFRESHES = None  # e.g. 2000, or None
SKYSTONES_PER_REFRESH = 3

# Community-gathered Secret Shop rates - the chance that any single refresh
# contains at least one of these. Derived from epic7db's currency guide:
# ~71 skystones per Covenant Bookmark pack and ~271 per Mystic Medal pack,
# at 3 skystones per refresh. Player-collected, NOT official rates.
EXPECTED_COVENANT_RATE = 0.042  # Covenant Bookmarks, ~1 in 24 refreshes
EXPECTED_MYSTIC_RATE = 0.011  # Mystic Medals, ~1 in 90 refreshes
SCROLL_DELAY = 0.4
POST_CYCLE_DELAY = 1.1
REFRESH_TOGGLE_DELAY = 1.1
POST_REFRESH_DELAY = 1.1
TITLE_BAR_SIZE = 30  # 23 for large screen
POST_BUY_ITEM_CLICK_DELAY = 0.7
REFRESH_SHOP = True
mystic_counter = 0
covenant_counter = 0
number_refreshes = 0

TOP_BAR_SIZE = 20

# Dashboard state, refreshed in place rather than appended to the console.
last_gold = None
last_skystones = None
recent_wishes = deque(maxlen=6)
run_start = None
run_end = None  # set when the run stops; freezes the timer
run_status = "starting"
stop_requested = False

# While background battling is running the game adds an extra icon to the
# top-right cluster, pushing the gold/skystone readout left - and NOT by a
# uniform amount, so each layout gets its own measured regions.
# BACKGROUND_BATTLING is detected once at startup from the swirl icon.
BACKGROUND_BATTLING = True
CURRENCY_REGIONS = {  # (left, top, width, height)
    False: {"gold": (1145, 25, 175, 45), "skystones": (1360, 25, 120, 45)},
    True: {"gold": (1060, 20, 180, 50), "skystones": (1250, 20, 145, 50)},
}

# The background-battling swirl icon occupies a fixed spot in the top bar.
# Template-matching it there is how the active layout is detected (verified
# scores: 0.98 with the icon present, 0.17 against the normal layout).
BB_ICON_SEARCH = (1408, 15, 100, 75)
BB_ICON_THRESHOLD = 0.6
_bb_icon = cv2.imread(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "bb_icon.png"),
    cv2.IMREAD_GRAYSCALE,
)

# Current screen size: 1250 x 733
# TODO: Add a force resize to this size perhaps ^ >> Bottom right corner is poorly captured --> impossible?
# TODO: REplace every exception with a GUI error
# TODO: Convert every pixel position with percentage (function??) based on the window size, but window size is incorrectly captured?


# << Window utils >>#
def get_game_window():
    """Get the correct game window depending on which launcher is being used"""
    window_title = "BlueStacks App Player" if BLUESTACKS else "Epic Seven"
    # getWindowsWithTitle does a SUBSTRING match, so a browser tab called
    # "... Epic Seven - YouTube - Opera" matches too. Require an exact title.
    windows = gw.getWindowsWithTitle(window_title)
    exact = [w for w in windows if w.title.strip() == window_title]
    if exact:
        return exact[0]
    if windows:
        raise Exception(
            "Only partial title matches found (none is the game): "
            + repr([w.title for w in windows])
        )
    raise Exception("Game window not found, please open Epic Seven.")


# << Image processing >>#
def preprocess_image(img):
    """Remove background noise and create a larger differentiation between text"""
    _, thresh = cv2.threshold(
        img, 150, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )  # Binarization
    denoised = cv2.medianBlur(thresh, 3)  # Noise removal
    return denoised


def extract_text(img, is_number):
    """Extract the text from a preprocessed image"""
    preprocessed_img = preprocess_image(img)
    config_numbers = r"--psm 7 -c tessedit_char_whitelist=0123456789,"  # oem of 3 uses default OCR engine mode, psm of 7 assumes it is a single line of text
    config_general = r"--psm 4"

    config = config_numbers if is_number else config_general
    return pytesseract.image_to_string(preprocessed_img, config=config)


def capture_cropped_region(left, top, width, height):
    """
    Capture a specific region of the screen.
    region = {"left": x, "top": y, "width": w, "height": h}
    """
    with mss.MSS() as sct:
        monitor = {
            "left": WINDOW_START_X + left,
            "top": WINDOW_START_Y + top,
            "width": width,
            "height": height,
        }
        screenshot = sct.grab(monitor)
        img = np.array(screenshot)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return img


# Hand-back-the-mouse behaviour: if the cursor is somewhere the bot did not
# put it, the user has taken the mouse. The bot halts at its current step and
# resumes only after the mouse has been still for USER_IDLE_RESUME seconds.
MOUSE_TOLERANCE = 8  # px of drift before it counts as user movement
USER_IDLE_RESUME = 5.0  # seconds of stillness before the bot resumes
user_paused = False
_bot_mouse_lock = threading.Lock()  # held while the bot itself is moving
_expected_pos = None  # where the bot last left the cursor


def bot_move(x, y, duration=0.0):
    """All bot cursor movement goes through here so the watcher can tell
    bot moves apart from user moves."""
    global _expected_pos
    with _bot_mouse_lock:
        pyautogui.moveTo(x, y, duration=duration)
        _expected_pos = (x, y)


def bot_drag(x1, y1, x2, y2, duration):
    global _expected_pos
    with _bot_mouse_lock:
        pyautogui.moveTo(x1, y1)
        pyautogui.mouseDown()
        pyautogui.moveTo(x2, y2, duration=duration)
        pyautogui.mouseUp()
        _expected_pos = (x2, y2)


def _mouse_watcher():
    """Daemon thread: flips user_paused when the cursor strays from where
    the bot left it, and clears it after USER_IDLE_RESUME s of stillness."""
    global user_paused, _expected_pos
    last_pos = pyautogui.position()
    last_move_time = time.time()
    while True:
        time.sleep(0.1)
        pos = pyautogui.position()
        if _bot_mouse_lock.locked():  # bot is moving; not user input
            last_pos = pos
            continue
        if not user_paused:
            if _expected_pos is not None and (
                abs(pos[0] - _expected_pos[0]) > MOUSE_TOLERANCE
                or abs(pos[1] - _expected_pos[1]) > MOUSE_TOLERANCE
            ):
                user_paused = True
                last_pos, last_move_time = pos, time.time()
        else:
            if abs(pos[0] - last_pos[0]) > 2 or abs(pos[1] - last_pos[1]) > 2:
                last_pos, last_move_time = pos, time.time()
            elif time.time() - last_move_time >= USER_IDLE_RESUME:
                _expected_pos = pos  # accept wherever the user left it
                user_paused = False


class StopRun(Exception):
    """Raised inside the worker when the Stop button was pressed."""


def check_stop():
    if stop_requested:
        raise StopRun()
    while user_paused:  # halted until the mouse is idle
        if stop_requested:
            raise StopRun()
        time.sleep(0.1)


def wait(seconds):
    """Interruptible sleep - reacts to the Stop button within ~50ms
    instead of finishing the full delay first."""
    end = time.time() + seconds
    while time.time() < end:
        check_stop()
        time.sleep(0.05)
    check_stop()


# << Click utils >>#
def scroll_shop():
    """Click and drag inside the shop to show more items."""
    check_stop()
    bot_drag(
        WINDOW_START_X + 1000,
        WINDOW_START_Y + 500,
        WINDOW_START_X + 1000,
        WINDOW_START_Y + 50,
        duration=0.4,
    )
    wait(SCROLL_DELAY)


def refresh_shop():  # Already accounts for title_bar size
    """Refreshes the shop."""
    check_stop()
    bot_move(WINDOW_START_X + 375, WINDOW_START_Y + 930)
    pyautogui.click()
    wait(REFRESH_TOGGLE_DELAY)
    bot_move(WINDOW_START_X + 1100, WINDOW_START_Y + 650)
    if REFRESH_SHOP:
        pyautogui.click()
    wait(POST_REFRESH_DELAY)


# << Extra utils >>#
def clean_number(text):
    """Removes `(`   `,`   `\n`   from a given string."""
    return re.sub(r"[\n,(]", "", text)


# << Epic Seven utils >>#
def detect_background_battling():
    """Is the background-battling swirl icon currently in the top bar?
    A wrong-layout crop can still parse as a (wrong) number, so the icon
    is the only trustworthy signal - not the OCR result."""
    if _bb_icon is None:
        return BACKGROUND_BATTLING  # bb_icon.png missing; trust the flag
    area = capture_cropped_region(*BB_ICON_SEARCH)
    score = cv2.matchTemplate(area, _bb_icon, cv2.TM_CCOEFF_NORMED).max()
    return score >= BB_ICON_THRESHOLD


def read_currency(name):
    """Read one top-bar amount from the active layout, with the other
    layout as a last-resort fallback. BACKGROUND_BATTLING is set once
    at startup - the icon stays put until it is clicked away."""
    for mode in (BACKGROUND_BATTLING, not BACKGROUND_BATTLING):
        left, top, width, height = CURRENCY_REGIONS[mode][name]
        text = clean_number(
            extract_text(capture_cropped_region(left, top, width, height), True)
        ).strip()
        if text:
            return float(text)
    raise Exception(
        "OCR read no " + name + " in either top-bar layout - the window size "
        "probably changed. Re-measure CURRENCY_REGIONS."
    )


def get_gold():
    """Retrieves the current amount of gold the player has."""

    return read_currency("gold")


def get_ss():
    """Retrieves the current number of skystones the player has."""
    return read_currency("skystones")


def enough_resources():
    """Check whether the amount of resources the player has are lower than the set thresholds."""
    global last_gold, last_skystones
    last_gold = get_gold()
    last_skystones = get_ss()
    return (last_gold > MINIMUM_GOLD) and (last_skystones > MINIMUM_SKYSTONES)


def process_shop_items(item_count, scroll):
    """Reads shop items, differentiating pre-scroll and post-scroll items."""
    for i in range(item_count):
        read_shop_item(i, scroll)


def stats_snapshot():
    """Everything the dashboard shows, as plain values. Read from the GUI
    thread while the worker thread writes them - all simple assignments."""
    now = run_end or datetime.now()
    elapsed = (now - run_start).total_seconds() if run_start else 0
    status = run_status
    if user_paused and status == "running":
        status = "paused (mouse in use)"
    return {
        "status": status,
        "refreshes": number_refreshes,
        "max_refreshes": MAX_REFRESHES,
        "duration_seconds": RUN_DURATION.total_seconds() if RUN_DURATION else None,
        "elapsed_seconds": elapsed,
        "skystones_spent": number_refreshes * SKYSTONES_PER_REFRESH,
        "gold": last_gold,
        "skystones": last_skystones,
        "covenant": covenant_counter,
        "mystic": mystic_counter,
        "expected_covenant": EXPECTED_COVENANT_RATE,
        "expected_mystic": EXPECTED_MYSTIC_RATE,
    }


def request_stop():
    """Asked for by the dashboard's Stop button or window close."""
    global stop_requested
    stop_requested = True


def run_bot():
    """The shop loop. Runs on a worker thread so the GUI stays responsive."""
    global number_refreshes, run_status, run_end
    try:
        while True:
            if stop_requested:
                run_status = "stopped"
                return
            if RUN_DURATION is not None and datetime.now() - run_start >= RUN_DURATION:
                run_status = "time limit reached"
                return
            if MAX_REFRESHES is not None and number_refreshes >= MAX_REFRESHES:
                run_status = "refresh limit reached"
                return
            run_status = "running"
            buy_shop()
            number_refreshes += 1
    except StopRun:
        run_status = "stopped"
    except Exception as error:
        run_status = str(error)
    finally:
        run_end = datetime.now()


def buy_shop():
    """Handles buying items from the shop, refreshing when needed."""
    if number_refreshes % CHECK_EVERY == 0:
        if not (enough_resources()):
            raise Exception("Insufficient resources, shop refreshing stopped.")

    process_shop_items(
        2, scroll=False
    )  # Nr of items to buy from (used for coordinate estimation)

    scroll_shop()

    process_shop_items(5, scroll=True)

    # print(POST_CYCLE_DELAY)
    # Refresh the shop
    refresh_shop()


# TODO: Fix pixel positions


def read_shop_item(item, scroll):
    check_stop()
    top = 151 - TOP_BAR_SIZE
    item_height = 140
    padding = 55
    button_center = 80
    item_left = 1000
    item_width = 400

    if scroll:
        top = 277 - TOP_BAR_SIZE  # title-bar size already deduced
    top = top + (item * 205)
    for_sale = capture_cropped_region(item_left, top, item_width, item_height)
    item_text = extract_text(for_sale, False)
    # print(item_text)
    # if "Summon" not in item_text:
    #     return  # Early exit if "Summon" is not in text

    is_covenant = "Covenant" in item_text and "Bookmarks" in item_text
    is_mystic = "Mystic" in item_text and "Medals" in item_text

    if not (is_covenant or is_mystic):
        return  # If neither, exit function

    # Buy the summon
    bot_move(WINDOW_START_X + 1700, WINDOW_START_Y + top + 100)  # Button center
    pyautogui.click()

    wait(POST_BUY_ITEM_CLICK_DELAY)

    bot_move(WINDOW_START_X + 1115, WINDOW_START_Y + 730)
    pyautogui.click()

    # Update the appropriate counter
    global covenant_counter, mystic_counter
    if is_covenant:
        covenant_counter += 1
    else:
        mystic_counter += 1
    recent_wishes.append(
        (
            datetime.now().strftime("%H:%M:%S"),
            "Covenant Bookmarks" if is_covenant else "Mystic Medals",
        )
    )
    wait(2)


# py -3.9 main.py
if __name__ == "__main__":
    # top = tkinter.Tk()
    # top.mainloop()
    if RUN_DURATION is None and MAX_REFRESHES is None:
        raise Exception(
            "Set RUN_DURATION, MAX_REFRESHES or both - "
            "with neither set the run would never stop."
        )

    game_window = get_game_window()
    WINDOW_START_X = game_window.left
    WINDOW_START_Y = game_window.top + TITLE_BAR_SIZE
    BACKGROUND_BATTLING = detect_background_battling()
    # print("Background battling detected:", BACKGROUND_BATTLING)
    bot_move(WINDOW_START_X + 5, WINDOW_START_Y - 10)
    pyautogui.click()

    threading.Thread(target=_mouse_watcher, daemon=True).start()

    run_start = datetime.now()
    view = dashboard.Dashboard(on_stop=request_stop)
    worker = threading.Thread(target=run_bot, daemon=True)
    worker.start()
    view.poll(stats_snapshot)
    view.run()  # blocks here until the window is closed
    request_stop()
    worker.join(timeout=10)
    # print(run_status)

import cv2
import numpy as np
import pytesseract
import mss
import pygetwindow as gw
import pyautogui
import time
from datetime import datetime,timedelta
import re
import tkinter
import sys
import ctypes
from collections import deque

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
RUN_DURATION = timedelta(hours=1)   # e.g. timedelta(minutes=30), or None
MAX_REFRESHES = None                # e.g. 2000, or None
SKYSTONES_PER_REFRESH = 3
MAX_RECENT_WISHES = 6               # how many purchases the dashboard lists
SCROLL_DELAY = 0.4
POST_CYCLE_DELAY = 1.1
REFRESH_TOGGLE_DELAY = 1.1
POST_REFRESH_DELAY = 1.1
TITLE_BAR_SIZE = 30  # 23 for large screen
POST_BUY_ITEM_CLICK_DELAY = 0.7
REFRESH_SHOP= True
mystic_counter = 0
covenant_counter = 0
number_refreshes = 0

TOP_BAR_SIZE = 20

# Dashboard state, refreshed in place rather than appended to the console.
last_gold = None
last_skystones = None
recent_wishes = deque(maxlen=MAX_RECENT_WISHES)

# While background battling is running the game adds an extra icon to the
# top-right cluster, which pushes the gold/skystone readout one icon further
# to the left. Measured icon pitch is 82px (48px icon + 34px padding).
BACKGROUND_BATTLING = False
ICON_PITCH = 82

# Current screen size: 1250 x 733 
#TODO: Add a force resize to this size perhaps ^ >> Bottom right corner is poorly captured --> impossible?
# TODO: REplace every exception with a GUI error
# TODO: Convert every pixel position with percentage (function??) based on the window size, but window size is incorrectly captured?

#<< Console dashboard >>#
# The dashboard is redrawn in place: every render moves the cursor back up
# over the previous one, so the console shows one live table instead of a
# growing wall of text. Height is kept constant so nothing is left behind.
_ESC = "\033["
_ansi_ok = False
_box = None
_last_height = 0

TABLE_WIDTH = 46

C_RESET = _ESC + "0m"
C_DIM = _ESC + "38;5;244m"
C_TITLE = _ESC + "1;38;5;186m"
C_GOLD = _ESC + "38;5;220m"
C_STONE = _ESC + "38;5;81m"
C_WISH = _ESC + "1;38;5;156m"
C_FRAME = _ESC + "38;5;240m"
C_WISHFRAME = _ESC + "38;5;156m"

ASCII_BOX = {"tl": "+", "tr": "+", "bl": "+", "br": "+",
             "h": "-", "v": "|", "ml": "+", "mr": "+"}
UNICODE_BOX = {"tl": "\u250c", "tr": "\u2510", "bl": "\u2514", "br": "\u2518",
               "h": "\u2500", "v": "\u2502", "ml": "\u251c", "mr": "\u2524"}


def enable_console_colour():
    """ Switch on ANSI handling and UTF-8 output; conhost needs both asking for. """
    global _ansi_ok, _box
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            # 0x0004 = ENABLE_VIRTUAL_TERMINAL_PROCESSING
            _ansi_ok = bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
        kernel32.SetConsoleOutputCP(65001)
    except Exception:
        _ansi_ok = False
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    _box = _pick_box()
    return _ansi_ok


def _pick_box():
    """ Unicode box drawing if the console can encode it, plain ASCII if not. """
    try:
        "".join(UNICODE_BOX.values()).encode(sys.stdout.encoding or "ascii")
        return UNICODE_BOX
    except (UnicodeEncodeError, LookupError, TypeError):
        return ASCII_BOX


def paint(text, colour):
    """ Wrap text in an ANSI colour, or return it untouched on a plain console. """
    return (colour + text + C_RESET) if _ansi_ok else text


def _rule(left, right, colour=C_FRAME):
    return paint(left + _box["h"] * TABLE_WIDTH + right, colour)


def _line(text, colour=None, frame=C_FRAME):
    """ One padded table row. Text is padded before colouring so escape codes
        never count towards the width. """
    body = text + " " * max(0, TABLE_WIDTH - len(text))
    if colour:
        body = paint(body, colour)
    edge = paint(_box["v"], frame)
    return edge + body + edge


def _stat(label, value, colour=None, frame=C_FRAME):
    return _line("  %-23s%s" % (label, value), colour, frame)


def _hms(delta):
    seconds = int(delta.total_seconds())
    return "%02d:%02d:%02d" % (seconds // 3600, (seconds // 60) % 60, seconds % 60)


def _amount(value):
    return "?" if value is None else "{:,}".format(int(value))


def _progress():
    if MAX_REFRESHES:
        return "{:,} / {:,}".format(number_refreshes, MAX_REFRESHES)
    return "{:,}".format(number_refreshes)


def _build_dashboard(start_time, status):
    box = _box
    lines = [_rule(box["tl"], box["tr"]),
             _line("  EPIC SEVEN " + box["h"] + " SECRET SHOP", C_TITLE),
             _rule(box["ml"], box["mr"]),
             _stat("Elapsed", _hms(datetime.now() - start_time)),
             _stat("Refreshes", _progress()),
             _stat("Skystones spent",
                   "{:,}".format(number_refreshes * SKYSTONES_PER_REFRESH)),
             _stat("Gold", _amount(last_gold), C_GOLD),
             _stat("Skystones", _amount(last_skystones), C_STONE),
             _stat("Status", status or "running", C_DIM)]

    # The wishes get their own coloured frame so they stand out from the stats.
    total = covenant_counter + mystic_counter
    lines.append(_rule(box["ml"], box["mr"], C_WISHFRAME))
    lines.append(_stat("WISHES", "%d total" % total, C_WISH, C_WISHFRAME))
    lines.append(_stat("  Covenant Bookmarks", str(covenant_counter),
                       C_WISH, C_WISHFRAME))
    lines.append(_stat("  Mystic Medals", str(mystic_counter),
                       C_WISH, C_WISHFRAME))

    newest = list(reversed(recent_wishes))
    for i in range(MAX_RECENT_WISHES):
        if i < len(newest):
            stamp, name = newest[i]
            lines.append(_line("    %s  %s" % (stamp, name), C_DIM, C_WISHFRAME))
        else:
            lines.append(_line("", None, C_WISHFRAME))
    lines.append(_rule(box["bl"], box["br"], C_WISHFRAME))
    return lines


def render_dashboard(start_time, status=""):
    """ Redraw the table over the previous one instead of appending to it. """
    global _last_height
    if _box is None:
        enable_console_colour()
    lines = _build_dashboard(start_time, status)
    out = []
    if _last_height and _ansi_ok:
        out.append(_ESC + str(_last_height) + "A")   # cursor back to the top
    for line in lines:
        if _ansi_ok:
            out.append(_ESC + "2K")                  # wipe the old row
        out.append(line + "\n")
    sys.stdout.write("".join(out))
    sys.stdout.flush()
    _last_height = len(lines)


#<< Window utils >>#
def get_game_window():
    """ Get the correct game window depending on which launcher is being used """
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
            + repr([w.title for w in windows]))
    raise Exception("Game window not found, please open Epic Seven.")

#<< Image processing >>#
def preprocess_image(img):
    """ Remove background noise and create a larger differentiation between text """
    _, thresh = cv2.threshold(img, 150, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)  # Binarization
    denoised = cv2.medianBlur(thresh, 3)  # Noise removal
    return denoised

def extract_text(img, is_number):
    """ Extract the text from a preprocessed image """
    preprocessed_img = preprocess_image(img)
    config_numbers = r'--psm 7 -c tessedit_char_whitelist=0123456789,' # oem of 3 uses default OCR engine mode, psm of 7 assumes it is a single line of text
    config_general = r'--psm 4'

    config = config_numbers if is_number else config_general
    return pytesseract.image_to_string(preprocessed_img, config=config)

def capture_cropped_region(left, top, width, height):
    """
    Capture a specific region of the screen.
    region = {"left": x, "top": y, "width": w, "height": h}
    """
    with mss.mss() as sct:
        monitor = {
            "left": WINDOW_START_X + left,
            "top": WINDOW_START_Y + top,
            "width": width,
            "height": height
        }
        screenshot = sct.grab(monitor)
        img = np.array(screenshot)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return img



#<< Click utils >>#
def scroll_shop():
    """ Click and drag inside the shop to show more items. """
    pyautogui.moveTo(WINDOW_START_X + 1000, WINDOW_START_Y + 500)  # Move to start position
    pyautogui.mouseDown()  # Click
    pyautogui.moveTo(WINDOW_START_X + 1000, WINDOW_START_Y + 50 , duration=0.4)  # Drag
    pyautogui.mouseUp()  # Release mouse
    time.sleep(SCROLL_DELAY)

def refresh_shop(): #Already accounts for title_bar size
    """ Refreshes the shop. """
    pyautogui.moveTo(WINDOW_START_X + 375, WINDOW_START_Y + 930)
    pyautogui.click()
    time.sleep(REFRESH_TOGGLE_DELAY)
    pyautogui.moveTo(WINDOW_START_X + 1100, WINDOW_START_Y + 650)
    if(REFRESH_SHOP): pyautogui.click()
    time.sleep(POST_REFRESH_DELAY)

#<< Extra utils >>#
def clean_number(text):
    """ Removes `(`   `,`   `\n`   from a given string. """
    return re.sub(r"[\n,(]", "", text)


#<< Epic Seven utils >>#
def currency_offset():
    """ Horizontal shift of the gold/skystone readout for the current top bar. """
    return -ICON_PITCH if BACKGROUND_BATTLING else 0

def get_gold():
    """ Retrieves the current amount of gold the player has. """

    gold_string = extract_text(capture_cropped_region(left=1145 + currency_offset(), top= 25, width= 175, height= 45), True)
    return float(clean_number(gold_string))

def get_ss():

    """ Retrieves the current number of skystones the player has. """
    skystones_string = extract_text(capture_cropped_region(left=1360 + currency_offset(), top= 25, width= 120, height= 45), True)
    return float(clean_number(skystones_string))

def enough_resources():
    """ Check whether the amount of resources the player has are lower than the set thresholds."""
    global last_gold, last_skystones
    last_gold = get_gold()
    last_skystones = get_ss()
    return (last_gold > MINIMUM_GOLD) and (last_skystones > MINIMUM_SKYSTONES)
    
def process_shop_items(item_count, scroll):
    """Reads shop items, differentiating pre-scroll and post-scroll items."""
    for i in range(item_count):
        read_shop_item(i, scroll)


def buy_shop():
    """Handles buying items from the shop, refreshing when needed."""
    if number_refreshes % CHECK_EVERY == 0:
        if not(enough_resources()):
            raise Exception("Insufficient resources, shop refreshing stopped.")

    process_shop_items(2, scroll=False) # Nr of items to buy from (used for coordinate estimation)

    scroll_shop()

    process_shop_items(5, scroll=True)


    # print(POST_CYCLE_DELAY)
    # Refresh the shop
    refresh_shop()

#TODO: Fix pixel positions

def read_shop_item(item, scroll):
    top = 151 - TOP_BAR_SIZE
    item_height = 140
    padding = 55
    button_center = 80
    item_left = 1000
    item_width = 400

    if(scroll):
        top = 277 - TOP_BAR_SIZE #title-bar size already deduced
    top = top + (item * 205)
    for_sale = capture_cropped_region(item_left,top,item_width,item_height)
    item_text = extract_text(for_sale, False)
    # print(item_text)
    # if "Summon" not in item_text:
    #     return  # Early exit if "Summon" is not in text
    
    is_covenant = "Covenant" in item_text and "Bookmarks" in item_text
    is_mystic = "Mystic" in item_text and "Medals" in item_text

    if not (is_covenant or is_mystic):
        return  # If neither, exit function

    # Buy the summon
    pyautogui.moveTo(WINDOW_START_X + 1700, WINDOW_START_Y + top + 100) # Button center
    pyautogui.click()

    time.sleep(POST_BUY_ITEM_CLICK_DELAY)

    pyautogui.moveTo(WINDOW_START_X  + 1115, WINDOW_START_Y + 730)
    pyautogui.click()

    # Update the appropriate counter
    global covenant_counter, mystic_counter
    if is_covenant:
        covenant_counter += 1
    else:
        mystic_counter += 1 
    recent_wishes.append((datetime.now().strftime("%H:%M:%S"),
                          "Covenant Bookmarks" if is_covenant else "Mystic Medals"))
    time.sleep(2)

# py -3.9 main.py
if __name__ == "__main__":
    # top = tkinter.Tk()
    # top.mainloop()
    if RUN_DURATION is None and MAX_REFRESHES is None:
        raise Exception("Set RUN_DURATION, MAX_REFRESHES or both - "
                        "with neither set the run would never stop.")

    game_window = get_game_window()
    WINDOW_START_X = game_window.left
    WINDOW_START_Y = game_window.top + TITLE_BAR_SIZE
    pyautogui.moveTo(WINDOW_START_X + 5, WINDOW_START_Y - 10)
    pyautogui.click()

    enable_console_colour()
    start = datetime.now()
    reason = "done"
    render_dashboard(start)
    try:
        while True:
            if RUN_DURATION is not None and datetime.now() - start >= RUN_DURATION:
                reason = "time limit reached"
                break
            if MAX_REFRESHES is not None and number_refreshes >= MAX_REFRESHES:
                reason = "refresh limit reached"
                break
            buy_shop()
            number_refreshes += 1
            render_dashboard(start)
    except KeyboardInterrupt:
        reason = "stopped by user"
    except Exception as error:
        reason = str(error)
    render_dashboard(start, reason)



import cv2
import numpy as np
import pytesseract
import mss
import pygetwindow as gw
import pyautogui
import time
from datetime import datetime,timedelta
import re
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
RUN_DURATION = timedelta(hours=1)   # e.g. timedelta(minutes=30), or None
MAX_REFRESHES = None                # e.g. 2000, or None
SKYSTONES_PER_REFRESH = 3

# Community-gathered Secret Shop rates - the chance that any single refresh
# contains at least one of these. These are player-collected figures from
# Reddit threads and community spreadsheets, NOT official published rates,
# and different data sets disagree. Adjust to whatever numbers you trust.
EXPECTED_COVENANT_RATE = 0.05    # Covenant Bookmarks, ~1 in 20 refreshes
EXPECTED_MYSTIC_RATE = 0.025     # Mystic Medals, ~1 in 40 refreshes
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
recent_wishes = deque(maxlen=6)
run_start = None
run_status = "starting"
stop_requested = False

# While background battling is running the game adds an extra icon to the
# top-right cluster, which pushes the gold/skystone readout one icon further
# to the left. Measured icon pitch is 82px (48px icon + 34px padding).
BACKGROUND_BATTLING = False
ICON_PITCH = 82

# Current screen size: 1250 x 733 
#TODO: Add a force resize to this size perhaps ^ >> Bottom right corner is poorly captured --> impossible?
# TODO: REplace every exception with a GUI error
# TODO: Convert every pixel position with percentage (function??) based on the window size, but window size is incorrectly captured?

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


def stats_snapshot():
    """ Everything the dashboard shows, as plain values. Read from the GUI
        thread while the worker thread writes them - all simple assignments. """
    elapsed = (datetime.now() - run_start).total_seconds() if run_start else 0
    return {
        "status": run_status,
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
    """ Asked for by the dashboard's Stop button or window close. """
    global stop_requested
    stop_requested = True


def run_bot():
    """ The shop loop. Runs on a worker thread so the GUI stays responsive. """
    global number_refreshes, run_status
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
    except Exception as error:
        run_status = str(error)


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

    run_start = datetime.now()
    view = dashboard.Dashboard(on_stop=request_stop)
    worker = threading.Thread(target=run_bot, daemon=True)
    worker.start()
    view.poll(stats_snapshot)
    view.run()          # blocks here until the window is closed
    request_stop()
    worker.join(timeout=10)
    print(run_status)

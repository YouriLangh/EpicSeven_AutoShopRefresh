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

# Tesseract is installed but not on PATH, so point pytesseract at the exe directly.
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

BLUESTACKS = False
WINDOW_START_X = 0
WINDOW_START_Y = 0
CHECK_EVERY = 1000
MINIMUM_GOLD = 1_000_000
MINIMUM_SKYSTONES = 2_000
PRINT_EVERY = 100
SCROLL_DELAY = 0.4
POST_CYCLE_DELAY = 1.1
REFRESH_TOGGLE_DELAY = 1.1
POST_REFRESH_DELAY = 1.1
TITLE_BAR_SIZE = 30  # 23 for large screen

# Screen geometry, calibrated against a maximised 1936x1056 game window
# (1920x1080 monitor). All values are relative to WINDOW_START_X/Y.
# Re-derive them with calibrate.py if the window size ever changes.
GOLD_REGION = (1145, 25, 175, 45)       # left, top, width, height
SKYSTONE_REGION = (1360, 25, 120, 45)
ITEM_LEFT = 1030
ITEM_WIDTH = 400
ITEM_HEIGHT = 130
ITEM_PITCH = 204                        # vertical distance between shop rows
ITEM_TOP = 135                          # first row, before scrolling
ITEM_TOP_SCROLLED = 60                  # first row, after scroll_shop()
BUY_X = 1745                            # centre of the green Buy button
BUY_OFFSET_Y = 98                       # Buy centre, relative to the row top
REFRESH_BUTTON = (370, 935)             # green Refresh button
# NOT YET CALIBRATED - these two dialogs only exist mid-purchase/mid-refresh,
# so they could not be measured from a static screenshot. Verify before use.
REFRESH_CONFIRM = (1100, 650)           # "confirm refresh" button in the popup
BUY_CONFIRM = (1115, 730)               # "confirm purchase" button in the popup
POST_BUY_ITEM_CLICK_DELAY = 0.7
REFRESH_SHOP= False
mystic_counter = 0
covenant_counter = 0
number_refreshes = 0



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
    pyautogui.moveTo(WINDOW_START_X + 1400, WINDOW_START_Y + 770)  # Move to start position
    pyautogui.mouseDown()  # Click
    pyautogui.moveTo(WINDOW_START_X + 1400, WINDOW_START_Y + 370, duration=0.2)  # Drag
    pyautogui.mouseUp()  # Release mouse
    time.sleep(SCROLL_DELAY)

def refresh_shop(): #Already accounts for title_bar size
    """ Refreshes the shop. """
    pyautogui.moveTo(WINDOW_START_X + REFRESH_BUTTON[0], WINDOW_START_Y + REFRESH_BUTTON[1])
    pyautogui.click()
    time.sleep(REFRESH_TOGGLE_DELAY)
    pyautogui.moveTo(WINDOW_START_X + REFRESH_CONFIRM[0], WINDOW_START_Y + REFRESH_CONFIRM[1])
    if(REFRESH_SHOP): pyautogui.click()
    time.sleep(POST_REFRESH_DELAY)

#<< Extra utils >>#
def clean_number(text):
    """ Removes `(`   `,`   `\n`   from a given string. """
    return re.sub(r"[\n,(]", "", text)


def to_number(text, label):
    """ Turn an OCR'd number into a float, or explain why it could not be read. """
    cleaned = clean_number(text).strip()
    if not cleaned:
        raise Exception(
            "OCR read no " + label + " - the capture region is almost certainly "
            "misaligned for this window size. Run calibrate.py to re-derive it.")
    return float(cleaned)


#<< Epic Seven utils >>#
def get_gold():
    """ Retrieves the current amount of gold the player has. """

    left, top, width, height = GOLD_REGION
    gold_string = extract_text(capture_cropped_region(left, top, width, height), True)
    return to_number(gold_string, "gold")

def get_ss():

    """ Retrieves the current number of skystones the player has. """
    left, top, width, height = SKYSTONE_REGION
    skystones_string = extract_text(capture_cropped_region(left, top, width, height), True)
    return to_number(skystones_string, "skystones")

def enough_resources():
    """ Check whether the amount of resources the player has are lower than the set thresholds."""
    gold = get_gold()
    skystones = get_ss()
    print(f"Gold: {gold}, Skystones: {skystones}")
    return (gold > MINIMUM_GOLD) and (skystones > MINIMUM_SKYSTONES)
    
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


    print(POST_CYCLE_DELAY)
    # Refresh the shop
    refresh_shop()

#TODO: Fix pixel positions

def read_shop_item(item, scroll):
    top = ITEM_TOP_SCROLLED if scroll else ITEM_TOP
    top = top + (item * ITEM_PITCH)
    for_sale = capture_cropped_region(ITEM_LEFT, top, ITEM_WIDTH, ITEM_HEIGHT)
    item_text = extract_text(for_sale, False)
    print(item_text)
    # if "Summon" not in item_text:
    #     return  # Early exit if "Summon" is not in text
    
    is_covenant = "Covenant" in item_text and "Bookmarks" in item_text
    is_mystic = "Mystic" in item_text and "Medals" in item_text

    if not (is_covenant or is_mystic):
        return  # If neither, exit function

    # Buy the summon
    pyautogui.moveTo(WINDOW_START_X + BUY_X, WINDOW_START_Y + top + BUY_OFFSET_Y) # Button center
    pyautogui.click()

    time.sleep(POST_BUY_ITEM_CLICK_DELAY)

    pyautogui.moveTo(WINDOW_START_X + BUY_CONFIRM[0], WINDOW_START_Y + BUY_CONFIRM[1])
    pyautogui.click()

    # Update the appropriate counter
    global covenant_counter, mystic_counter
    if is_covenant:
        covenant_counter += 1
    else:
        mystic_counter += 1 
    time.sleep(2)


if __name__ == "__main__":
    # top = tkinter.Tk()
    # top.mainloop()
    game_window = get_game_window()
    WINDOW_START_X = game_window.left
    WINDOW_START_Y = game_window.top + TITLE_BAR_SIZE
    pyautogui.moveTo(WINDOW_START_X, WINDOW_START_Y - 10)
    pyautogui.click()

    start = datetime.now()
    end_time = start + timedelta(minutes=30)
    while datetime.now() < end_time:
        buy_shop()
        number_refreshes +=1
        if number_refreshes % PRINT_EVERY == 0:
            print(f"{covenant_counter} Covenent BMs bought and {mystic_counter} Mystics bought")



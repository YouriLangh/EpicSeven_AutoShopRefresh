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

BLUESTACKS = False
WINDOW_START_X = 0
WINDOW_START_Y = 0
CHECK_EVERY = 1000
MINIMUM_GOLD = 10_000_000
MINIMUM_SKYSTONES = 2_000
PRINT_EVERY = 100
SCROLL_DELAY = 0.3
POST_CYCLE_DELAY = 1
REFRESH_TOGGLE_DELAY = 1
POST_REFRESH_DELAY = 1
TITLE_BAR_SIZE = 30  # 23 for large screen
POST_BUY_ITEM_CLICK_DELAY = 0.6

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
    windows = gw.getWindowsWithTitle(window_title) 
    if windows:
        return windows[0]
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
    pyautogui.moveTo(WINDOW_START_X + 700, WINDOW_START_Y + 400)  # Move to start position
    pyautogui.mouseDown()  # Click
    pyautogui.moveTo(WINDOW_START_X + 700, WINDOW_START_Y + 400 + -200, duration=0.2)  # Drag
    pyautogui.mouseUp()  # Release mouse
    time.sleep(SCROLL_DELAY)

def refresh_shop(): #Already accounts for title_bar size
    """ Refreshes the shop. """
    pyautogui.moveTo(WINDOW_START_X + 235, WINDOW_START_Y + 650)
    pyautogui.click()
    time.sleep(REFRESH_TOGGLE_DELAY)
    pyautogui.moveTo(WINDOW_START_X + 720, WINDOW_START_Y + 430)
    #pyautogui.click()
    time.sleep(POST_REFRESH_DELAY)

#<< Extra utils >>#
def clean_number(text):
    """ Removes `(`   `,`   `\n`   from a given string. """
    return re.sub(r"[\n,(]", "", text)


#<< Epic Seven utils >>#
def get_gold():
    """ Retrieves the current amount of gold the player has. """
    gold_string = extract_text(capture_cropped_region(left=785, top= 17, width= 110, height= 30), True)
    return float(clean_number(gold_string))

def get_ss():
    """ Retrieves the current number of skystones the player has. """
    skystones_string = extract_text(capture_cropped_region(left=927, top= 17, width= 75, height= 30), True)
    return float(clean_number(skystones_string))

def enough_resources():
    """ Check whether the amount of resources the player has are lower than the set thresholds."""
    gold = get_gold()
    skystones = get_ss()
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
    top = 113 - TITLE_BAR_SIZE
    item_height = 103
    padding = 37
    button_center = 80
    item_left = 652
    item_width = 450
    item_height = 122
    if(scroll):
        top = 154 #title-bar size already deduced
    top = top + (item * 140)
    for_sale = capture_cropped_region(item_left,top,item_width,item_height)
    item_text = extract_text(for_sale, False)
    print(item_text)
    if "Summon" not in item_text:
        return  # Early exit if "Summon" is not in text
    
    is_covenant = "Covenant" in item_text and "Bookmarks" in item_text
    is_mystic = "Mystic" in item_text and "Medals" in item_text

    if not (is_covenant or is_mystic):
        return  # If neither, exit function

    # Buy the summon
    pyautogui.moveTo(WINDOW_START_X + 1116, WINDOW_START_Y + top + 80) # Button center
    pyautogui.click()

    time.sleep(POST_BUY_ITEM_CLICK_DELAY)

    pyautogui.moveTo(WINDOW_START_X  + 690, WINDOW_START_Y + 490)
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

    start = datetime.now()
    end_time = start + timedelta(seconds=10)
    while datetime.now() < end_time:
        buy_shop()
        number_refreshes +=1
        if number_refreshes % PRINT_EVERY == 0:
            print(f"{covenant_counter} Covenent BMs bought and {mystic_counter} Mystics bought")



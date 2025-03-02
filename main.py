import cv2
import numpy as np
import pytesseract
import mss
import pygetwindow as gw
import pyautogui
import time
from datetime import datetime,timedelta
import keyboard


def get_game_window():
    windows = gw.getWindowsWithTitle("BlueStacks App Player")  # Find the game window
    if windows:
        return windows[0]
    return None

def extract_text(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)  # Convert to grayscale
    text = pytesseract.image_to_string(gray)
    return text

def relative_click_and_drag():
    """Click and drag inside the BlueStacks window."""
    game_window = get_game_window()
    if game_window:
        base_x, base_y = game_window.left, game_window.top
        pyautogui.moveTo(game_window.left + 700, game_window.top + 400)  # Move to start position
        pyautogui.mouseDown()  # Click
        pyautogui.moveTo(game_window.left + 700, game_window.top + 400 + -300, duration=0.2)  # Drag
        pyautogui.mouseUp()  # Release mouse


def scroll_shop():
    game_window = get_game_window()
    if not game_window:
        print("Epic Seven window not found!")
        return None
    pyautogui.moveTo(game_window.left, game_window.top)
    pyautogui.moveTo(game_window.left + 700, game_window.top + 400)
    relative_click_and_drag()
    time.sleep(0.5)

def capture_cropped_region(left, top, width, height):
    """
    Capture a specific region of the screen.
    region = {"left": x, "top": y, "width": w, "height": h}
    """
    game_window = get_game_window()
    if not game_window:
        print("Epic Seven window not found!")
        return None
    with mss.mss() as sct:
        monitor = {
            "left": game_window.left + left,
            "top": game_window.top + top,
            "width": width,
            "height": height
        }
        screenshot = sct.grab(monitor)
        img = np.array(screenshot)
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)  # Convert to BGR
        return img

def get_gold():
    gold_string = extract_text(capture_cropped_region(left=795, top= 51, width= 110, height= 60))
    return float(gold_string.strip('\n').strip('').replace(',', ''))

def get_ss():
    gold_string = extract_text(capture_cropped_region(left=935, top= 51, width= 70, height= 60))
    return float(gold_string.strip('\n').strip('').replace(',', ''))

def read_shop_item(item, scroll):
    top = 125
    if(scroll):
        top += 65
    top = top + (item * 135)
    for_sale = capture_cropped_region(652,top,310,110)
    item_text = extract_text(for_sale)
    print(item_text)
    if ("Covenant" in item_text and "Bookmarks" in item_text and "Summon" in item_text) or ("Mystic" in item_text and "Medals" in item_text and "Summon" in item_text):
        print("I found something")
        game_window = get_game_window()
        pyautogui.moveTo(game_window.left + 1115, game_window.top + top + 75)
        pyautogui.click()
        time.sleep(1)
        pyautogui.moveTo(game_window.left + 700, game_window.top + 530)
        pyautogui.click()
        time.sleep(2.5)

def buy_shop():
    gold = get_gold()
    skystones = get_ss()
    print(skystones)
    print(gold)
    if gold < 10_000_000 or skystones < 2_000:
        return
    for i in range(2):
        read_shop_item(i, False)
    scroll_shop()
    for i in range(5):
        read_shop_item(i, True)
    time.sleep(1)
    game_window = get_game_window()

    # Refresh the shop
    pyautogui.moveTo(game_window.left + 235, game_window.top + 680)
    pyautogui.click()
    time.sleep(0.5)
    pyautogui.moveTo(game_window.left + 720, game_window.top + 460)
    time.sleep(0.5)
    #pyautogui.click()
    time.sleep(1)

if __name__ == "__main__":
    buy_shop()
    # start = datetime.now()
    # end_time = start + timedelta(hours=0.5)
    # while datetime.now() < end_time:
    #     buy_shop()

    


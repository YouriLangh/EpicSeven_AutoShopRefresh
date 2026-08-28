"""
Read-only calibration helper. Moves nothing and clicks nothing - it just
captures the game window, reports its geometry, and shows what main.py's
capture regions currently see.

Run it whenever the game window size changes and the OCR starts coming back
empty, then copy the corrected numbers into main.py's geometry block.

    py -3.9 calibrate.py
"""
import cv2
import numpy as np

import main as e7


def dump_window():
    """ Save a full screenshot of the game window and report its geometry. """
    window = e7.get_game_window()
    print("window title : " + repr(window.title))
    print("position     : left=%d top=%d" % (window.left, window.top))
    print("size         : %dx%d" % (window.width, window.height))

    e7.WINDOW_START_X = window.left
    e7.WINDOW_START_Y = window.top + e7.TITLE_BAR_SIZE
    print("capture origin: x=%d y=%d (top + TITLE_BAR_SIZE)"
          % (e7.WINDOW_START_X, e7.WINDOW_START_Y))

    # Grab the whole window in the same coordinate frame the regions use.
    full = e7.capture_cropped_region(
        0, -e7.TITLE_BAR_SIZE, window.width, window.height)
    cv2.imwrite("calibration_window.png", full)
    print("wrote calibration_window.png")
    print("  region (left, top) maps to pixel (left, top + %d) in that file"
          % e7.TITLE_BAR_SIZE)
    return full


def show(label, region, is_number):
    """ OCR one region and save the exact crop that was read. """
    left, top, width, height = region
    img = e7.capture_cropped_region(left, top, width, height)
    cv2.imwrite("calibration_%s.png" % label, e7.preprocess_image(img))
    text = e7.extract_text(img, is_number).strip()
    status = "OK " if text else "EMPTY <- misaligned"
    print("  %-14s %-22s %s %s" % (label, str(region), status, repr(text)))


if __name__ == "__main__":
    dump_window()

    print("\nresources:")
    show("gold", e7.GOLD_REGION, True)
    show("skystones", e7.SKYSTONE_REGION, True)

    print("\nshop rows (before scrolling):")
    for i in range(5):
        show("row%d" % i,
             (e7.ITEM_LEFT, e7.ITEM_TOP + i * e7.ITEM_PITCH,
              e7.ITEM_WIDTH, e7.ITEM_HEIGHT), False)

    print("\nEvery row above should name the item sitting in it.")
    print("If a row is EMPTY or shows the wrong item, adjust ITEM_TOP /")
    print("ITEM_PITCH in main.py and re-run. Scroll the shop by hand first")
    print("to calibrate ITEM_TOP_SCROLLED the same way.")

import cv2
import numpy as np
from PIL import ImageGrab
import config
import ctypes
from ctypes import wintypes

try:
    ctypes.windll.user32.SetProcessDPIAware()
except:
    pass

# Global bounding box cache to completely eliminate lag during the mini-game
GAME_BBOX = None
user32 = ctypes.windll.user32


def lock_active_window():
    """Calculates and caches the game window client boundaries once on startup."""
    global GAME_BBOX
    hwnd = user32.GetForegroundWindow()
    if hwnd:
        rect = wintypes.RECT()
        if user32.GetClientRect(hwnd, ctypes.byref(rect)):
            pt_topleft = wintypes.POINT(rect.left, rect.top)
            pt_bottomright = wintypes.POINT(rect.right, rect.bottom)
            user32.ClientToScreen(hwnd, ctypes.byref(pt_topleft))
            user32.ClientToScreen(hwnd, ctypes.byref(pt_bottomright))
            GAME_BBOX = (pt_topleft.x, pt_topleft.y, pt_bottomright.x, pt_bottomright.y)


def get_screenshot():
    """Captures the screen using the cached game window bounds."""
    global GAME_BBOX
    try:
        screenshot_raw = (
            ImageGrab.grab(bbox=GAME_BBOX, all_screens=True)
            if GAME_BBOX
            else ImageGrab.grab(all_screens=True)
        )
        return cv2.cvtColor(np.array(screenshot_raw), cv2.COLOR_RGB2BGR)
    except Exception:
        screenshot_raw = ImageGrab.grab(all_screens=True)
        return cv2.cvtColor(np.array(screenshot_raw), cv2.COLOR_RGB2BGR)


def check_hook_visible(frame):
    """Scans for the bite indicator ring strictly inside the bottom-right quadrant."""
    h, w, _ = frame.shape
    tol = config.COLOR_TOLERANCE
    r_h, g_h, b_h = config.HOOK_ICON_COLOR

    lower_hook = np.array([max(0, b_h - tol), max(0, g_h - tol), max(0, r_h - tol)])
    upper_hook = np.array(
        [min(255, b_h + tol), min(255, g_h + tol), min(255, r_h + tol)]
    )

    roi_br = frame[int(h * 0.65) : h, int(w * 0.65) : w]
    mask_hook = cv2.inRange(roi_br, lower_hook, upper_hook)
    contours_hook, _ = cv2.findContours(
        mask_hook, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    return any(cv2.contourArea(c) > 30 for c in contours_hook)


def check_reward_visible(frame):
    """Scans the screen and uses area constraints to filter out background ocean scenery."""
    local_tol = 60
    r_r, g_r, b_r = config.REWARD_BADGE_COLOR

    lower_reward = np.array(
        [max(0, b_r - local_tol), max(0, g_r - local_tol), max(0, r_r - local_tol)]
    )
    upper_reward = np.array(
        [
            min(255, b_r + local_tol),
            min(255, g_r + local_tol),
            min(255, r_r + local_tol),
        ]
    )

    mask_reward = cv2.inRange(frame, lower_reward, upper_reward)
    contours_reward, _ = cv2.findContours(
        mask_reward, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    return any(400 < cv2.contourArea(c) < 15000 for c in contours_reward)


def track_minigame(frame):
    """Focused mini-game bar tracking. Converts to HSV to capture full bar width."""
    h, w, _ = frame.shape

    # Isolate upper 35% height to ignore rod line and text box noise
    search_h = int(h * 0.35)
    crop_frame = frame[0:search_h, 0:w]

    # Convert to HSV color space for lighting-immune width detection
    hsv = cv2.cvtColor(crop_frame, cv2.COLOR_BGR2HSV)

    # RESTORED: Stable universal boundaries for teal/green target segments (#23bba5 / #2acbaf)
    lower_target = np.array([75, 40, 40])
    upper_target = np.array([100, 255, 255])

    # RESTORED: Stable universal boundaries for bright yellow slider lines (#fdf396)
    lower_dash = np.array([24, 40, 40])
    upper_dash = np.array([38, 255, 255])

    mask_target = cv2.inRange(hsv, lower_target, upper_target)
    mask_dash = cv2.inRange(hsv, lower_dash, upper_dash)

    contours_target, _ = cv2.findContours(
        mask_target, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    contours_dash, _ = cv2.findContours(
        mask_dash, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    target_candidates = []
    dash_candidates = []

    for c in contours_target:
        if cv2.contourArea(c) > 50:
            M = cv2.moments(c)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                target_candidates.append((cx, cy, c))

    for c in contours_dash:
        if cv2.contourArea(c) > 4:
            M = cv2.moments(c)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                dash_candidates.append((cx, cy))

    # Pair items sharing identical alignment rows
    for tx, ty, t_contour in target_candidates:
        for dx, dy in dash_candidates:
            if abs(ty - dy) <= 25:
                _, _, w_box, _ = cv2.boundingRect(t_contour)
                return tx, dx, w_box

    return None, None, 0


def reset_roi():
    pass

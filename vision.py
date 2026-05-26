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

# --- Global tracker for the game window ---
GAME_HWND = None
user32 = ctypes.windll.user32


def lock_active_window():
    """Saves the handle of the currently active window (the game)."""
    global GAME_HWND
    GAME_HWND = user32.GetForegroundWindow()


def get_screenshot():
    """Captures strictly the inner client region, ignoring the title bar."""
    global GAME_HWND

    if GAME_HWND:
        rect = wintypes.RECT()
        # Get exclusively the inner game area
        if user32.GetClientRect(GAME_HWND, ctypes.byref(rect)):
            # Map the local window coordinates to absolute monitor coordinates
            pt_topleft = wintypes.POINT(rect.left, rect.top)
            pt_bottomright = wintypes.POINT(rect.right, rect.bottom)
            user32.ClientToScreen(GAME_HWND, ctypes.byref(pt_topleft))
            user32.ClientToScreen(GAME_HWND, ctypes.byref(pt_bottomright))

            bbox = (pt_topleft.x, pt_topleft.y, pt_bottomright.x, pt_bottomright.y)

            try:
                # all_screens=True prevents crashes if the window is on a second monitor
                screenshot_raw = ImageGrab.grab(bbox=bbox, all_screens=True)
                return cv2.cvtColor(np.array(screenshot_raw), cv2.COLOR_RGB2BGR)
            except Exception:
                pass

    # Safe fallback if window locking fails
    screenshot_raw = ImageGrab.grab(all_screens=True)
    return cv2.cvtColor(np.array(screenshot_raw), cv2.COLOR_RGB2BGR)


def check_hook_visible(frame):
    """Restored to original RGB logic using config variables."""
    h, w, _ = frame.shape
    tol = config.COLOR_TOLERANCE
    r_h, g_h, b_h = config.HOOK_ICON_COLOR

    lower_hook = np.array([max(0, b_h - tol), max(0, g_h - tol), max(0, r_h - tol)])
    upper_hook = np.array(
        [min(255, b_h + tol), min(255, g_h + tol), min(255, r_h + tol)]
    )

    roi_br = frame[int(h * 0.65) :, int(w * 0.65) : w]
    mask_hook = cv2.inRange(roi_br, lower_hook, upper_hook)
    contours_hook, _ = cv2.findContours(
        mask_hook, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    return any(cv2.contourArea(c) > 30 for c in contours_hook)


def check_reward_visible(frame):
    """Scans strictly the center of the screen for the reward badge to avoid background noise."""
    h, w, _ = frame.shape

    # Crop to the center 50% of the screen (ignores sky and water at the edges)
    roi_center = frame[int(h * 0.25) : int(h * 0.75), int(w * 0.25) : int(w * 0.75)]

    # Tighten tolerance to avoid confusing background blues with the reward badge
    local_tol = 20
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

    mask_reward = cv2.inRange(roi_center, lower_reward, upper_reward)
    contours_reward, _ = cv2.findContours(
        mask_reward, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    # Check if any matching blue area is larger than 400 pixels
    return any(cv2.contourArea(c) > 400 for c in contours_reward)


def track_minigame(frame):
    """Focused mini-game bar tracking."""
    h, w, _ = frame.shape
    search_h = int(h * 0.35)
    crop_frame = frame[0:search_h, 0:w]
    hsv = cv2.cvtColor(crop_frame, cv2.COLOR_BGR2HSV)

    lower_target = np.array([75, 40, 40])
    upper_target = np.array([100, 255, 255])
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
        area = cv2.contourArea(c)
        if area > 50:
            M = cv2.moments(c)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                target_candidates.append((cx, cy, c, area))

    for c in contours_dash:
        area = cv2.contourArea(c)
        if area > 4:
            M = cv2.moments(c)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                dash_candidates.append((cx, cy, area))

    target_candidates.sort(key=lambda x: x[3], reverse=True)
    dash_candidates.sort(key=lambda x: x[2], reverse=True)

    for tx, ty, t_contour, _ in target_candidates:
        for dx, dy, _ in dash_candidates:
            if abs(ty - dy) <= 100:
                _, _, w_box, _ = cv2.boundingRect(t_contour)
                return tx, dx, w_box

    return None, None, 0


def reset_roi():
    pass

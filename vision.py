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

    # CRITICAL FIX: Increased tolerance from 20 to 60.
    # The game has a Day/Night weather cycle that heavily shifts UI lighting.
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

    mask_reward = cv2.inRange(roi_center, lower_reward, upper_reward)
    contours_reward, _ = cv2.findContours(
        mask_reward, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    # CRITICAL FIX: Increased area requirement to 1000.
    # The badge is massive, so this safely prevents false triggers from the ocean.
    return any(cv2.contourArea(c) > 1000 for c in contours_reward)


def track_minigame(frame):
    """Dynamic ROI Tracking: Finds the UI first, then tracks elements exclusively inside it."""
    h, w, _ = frame.shape
    search_h = int(h * 0.40)  # Minigame is always in the top 40% of the screen

    # --- STEP 1: Find the UI Track by locating the Green Bar ---
    crop_top = frame[0:search_h, 0:w]
    hsv_top = cv2.cvtColor(crop_top, cv2.COLOR_BGR2HSV)

    lower_target = np.array([75, 40, 40])
    upper_target = np.array([100, 255, 255])
    mask_target = cv2.inRange(hsv_top, lower_target, upper_target)

    contours_target, _ = cv2.findContours(
        mask_target, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    best_target = None
    max_target_area = 0

    # Filter to find the actual Green Bar (the largest horizontal green object)
    for c in contours_target:
        x, y, bw, bh = cv2.boundingRect(c)
        area = bw * bh
        if area > 50 and bw > (bh * 2):  # Must be a wide horizontal rectangle
            if area > max_target_area:
                max_target_area = area
                best_target = (x, y, bw, bh)

    # If we can't find the Green Bar, the UI is not visible. Stop here.
    if best_target is None:
        return None, None, 0

    target_x, target_y, target_w, target_h = best_target
    center_target_x = target_x + (target_w // 2)

    # --- STEP 2: Lock onto the UI and find the Yellow Dash ---
    # Now that we know EXACTLY where the UI is vertically,
    # we create a strict horizontal slice just for the dash.
    # We add a 10-pixel vertical buffer above and below to ensure we catch it.
    slice_y1 = max(0, target_y - 10)
    slice_y2 = min(search_h, target_y + target_h + 10)

    # Crop the image to ONLY the tiny horizontal UI track
    ui_slice = frame[slice_y1:slice_y2, 0:w]
    hsv_slice = cv2.cvtColor(ui_slice, cv2.COLOR_BGR2HSV)

    lower_dash = np.array([24, 40, 40])
    upper_dash = np.array([38, 255, 255])
    mask_dash = cv2.inRange(hsv_slice, lower_dash, upper_dash)

    contours_dash, _ = cv2.findContours(
        mask_dash, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    best_dash_x = None

    # Find the yellow dash inside this tiny horizontal slice
    for c in contours_dash:
        x, y, bw, bh = cv2.boundingRect(c)
        area = bw * bh

        # The dash is a vertical line.
        # Because our slice is so tight, background noise is basically 0.
        if area > 4 and bh > bw:
            # Note: Because the slice is full width (0:w),
            # the X coordinate perfectly matches the original frame.
            best_dash_x = x + (bw // 2)
            break  # Found the dash, stop searching!

    if best_dash_x is not None:
        return center_target_x, best_dash_x, target_w

    return center_target_x, None, target_w


def reset_roi():
    pass


def find_image(frame, template, threshold=0.8, region="all"):
    """Scans a restricted region of the screen to eliminate cross-matching bugs."""
    if template is None:
        return False

    h, w, _ = frame.shape

    # --- CRITICAL FIX: Isolate search zones to prevent wrong step detection ---
    if region == "center":
        # Reward screen strictly occupies the center 50% of the screen
        search_frame = frame[
            int(h * 0.25) : int(h * 0.75), int(w * 0.25) : int(w * 0.75)
        ]
    elif region == "hook":
        # Hook prompt strictly appears around the center player action space
        search_frame = frame[
            int(h * 0.40) : int(h * 0.85), int(w * 0.35) : int(w * 0.65)
        ]
    elif region == "minigame":
        # Minigame bar strictly populates the top 40%
        search_frame = frame[0 : int(h * 0.40), 0:w]
    else:
        search_frame = frame

    # Transparent background (Alpha channel) fallback handler
    if len(template.shape) == 3 and template.shape[2] == 4:
        mask = template[:, :, 3]
        template_bgr = template[:, :, :3]
        template_gray = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)
        frame_gray = cv2.cvtColor(search_frame, cv2.COLOR_BGR2GRAY)
        result = cv2.matchTemplate(
            frame_gray, template_gray, cv2.TM_CCORR_NORMED, mask=mask
        )
    else:
        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        frame_gray = cv2.cvtColor(search_frame, cv2.COLOR_BGR2GRAY)
        result = cv2.matchTemplate(frame_gray, template_gray, cv2.TM_CCOEFF_NORMED)

    _, max_val, _, _ = cv2.minMaxLoc(result)
    return max_val >= threshold

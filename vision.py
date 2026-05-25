import cv2
import numpy as np
from PIL import ImageGrab
import config
import ctypes

try:
    ctypes.windll.user32.SetProcessDPIAware()
except:
    pass

_roi_bbox = None


def locate_elements():
    """
    Tracks elements using an optimized local sub-region window.
    Returns (target_x, dash_x, target_width, is_reward_screen).
    """
    global _roi_bbox

    screenshot_raw = ImageGrab.grab()
    screenshot = np.array(screenshot_raw)
    frame = cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR)

    if _roi_bbox is not None:
        crop_frame = frame[_roi_bbox[1] : _roi_bbox[3], _roi_bbox[0] : _roi_bbox[2]]
        offset_x, offset_y = _roi_bbox[0], _roi_bbox[1]
    else:
        crop_frame = frame
        offset_x, offset_y = 0, 0

    tol = config.COLOR_TOLERANCE

    r_t, g_t, b_t = config.TARGET_BAR_COLOR
    lower_target = np.array([max(0, b_t - tol), max(0, g_t - tol), max(0, r_t - tol)])
    upper_target = np.array(
        [min(255, b_t + tol), min(255, g_t + tol), min(255, r_t + tol)]
    )

    r_d, g_d, b_d = config.DASH_COLOR
    lower_dash = np.array([max(0, b_d - tol), max(0, g_d - tol), max(0, r_d - tol)])
    upper_dash = np.array(
        [min(255, b_d + tol), min(255, g_d + tol), min(255, r_d + tol)]
    )

    mask_target = cv2.inRange(crop_frame, lower_target, upper_target)
    mask_dash = cv2.inRange(crop_frame, lower_dash, upper_dash)

    contours_target, _ = cv2.findContours(
        mask_target, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    contours_dash, _ = cv2.findContours(
        mask_dash, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    target_candidates = []
    dash_candidates = []

    for c in contours_target:
        if cv2.contourArea(c) > 60:
            M = cv2.moments(c)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"]) + offset_x
                cy = int(M["m01"] / M["m00"]) + offset_y
                target_candidates.append((cx, cy, c))

    for c in contours_dash:
        if cv2.contourArea(c) > 5:
            M = cv2.moments(c)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"]) + offset_x
                cy = int(M["m01"] / M["m00"]) + offset_y
                dash_candidates.append((cx, cy))

    # Identify and verify gauge coordinates
    for tx, ty, t_contour in target_candidates:
        for dx, dy in dash_candidates:
            if abs(ty - dy) <= 20 and abs(tx - dx) <= 400:
                # Extract the exact pixel width of the target bar
                x, y, w, h = cv2.boundingRect(t_contour)

                if _roi_bbox is None:
                    _roi_bbox = (max(0, x - 150), max(0, ty - 60), x + w + 150, ty + 60)

                return tx, dx, w, False

    _roi_bbox = None

    # Reward screen check
    r_r, g_r, b_r = config.REWARD_BADGE_COLOR
    lower_reward = np.array([max(0, b_r - tol), max(0, g_r - tol), max(0, r_r - tol)])
    upper_reward = np.array(
        [min(255, b_r + tol), min(255, g_r + tol), min(255, r_r + tol)]
    )

    mask_reward = cv2.inRange(frame, lower_reward, upper_reward)
    contours_reward, _ = cv2.findContours(
        mask_reward, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    for c in contours_reward:
        if cv2.contourArea(c) > 2000:
            return None, None, 0, True

    return None, None, 0, False

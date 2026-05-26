import time
import tkinter as tk
import vision
import controller
import config
from gui import AppleFishingGUI
import keyboard
import pydirectinput
import random
import os
import logging
import cv2
import numpy as np


class ColoredFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[94m",
        "INFO": "\033[96m",
        "WARNING": "\033[93m",
        "ERROR": "\033[91m",
        "CRITICAL": "\033[95m",
    }
    RESET = "\033[0m"

    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.RESET)
        format_str = f"{log_color}%(asctime)s [%(levelname)s] %(message)s{self.RESET}"
        formatter = logging.Formatter(format_str)
        return formatter.format(record)


file_handler = logging.FileHandler("logs/execution.log", encoding="utf-8")
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(ColoredFormatter())

logging.basicConfig(level=logging.INFO, handlers=[file_handler, stream_handler])

LEARNING_METRICS = {
    "optimal_gain": 1.0,
    "best_historical_score": 9999.0,
    "exploration_rate": 0.10,
}


def reliable_press(key, duration=0.1):
    pydirectinput.keyDown(key)
    time.sleep(duration)
    pydirectinput.keyUp(key)


def bot_loop(status_callback):
    pydirectinput.PAUSE = 0.001

    episode_errors = []
    lost_frames = 0
    rounds_completed = 0
    frames_inside = 0
    total_frames_tracked = 0
    cast_time = time.time()

    vision.reset_roi()
    logging.info("\n[START] Reactive Automation Engine Initialized.")

    base_dir = os.path.dirname(os.path.abspath(__file__))
    templates_dir = os.path.join(base_dir, "templates")

    if not os.path.exists(templates_dir):
        logging.error(
            f"[!] ERROR: The 'templates' folder is missing! I looked here: {templates_dir}"
        )
        status_callback("Folder Missing", "#FF453A")
        config.IS_RUNNING = False
        return

    def safe_imread(filename):
        file_path = os.path.join(templates_dir, filename)
        if not os.path.exists(file_path):
            return None
        try:
            file_bytes = np.fromfile(file_path, dtype=np.uint8)
            # CRITICAL FIX: IMREAD_UNCHANGED prevents Python from destroying transparent backgrounds
            img = cv2.imdecode(file_bytes, cv2.IMREAD_UNCHANGED)
            return img
        except Exception as e:
            logging.error(f"[!] ERROR: Cannot open '{filename}'. Reason: {e}")
            return None

    # Load all images (.png format)
    template_reward = safe_imread("reward.png")
    template_minigame = safe_imread("minigame.png")
    template_hook1 = safe_imread("hook.png")
    template_hook2 = safe_imread(
        "hook2.png"
    )  # Added support for the second transparent hook animation

    if template_reward is None or template_minigame is None or template_hook1 is None:
        logging.error("[!] ERROR: Core images missing from templates folder.")
        status_callback("Missing Image", "#FF453A")
        config.IS_RUNNING = False
        return

    vision.lock_active_window()

    while config.IS_RUNNING:
        frame = vision.get_screenshot()

        # PRIORITY 1: DO WE SEE THE REWARD SCREEN? (Search ONLY center)
        if vision.find_image(frame, template_reward, threshold=0.80, region="center"):
            status_callback("Reward Screen Detected! [ESC]...", "#BF5AF2")
            controller.stop_moving()
            reliable_press("escape", 0.1)
            time.sleep(4.0)  # Safe animation delay to let character put away fish

            rounds_completed += 1
            logging.info(f"[SUCCESS] Catch Count: {rounds_completed}")
            cast_time = 0  # Forces immediate recast
            continue

        # PRIORITY 2: DO WE SEE THE MINIGAME UI? (Search ONLY top half)
        elif vision.find_image(
            frame, template_minigame, threshold=0.80, region="minigame"
        ):
            target_x, dash_x, target_width = vision.track_minigame(frame)
            # ... (keep your existing tracking movement controls here) ...
            continue

        # PRIORITY 3: DO WE SEE THE BITE/HOOK ICON? (Search ONLY player action area)
        elif vision.find_image(
            frame, template_hook1, threshold=0.75, region="hook"
        ) or vision.find_image(frame, template_hook2, threshold=0.75, region="hook"):
            status_callback("Bite Detected! Confirming Game [F]...", "#34C759")
            reliable_press("f", 0.1)
            time.sleep(0.5)  # Wait for minigame to construct
            continue

        # PRIORITY 4: IF NOTHING ELSE IS ON SCREEN, WE MUST BE IDLE. CAST LINE.
        else:
            controller.stop_moving()

            # CRITICAL FIX: Lowered retry cooldown to 2.5s. If game ignores 'F', it retries rapidly.
            if time.time() - cast_time > 2.5:
                status_callback("Idle. Casting Line [F]...", "#FF9500")
                reliable_press("f", 0.1)
                cast_time = time.time()
                time.sleep(2.0)
            else:
                status_callback("Waiting for Fish...", "#8E8E93")
            time.sleep(0.05)

    controller.stop_moving()
    status_callback("Ready", "#8E8E93")
    logging.info("\n[STOP] Automation engine safely shut down.\n")


if __name__ == "__main__":
    import sys
    import ctypes

    def is_admin():
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

    if not is_admin():
        print("[System] Launching with User privileges. Elevating to Administrator...")
        safe_args = " ".join([f'"{arg}"' for arg in sys.argv])
        try:
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, safe_args, None, 1
            )
        except Exception as e:
            print(f"[Error] Privilege elevation failed: {e}")
            input("Press Enter to close...")
        sys.exit(0)

    print("[System] Administrator privileges confirmed. Booting CatchSys GUI...")
    root = tk.Tk()
    app = AppleFishingGUI(root, worker_function=bot_loop)

    try:
        keyboard.add_hotkey(config.HOTKEY_TOGGLE, app.external_toggle)
    except Exception as e:
        print(f"Warning: Global hotkey initialization failed ({e}).")

    root.bind(f"<{config.HOTKEY_TOGGLE.upper()}>", lambda event: app.external_toggle())
    root.mainloop()

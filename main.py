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

    # 1. Check if the templates folder itself exists
    if not os.path.exists(templates_dir):
        logging.error(
            f"[!] ERROR: The 'templates' folder is missing! I looked here: {templates_dir}"
        )
        status_callback("Folder Missing", "#FF453A")
        config.IS_RUNNING = False
        return

    def safe_imread(filename):
        """Safely loads images and tells you EXACTLY what is missing."""
        file_path = os.path.join(templates_dir, filename)

        # 2. Check if the specific file exists
        if not os.path.exists(file_path):
            logging.error(
                f"[!] ERROR: Missing file! I cannot find '{filename}' in the templates folder."
            )
            return None

        try:
            # 3. Read safely to bypass any foreign language folder bugs
            file_bytes = np.fromfile(file_path, dtype=np.uint8)
            img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

            if img is None:
                logging.error(f"[!] ERROR: '{filename}' exists but is broken or empty.")
            return img
        except Exception as e:
            logging.error(f"[!] ERROR: Cannot open '{filename}'. Reason: {e}")
            return None

    # Load images individually so the bot can report exactly which one failed
    template_reward = safe_imread("reward.jpg")
    template_minigame = safe_imread("minigame.jpg")
    template_hook = safe_imread("hook.jpg")

    # If ANY image failed to load, stop the bot
    if template_reward is None or template_minigame is None or template_hook is None:
        logging.error("[!] Please fix the missing files listed above and try again.")
        status_callback("Missing Image", "#FF453A")
        config.IS_RUNNING = False
        return

    vision.lock_active_window()

    while config.IS_RUNNING:
        frame = vision.get_screenshot()

        # PRIORITY 1: DO WE SEE THE REWARD SCREEN?
        if vision.find_image(frame, template_reward, threshold=0.80):
            status_callback("Reward Screen Detected! [ESC]...", "#BF5AF2")
            controller.stop_moving()
            reliable_press("escape", 0.1)
            time.sleep(1.5)  # Wait for UI to close

            rounds_completed += 1
            logging.info(f"[SUCCESS] Catch Count: {rounds_completed}")
            continue  # Skip the rest of the loop and start over

        # PRIORITY 2: DO WE SEE THE MINIGAME UI?
        elif vision.find_image(frame, template_minigame, threshold=0.80):
            target_x, dash_x, target_width = vision.track_minigame(frame)

            if target_x is not None and dash_x is not None and target_width > 0:
                lost_frames = 0
                distance = dash_x - target_x

                # The "Safe Zone" is 30% of the bar's width
                safe_zone = target_width * 0.30

                if dash_x > target_x + safe_zone:
                    controller.move_left()
                elif dash_x < target_x - safe_zone:
                    controller.move_right()
                else:
                    controller.stop_moving()

                status_callback("Playing Minigame...", "#34C759")
                time.sleep(0.001)
            else:
                controller.stop_moving()
                lost_frames += 1
                time.sleep(0.03)

            continue

        # PRIORITY 3: DO WE SEE THE BITE/HOOK ICON?
        elif vision.find_image(frame, template_hook, threshold=0.80):
            status_callback("Bite Detected! Confirming Game [F]...", "#34C759")
            reliable_press("f", 0.1)
            time.sleep(0.5)  # Wait for minigame to load
            continue

        # PRIORITY 4: IF NOTHING ELSE IS ON SCREEN, WE MUST BE IDLE. CAST LINE.
        else:
            controller.stop_moving()

            # We use a cooldown so it doesn't spam 'F' 100 times a second
            if time.time() - cast_time > 5.0:
                status_callback("Idle. Casting Line [F]...", "#FF9500")
                reliable_press("f", 0.1)
                cast_time = time.time()
                time.sleep(2.0)  # Wait for casting animation
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

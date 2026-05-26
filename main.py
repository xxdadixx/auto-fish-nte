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

    current_state = "INITIAL_SYNC"
    last_logged_state = None
    episode_errors = []
    lost_frames = 0
    rounds_completed = 0
    cast_time = time.time()
    wait_time = time.time()

    frames_inside = 0
    total_frames_tracked = 0

    current_gain = LEARNING_METRICS["optimal_gain"]
    exploration_modifier = 1.0 + random.uniform(
        -LEARNING_METRICS["exploration_rate"], LEARNING_METRICS["exploration_rate"]
    )
    active_gain = current_gain * exploration_modifier

    vision.reset_roi()
    logging.info(
        "\n=========================================\n[START] Automation engine successfully initialized.\n========================================="
    )

    # Lock onto the window the user just clicked
    vision.lock_active_window()

    while config.IS_RUNNING:
        if current_state != last_logged_state:
            logging.info(
                f"\n---> STEP TRANSITION: [ {last_logged_state} ] to [ {current_state} ] <---"
            )
            last_logged_state = current_state

        frame = vision.get_screenshot()

        # --- STEP 1: CHECK FISHING STATUS & CAST ---
        if current_state == "STEP_1_CHECK":
            controller.stop_moving()
            if not vision.check_hook_visible(frame):
                status_callback("No Status Detected. Casting Line [F]...", "#FF9500")
                reliable_press("f", 0.1)
                cast_time = time.time()
                current_state = "STEP_2_WAITING"
                time.sleep(2.0)  # Animation lock buffer
            else:
                current_state = "STEP_2_WAITING"
                time.sleep(0.5)
            continue

        # --- STEP 2: CHECK GLOWING ICON & CONFIRM MINI-GAME ---
        if current_state == "STEP_2_WAITING":
            target_x, dash_x, target_width = vision.track_minigame(frame)
            if target_x is not None and dash_x is not None:
                current_state = "STEP_3_MINIGAME"
                lost_frames = 0
                episode_errors = []
                frames_inside = 0
                total_frames_tracked = 0
                continue

            if vision.check_hook_visible(frame):
                status_callback("Bite Detected! Confirming Game [F]...", "#34C759")
                reliable_press("f", 0.1)
                current_state = "WAIT_MINIGAME_LOAD"  # Added missing transition state
                wait_time = time.time()
                time.sleep(0.5)
            else:
                status_callback(
                    f"Waiting for Bite... ({time.time() - cast_time:.1f}s)", "#FF9500"
                )
                if time.time() - cast_time > 25.0:  # Safety Timeout
                    logging.warning("\n[!] Timeout reached. Resetting back to Step 1.")
                    current_state = "STEP_1_CHECK"
            time.sleep(0.04)
            continue

        # --- NEW: SAFEGUARD TO WAIT FOR UI TO RENDER ---
        if current_state == "WAIT_MINIGAME_LOAD":
            status_callback("Waiting for Minigame UI...", "#34C759")
            target_x, dash_x, target_width = vision.track_minigame(frame)
            if target_x is not None and dash_x is not None:
                current_state = "STEP_3_MINIGAME"
                lost_frames = 0
                episode_errors = []
                frames_inside = 0
                total_frames_tracked = 0
            elif time.time() - wait_time > 3.0:  # Timeout safety net
                current_state = "STEP_1_CHECK"
            continue

        # --- STEP 3: HIGH-SPEED TRACKING MINI-GAME ---
        if current_state == "STEP_3_MINIGAME":
            target_x, dash_x, target_width = vision.track_minigame(frame)

            if target_x is not None and dash_x is not None and target_width > 0:
                lost_frames = 0
                distance = dash_x - target_x
                half_width = target_width / 2.0
                error_ratio = distance / half_width if half_width > 0 else 0

                total_frames_tracked += 1
                if abs(error_ratio) <= 1.0:
                    frames_inside += 1

                rolling_accuracy = (frames_inside / total_frames_tracked) * 100
                status_callback(f"Tracking | Acc: {rolling_accuracy:.1f}%", "#34C759")

                # Move yellow bar (dash) left (A) if it's to the right of green bar (target)
                if dash_x > target_x + (target_width * 0.1):
                    controller.move_left()
                # Move yellow bar (dash) right (D) if it's to the left of green bar (target)
                elif dash_x < target_x - (target_width * 0.1):
                    controller.move_right()
                # Stop if the yellow bar has reached the green bar
                else:
                    controller.stop_moving()

                time.sleep(0.001)
                episode_errors.append(abs(distance))
            else:
                lost_frames += 1
                time.sleep(0.03)
                if lost_frames >= 5:  # UI target lost; game ended
                    controller.stop_moving()
                    current_state = "WAITING_FOR_REWARD"
                    wait_time = time.time()
            continue

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

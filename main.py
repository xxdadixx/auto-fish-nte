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


# --- CUSTOM COLORED LOGGING FORMATTER ---
class ColoredFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[94m",  # Blue
        "INFO": "\033[96m",  # Cyan
        "WARNING": "\033[93m",  # Yellow
        "ERROR": "\033[91m",  # Red
        "CRITICAL": "\033[95m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.RESET)
        format_str = f"{log_color}%(asctime)s [%(levelname)s] %(message)s{self.RESET}"
        formatter = logging.Formatter(format_str)
        return formatter.format(record)


# Configure structured file logging (plain text for file, colors for console)
file_handler = logging.FileHandler("logs/execution.log", encoding="utf-8")
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(ColoredFormatter())

logging.basicConfig(level=logging.INFO, handlers=[file_handler, stream_handler])

# Persistent In-Memory Learning Parameters across runs
LEARNING_METRICS = {
    "optimal_gain": 1.0,
    "best_historical_score": 9999.0,
    "exploration_rate": 0.10,
}


def reliable_press(key, duration=0.1):
    """Sends a hardware keypress with an explicit hold duration to guarantee registration."""
    pydirectinput.keyDown(key)
    time.sleep(duration)
    pydirectinput.keyUp(key)


def bot_loop(status_callback):
    """
    State-Machine Autonomous Fishing Engine with First-Frame Auto-Detection.
    Optimized with Wide-Belt Hysteresis and HSV tracking to keep the bar centered smoothly.
    """
    pydirectinput.PAUSE = 0.001

    current_state = None
    last_logged_state = None
    episode_errors = []
    lost_frames = 0
    rounds_completed = 0
    cast_time = time.time()

    # Dynamic accuracy tracking properties
    frames_inside = 0
    total_frames_tracked = 0

    # Policy weights assignment
    current_gain = LEARNING_METRICS["optimal_gain"]
    exploration_modifier = 1.0 + random.uniform(
        -LEARNING_METRICS["exploration_rate"], LEARNING_METRICS["exploration_rate"]
    )
    active_gain = current_gain * exploration_modifier

    vision.reset_roi()
    logging.info(
        "\n=========================================\n[START] Automation engine successfully initialized.\n========================================="
    )

    while config.IS_RUNNING:
        # Prevent log flooding by capturing explicit state changes only, with visual spacing
        if current_state != last_logged_state:
            logging.info(
                f"\n---> STATE TRANSITION: [ {last_logged_state} ] to [ {current_state} ] <---"
            )
            last_logged_state = current_state

        # Dynamic first-frame initialization check
        if current_state is None:
            status_callback("Syncing Game State...", "#FF9500")
            frame = vision.get_screenshot()
            if vision.check_reward_visible(frame):
                current_state = "REWARD"
            elif vision.check_hook_visible(frame):
                current_state = "WAITING_BITE"
                cast_time = time.time()
            else:
                target_x, dash_x, target_width = vision.track_minigame(frame)
                if target_x is not None and dash_x is not None:
                    current_state = "MINIGAME"
                    lost_frames = 0
                    episode_errors = []
                    frames_inside = 0
                    total_frames_tracked = 0
                else:
                    current_state = "CAST"
            continue

        # --- STAGE 1: CAST THE LINE ---
        if current_state == "CAST":
            controller.stop_moving()
            status_callback("Casting Line Hook [F]...", "#FF9500")
            reliable_press("f", 0.1)
            cast_time = time.time()
            current_state = "WAITING_BITE"
            time.sleep(2.0)  # Allow initial animation to settle
            continue

        # Fetch active screen frame to distribute to the current state check
        frame = vision.get_screenshot()

        # --- STAGE 2: WAITING FOR BITE DIALOGUE ---
        if current_state == "WAITING_BITE":
            target_x, dash_x, target_width = vision.track_minigame(frame)
            if target_x is not None and dash_x is not None:
                current_state = "MINIGAME"
                lost_frames = 0
                episode_errors = []
                frames_inside = 0
                total_frames_tracked = 0
                continue

            if vision.check_hook_visible(frame):
                status_callback("Bite Detected! Hooking Fish [F]...", "#34C759")
                reliable_press("f", 0.1)
                current_state = "MINIGAME"
                lost_frames = 0
                episode_errors = []
                frames_inside = 0
                total_frames_tracked = 0
                time.sleep(0.8)  # Smooth transition into mini-game view layout
            else:
                status_callback(
                    f"Waiting for Bite... ({time.time() - cast_time:.1f}s)", "#FF9500"
                )
                if time.time() - cast_time > 25.0:  # Safety timeout loop reset
                    logging.warning(
                        "\n[!] Bite timeout reached without response. Recasting line."
                    )
                    current_state = "CAST"
            time.sleep(0.04)
            continue

        # --- STAGE 3: HIGH-SPEED TRACKING MINI-GAME ---
        if current_state == "MINIGAME":
            if vision.check_reward_visible(frame):
                controller.stop_moving()
                current_state = "REWARD"
                continue

            target_x, dash_x, target_width = vision.track_minigame(frame)

            if target_x is not None and dash_x is not None and target_width > 0:
                lost_frames = 0

                # 1. Calculate precise distance and proportional error ratio
                distance = dash_x - target_x
                half_width = target_width / 2.0
                error_ratio = distance / half_width if half_width > 0 else 0

                # 2. Track precision metrics (abs <= 1.0 means inside the true green belt)
                total_frames_tracked += 1
                if abs(error_ratio) <= 1.0:
                    frames_inside += 1

                # Calculate true rolling percentage
                rolling_accuracy = (frames_inside / total_frames_tracked) * 100
                status_callback(f"Inside Bar | Acc: {rolling_accuracy:.1f}%", "#34C759")

                # Throttled live log display every 15 frames to prevent screen lag
                if total_frames_tracked % 15 == 0:
                    logging.info(
                        f"[MINIGAME LIVE] Accuracy: {rolling_accuracy:.2f}% ({frames_inside}/{total_frames_tracked} frames inside)"
                    )

                # 3. Wide Belt Stabilization Strategy
                active_dir = controller._active_direction

                if active_dir is None:
                    # When stationary, let it float freely inside the bar. Only engage near the outer limits.
                    if error_ratio > 0.65:
                        controller.move_left()
                    elif error_ratio < -0.65:
                        controller.move_right()
                elif active_dir == "left":
                    # Stop holding Left early before it reaches center to allow soft braking
                    if error_ratio <= 0.15:
                        controller.stop_moving()
                elif active_dir == "right":
                    # Stop holding Right early before it reaches center to allow soft braking
                    if error_ratio >= -0.15:
                        controller.stop_moving()

                time.sleep(0.001)  # CPU Relief
                episode_errors.append(abs(distance))
            else:
                lost_frames += 1
                if lost_frames >= 4:  # Bar missing; game ended
                    controller.stop_moving()
                    if vision.check_reward_visible(frame):
                        current_state = "REWARD"
                    else:
                        status_callback("Fish escaped. Resetting...", "#FF9500")
                        logging.warning(
                            "\n[!] Mini-game terminated: Target tracking lost (Fish Escaped)."
                        )
                        current_state = "CAST"
            continue

        # --- STAGE 4: DISMISS REWARD WINDOW ---
        if current_state == "REWARD":
            status_callback("Reward Window Detected! Dismissing [ESC]...", "#BF5AF2")
            reliable_press("escape", 0.1)
            time.sleep(1.2)  # Wait for screen cards to clear

            # Print final round accuracy summary statistics
            if total_frames_tracked > 0:
                tracking_accuracy = (frames_inside / total_frames_tracked) * 100
                logging.info(
                    f"\n    -> [ROUND SUMMARY] Final Performance Tracking Accuracy: {tracking_accuracy:.2f}% inside the bar!"
                )
            else:
                logging.info(
                    "\n    -> [ROUND SUMMARY] No tracking samples captured this round."
                )

            # Policy reinforcement calculation
            if len(episode_errors) > 5:
                mean_absolute_error = sum(episode_errors) / len(episode_errors)
                best_score = LEARNING_METRICS["best_historical_score"]

                if mean_absolute_error < best_score:
                    LEARNING_METRICS["best_historical_score"] = mean_absolute_error
                    LEARNING_METRICS["optimal_gain"] = (
                        0.85 * LEARNING_METRICS["optimal_gain"]
                    ) + (0.15 * active_gain)
                    LEARNING_METRICS["exploration_rate"] = max(
                        0.02, LEARNING_METRICS["exploration_rate"] - 0.01
                    )
                    logging.info(
                        f"    -> [AI UPDATE] New policy achieved. Gain: {LEARNING_METRICS['optimal_gain']:.4f}, Exploration: {LEARNING_METRICS['exploration_rate']:.2f}"
                    )

            # Generate parameters for next round
            current_gain = LEARNING_METRICS["optimal_gain"]
            exploration_modifier = 1.0 + random.uniform(
                -LEARNING_METRICS["exploration_rate"],
                LEARNING_METRICS["exploration_rate"],
            )
            active_gain = current_gain * exploration_modifier

            # Increment rounds completed and log clearly separated at the end of the full cycle
            rounds_completed += 1
            logging.info(
                f"\n=========================================\n[SUCCESS] Round Completed! Total Catch Count: {rounds_completed}\n========================================="
            )

            current_state = "CAST"
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

    # DUAL-LAYER HOTKEY BINDING:
    # 1. Global System Hook (Works when focused inside Borderless/Windowed game)
    try:
        keyboard.add_hotkey(config.HOTKEY_TOGGLE, app.external_toggle)
    except Exception as e:
        print(f"Warning: Global hotkey initialization failed ({e}).")

    # 2. Local Window Focus Hook (Guaranteed to work whenever you press F5 directly on the bot GUI panel)
    root.bind(f"<{config.HOTKEY_TOGGLE.upper()}>", lambda event: app.external_toggle())

    root.mainloop()

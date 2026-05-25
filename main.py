import time
import tkinter as tk
import vision
import controller
import config
from gui import AppleFishingGUI
import keyboard
import pydirectinput
import random

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
    Optimized State-Machine Autonomous Fishing Engine with First-Frame Auto-Detection.
    Eliminates internal bar adjustments to lock position stability and prevent overshooting.
    """
    pydirectinput.PAUSE = 0.001

    current_state = None
    episode_errors = []
    lost_frames = 0
    cast_time = time.time()

    # Policy weights assignment
    current_gain = LEARNING_METRICS["optimal_gain"]
    exploration_modifier = 1.0 + random.uniform(
        -LEARNING_METRICS["exploration_rate"], LEARNING_METRICS["exploration_rate"]
    )
    active_gain = current_gain * exploration_modifier

    vision.reset_roi()

    while config.IS_RUNNING:

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
                continue

            if vision.check_hook_visible(frame):
                status_callback("Bite Detected! Hooking Fish [F]...", "#34C759")
                reliable_press("f", 0.1)
                current_state = "MINIGAME"
                lost_frames = 0
                episode_errors = []
                time.sleep(0.8)  # Smooth transition into mini-game view layout
            else:
                status_callback(
                    f"Waiting for Bite... ({time.time() - cast_time:.1f}s)", "#FF9500"
                )
                if time.time() - cast_time > 25.0:  # Safety timeout loop reset
                    current_state = "CAST"
            time.sleep(0.04)
            continue

        # --- STAGE 3: HIGH-SPEED TRACKING MINI-GAME ---
        if current_state == "MINIGAME":
            # BUG FIX: Checking reward window at top of frame cycle intercepts visual false-positives
            if vision.check_reward_visible(frame):
                controller.stop_moving()
                current_state = "REWARD"
                continue

            target_x, dash_x, target_width = vision.track_minigame(frame)

            if target_x is not None and dash_x is not None:
                lost_frames = 0
                status_callback(
                    f"Tracking Mini-Game (Gain: {active_gain:.2f})", "#34C759"
                )

                distance = dash_x - target_x
                abs_distance = abs(distance)
                episode_errors.append(abs_distance)

                # BUG FIX: Matches the exact physical boundaries of the color bar with a tiny 2% safety edge
                SAFE_BAR_ZONE = int(target_width * 0.48)

                if abs_distance <= SAFE_BAR_ZONE:
                    # Already safely inside the colored bar; drop inputs immediately to ride it
                    controller.stop_moving()
                else:
                    # Outside the bar bounds; engage continuous direction tracking to catch up fast
                    if distance > 0:
                        controller.move_left()
                    else:
                        controller.move_right()

                time.sleep(0.001)  # Micro-sleep to preserve CPU clock cycles
            else:
                lost_frames += 1
                if lost_frames >= 4:  # Bar is missing; mini-game has ended
                    controller.stop_moving()
                    if vision.check_reward_visible(frame):
                        current_state = "REWARD"
                    else:
                        status_callback("Fish escaped. Resetting...", "#FF9500")
                        current_state = "CAST"
            continue

        # --- STAGE 4: DISMISS REWARD WINDOW ---
        if current_state == "REWARD":
            status_callback("Reward Window Detected! Dismissing [ESC]...", "#BF5AF2")
            reliable_press("escape", 0.1)
            time.sleep(1.2)  # Wait for inventory saving screen cards to clear

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

            # Generate new values for the next round
            current_gain = LEARNING_METRICS["optimal_gain"]
            exploration_modifier = 1.0 + random.uniform(
                -LEARNING_METRICS["exploration_rate"],
                LEARNING_METRICS["exploration_rate"],
            )
            active_gain = current_gain * exploration_modifier

            current_state = "CAST"
            continue

    controller.stop_moving()
    status_callback("Ready", "#8E8E93")


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

    root.mainloop()

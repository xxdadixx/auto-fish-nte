import time
import tkinter as tk
import vision
import controller
import config
from gui import AppleFishingGUI
import keyboard
import pydirectinput


def bot_loop(status_callback):
    """
    Background automation loop engine using Inverse Proportional Dampening.
    Gently slows down the tracking cursor the closer it gets to the center.
    """
    pydirectinput.PAUSE = 0.001

    while config.IS_RUNNING:
        target_x, dash_x, target_width, is_reward = vision.locate_elements()

        if is_reward:
            controller.stop_moving()
            status_callback("Fish Caught! [F] Re-cast | [ESC] Close Window", "#BF5AF2")
            time.sleep(0.2)
            continue

        if target_x is None or dash_x is None:
            controller.stop_moving()
            status_callback("Scanning Screen...", "#FF9500")
            time.sleep(0.05)
            continue

        status_callback("Active Tracking", "#34C759")
        distance = dash_x - target_x  # Positive = Dash is right, Negative = Left
        abs_distance = abs(distance)

        # Dynamically scale tracking zones to accommodate narrower color bars
        DEADZONE = max(2, int(target_width * 0.05))
        BRAKING_ZONE = max(15, int(target_width * 0.35))

        # CASE 1: Inside Dynamic Deadzone -> Centered Perfectly
        if abs_distance <= DEADZONE:
            controller.stop_moving()
            time.sleep(0.01)  # Stay idle to let physics settle

        # CASE 2: Outside Braking Zone -> Full-Throttle Sprint Mode (High Speed)
        elif abs_distance > BRAKING_ZONE:
            if distance > 0:
                controller.move_left()
            else:
                controller.move_right()

        # CASE 3: Inside Braking Zone -> Inverse Proportional Dampening Mode
        else:
            # Kill any active continuous key-holds to drop speed instantly
            controller.stop_moving()

            # Fire a single frame hardware keystroke strike (No continuous down state)
            if distance > 0:
                pydirectinput.press("a")
            else:
                pydirectinput.press("d")

            # BUG FIX: Calculate an inverse stabilization wait time.
            # The closer the dash gets to the center, the LONGER the program waits
            # between taps. This actively destroys kinetic momentum and eliminates jitter.
            dampening_factor = (BRAKING_ZONE - abs_distance) * 0.0025
            settle_delay = max(0.005, dampening_factor)

            time.sleep(settle_delay)

        time.sleep(0.002)

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
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(sys.argv), None, 1
        )
        sys.exit(0)

    root = tk.Tk()
    app = AppleFishingGUI(root, worker_function=bot_loop)

    try:
        keyboard.add_hotkey(config.HOTKEY_TOGGLE, app.external_toggle)
    except Exception as e:
        print(f"Warning: Global hotkey initialization failed ({e}).")

    root.mainloop()

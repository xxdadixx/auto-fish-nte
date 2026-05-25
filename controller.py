import pydirectinput

# Remove built-in input delay for instantaneous reactions
pydirectinput.PAUSE = 0.001

# Internal state tracking variable to prevent input spamming
_active_direction = None  # Can be 'left', 'right', or None


def move_left():
    """Sends a continuous hold for Left (A) only if not already holding it."""
    global _active_direction

    if _active_direction != "left":
        pydirectinput.keyUp("d")  # Release right if active
        pydirectinput.keyDown("a")  # Engage continuous hold left
        _active_direction = "left"


def move_right():
    """Sends a continuous hold for Right (D) only if not already holding it."""
    global _active_direction

    if _active_direction != "right":
        pydirectinput.keyUp("a")  # Release left if active
        pydirectinput.keyDown("d")  # Engage continuous hold right
        _active_direction = "right"


def stop_moving():
    """Safely lifts all active keys and clears the directional state."""
    global _active_direction

    if _active_direction is not None:
        pydirectinput.keyUp("a")
        pydirectinput.keyUp("d")
        _active_direction = None

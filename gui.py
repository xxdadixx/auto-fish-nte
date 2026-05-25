import tkinter as tk
from tkinter import ttk
import threading
import config


class AppleFishingGUI:
    def __init__(self, root, worker_function):
        self.root = root
        self.worker_function = worker_function

        self.root.title("CatchSys")
        self.root.geometry("380x320")
        self.root.resizable(False, False)

        # Color Palette
        self.bg_color = "#1C1C1E"
        self.card_color = "#2C2C2E"
        self.text_color = "#FFFFFF"
        self.sub_text = "#AEAEB2"
        self.accent_blue = "#0A84FF"

        self.root.configure(bg=self.bg_color)
        self.setup_styles()
        self.build_ui()

    def setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure(".", background=self.bg_color, foreground=self.text_color)

    def build_ui(self):
        header = tk.Label(
            self.root,
            text="CatchSys Pro",
            font=("SF Pro Display", 20, "bold"),
            bg=self.bg_color,
            fg=self.text_color,
        )
        header.pack(pady=(25, 5), anchor="w", px=25)

        sub_header = tk.Label(
            self.root,
            text="Automated Fishing System",
            font=("SF Pro Text", 11),
            bg=self.bg_color,
            fg=self.sub_text,
        )
        sub_header.pack(pady=(0, 20), anchor="w", px=25)

        self.card = tk.Frame(self.root, bg=self.card_color, bd=0)
        self.card.pack(fill="x", padx=25, pady=10)

        status_label = tk.Label(
            self.card,
            text="SYSTEM STATUS",
            font=("SF Pro Text", 9, "bold"),
            bg=self.card_color,
            fg=self.sub_text,
        )
        status_label.pack(anchor="w", padx=15, pady=(12, 2))

        self.status_val = tk.Label(
            self.card,
            text="Ready",
            font=("SF Pro Text", 16, "bold"),
            bg=self.card_color,
            fg="#8E8E93",
        )
        self.status_val.pack(anchor="w", padx=15, pady=(0, 12))

        # Added dynamic hotkey hint text directly into the button layout
        self.btn = tk.Button(
            self.root,
            text=f"Start Automation ({config.HOTKEY_TOGGLE.upper()})",
            font=("SF Pro Text", 12, "bold"),
            bg=self.accent_blue,
            fg=self.text_color,
            activebackground="#0066CC",
            activeforeground=self.text_color,
            bd=0,
            relief="flat",
            cursor="hand2",
            command=self.toggle_automation,
        )
        self.btn.pack(fill="x", padx=25, pady=(25, 0), ipady=10)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def update_status(self, text, color):
        self.root.after(0, lambda: self.status_val.config(text=text, fg=color))

    def external_toggle(self):
        """Safely forwards out-of-thread hotkey events back to the main UI loop."""
        self.root.after(0, self.toggle_automation)

    def toggle_automation(self):
        if not config.IS_RUNNING:
            config.IS_RUNNING = True
            self.btn.config(
                text=f"Stop Automation ({config.HOTKEY_TOGGLE.upper()})", bg="#FF453A"
            )

            self.worker_thread = threading.Thread(
                target=self.worker_function, args=(self.update_status,), daemon=True
            )
            self.worker_thread.start()
        else:
            config.IS_RUNNING = False
            self.btn.config(
                text=f"Start Automation ({config.HOTKEY_TOGGLE.upper()})",
                bg=self.accent_blue,
            )

    def on_close(self):
        config.IS_RUNNING = False
        self.root.destroy()


# Padding patch helper
tk.Label.pack = lambda self, *args, **kwargs: (
    tk.Widget.pack(self, *args, **{k: v for k, v in kwargs.items() if k != "px"})
    if "px" not in kwargs
    else tk.Widget.pack(
        self,
        *args,
        **{**{k: v for k, v in kwargs.items() if k != "px"}, "padx": kwargs["px"]},
    )
)

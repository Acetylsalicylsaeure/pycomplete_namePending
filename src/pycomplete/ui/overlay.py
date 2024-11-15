import tkinter as tk
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class PredictionOverlay:
    """Manages prediction overlay window"""

    def __init__(self):
        self.root = tk.Tk()
        self._setup_window()
        self.label = None

    def _setup_window(self):
        try:
            self.root.attributes('-type', 'dock')
            self.root.attributes('-alpha', 0.7)
            self.root.config(bg='black')
            self.root.overrideredirect(True)
            self.root.withdraw()
        except Exception as e:
            logger.error(f"Error setting up overlay window: {e}")

    def show(self, text: str, x: int, y: int):
        """Show prediction at specified coordinates"""
        try:
            if not self.label:
                self.label = tk.Label(
                    self.root,
                    text=text,
                    fg='white',
                    bg='black',
                    font=('Sans', 10)
                )
                self.label.pack()
            else:
                self.label.config(text=text)

            self.root.geometry(f'+{x}+{y-30}')
            self.root.deiconify()
            self.root.update()
        except Exception as e:
            logger.error(f"Error showing overlay: {e}")

    def hide(self):
        """Hide the overlay"""
        try:
            self.root.withdraw()
            self.root.update()
        except Exception as e:
            logger.error(f"Error hiding overlay: {e}")

    def update(self):
        """Update the overlay window"""
        try:
            self.root.update()
        except Exception as e:
            logger.error(f"Error updating overlay: {e}")
        return True

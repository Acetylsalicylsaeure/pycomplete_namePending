import os
import subprocess
import logging
from typing import Tuple

import pyatspi
from gi.repository import GLib

from ..core.accessibility import AccessibilityManager
from ..core.config import ConfigManager
from ..core.text_field import TextFieldManager
from ..core.prediction import SimplePredictor
from ..ui.overlay import PredictionOverlay

logger = logging.getLogger(__name__)


class TextPredictorApp(AccessibilityManager):
    """Main text predictor application"""

    def __init__(self, config_path: str):
        super().__init__()
        self.config = ConfigManager.load_config(config_path)
        self.targets = ConfigManager.load_targets(self.config.target_file)
        self.text_field_manager = TextFieldManager()
        self.predictor = SimplePredictor()
        self.overlay = PredictionOverlay()
        self.current_field = None
        self.current_prediction = None

        # Set up logging
        logging.basicConfig(
            level=logging.DEBUG if self.config.debug_level > 0 else logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        # Register event handlers
        self.register_event('object:text-changed:insert',
                            self._on_text_changed)
        self.register_event('object:text-changed:delete',
                            self._on_text_changed)
        self.register_keystroke(
            self._on_key,
            kind=(pyatspi.KEY_PRESSED_EVENT, pyatspi.KEY_RELEASED_EVENT)
        )

        # Set up overlay update interval
        GLib.timeout_add(50, self._update_overlay)

    def _on_text_changed(self, event):
        """Handle text change events"""
        try:
            if not event.source:
                return

            text_field = self.text_field_manager.is_text_field(event.source)
            if not text_field:
                return

            self.current_field = event.source
            text = event.source.queryText()
            content = text.getText(0, text.characterCount)

            prediction = self.predictor.predict(content)
            if prediction:
                self.current_prediction = prediction
                x, y = self._get_cursor_position(event.source)
                self.overlay.show(prediction, x, y)
            else:
                self.current_prediction = None
                self.overlay.hide()
        except Exception as e:
            logger.error(f"Error handling text change: {e}")

    def _on_key(self, event):
        """Handle keyboard events"""
        try:
            if not self.current_field or not self.current_prediction:
                return False

            if self._is_trigger_key(event):
                self._insert_prediction(self.current_prediction)
                return True

            return False
        except Exception as e:
            logger.error(f"Error handling key event: {e}")
            return False

    def _get_cursor_position(self, obj) -> Tuple[int, int]:
        """Get cursor coordinates"""
        try:
            text = obj.queryText()
            component = obj.queryComponent()
            abs_x, abs_y = component.getPosition(0)
            x, y = text.getRangeExtents(
                text.caretOffset,
                text.caretOffset + 1,
                0
            )[:2]
            return abs_x + x, abs_y + y
        except Exception as e:
            logger.error(f"Error getting cursor position: {e}")
            return 0, 0

    def _is_trigger_key(self, event) -> bool:
        """Check if event matches trigger key"""
        return (
            event.event_string == self.config.trigger_key.event_string or
            getattr(event, 'id', None) == self.config.trigger_key.key_code
        )

    def _insert_prediction(self, text: str):
        """Insert prediction text"""
        try:
            subprocess.run(['ydotool', 'type', ' ' + text], check=True)
            self.current_prediction = None
            self.overlay.hide()
        except Exception as e:
            logger.error(f"Error inserting prediction: {e}")

    def _update_overlay(self):
        """Update overlay window"""
        self.overlay.update()
        return True

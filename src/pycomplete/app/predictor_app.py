import os
import subprocess
import logging
from typing import Tuple, Optional
import asyncio
import functools
import time
from gi.repository import GLib
import pyatspi
import aiohttp

from ..core.accessibility import AccessibilityManager
from ..core.config import ConfigManager
from ..core.text_field import TextFieldManager
from ..core.prediction import OllamaPredictor
from ..ui.overlay import PredictionOverlay

logger = logging.getLogger(__name__)


class TextPredictorApp(AccessibilityManager):
    """Main text predictor application"""

    def __init__(self, config_path: str, debug_level: int = 0):
        super().__init__()

        # Set up logging first
        self._setup_logging(debug_level)

        logger.debug(f"Initializing TextPredictorApp")
        self.config = ConfigManager.load_config(config_path)
        self.targets = ConfigManager.load_targets(self.config.target_file)
        self.text_field_manager = TextFieldManager()
        self.overlay = PredictionOverlay()
        self.current_field = None
        self.current_prediction = None
        self.last_text = ""

        # Debouncing variables
        self.last_request_time = 0
        self.debounce_delay = 0.25  # Increased to 250ms
        self._pending_content = None
        self._pending_timer = None
        self._current_task = None
        self._processing_prediction = False  # Flag to track active predictions

        # Initialize asyncio loop and session
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.session = aiohttp.ClientSession()

        # Set up async predictor
        self.predictor = OllamaPredictor(
            model="llama3.2:1b",
            session=self.session,
            trigger=" ",
            min_chars=3,
            idle_delay=1.0
        )

        # Set up async integration with GLib
        self._setup_loop_integration()
        # Register accessibility events
        logger.debug("Registering accessibility events")
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

        logger.info("Initialization complete")

    def register_event(self, event_type, handler):
        """Register an event handler with logging"""
        logger.debug(f"Registering event handler for {event_type}")
        super().register_event(event_type, handler)

    def register_keystroke(self, handler, **kwargs):
        """Register a keystroke handler with logging"""
        logger.debug("Registering keystroke handler")
        super().register_keystroke(handler, **kwargs)

    def _setup_logging(self, debug_level: int):
        """Set up logging with the specified debug level"""
        log_levels = {
            0: logging.WARNING,
            1: logging.INFO,
            2: logging.DEBUG
        }
        log_level = log_levels.get(debug_level, logging.DEBUG)

        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        logging.getLogger('src.pycomplete').setLevel(log_level)
        logger.setLevel(log_level)

        if debug_level >= 2:
            logging.getLogger('asyncio').setLevel(logging.DEBUG)

    def _setup_loop_integration(self):
        """Set up integration between asyncio and GLib main loops"""
        logger.debug("Setting up event loop integration")

        def process_async_events():
            try:
                self.loop.stop()
                self.loop.run_forever()
            except Exception as e:
                logger.error(f"Error processing async events: {
                             e}", exc_info=True)
            return True

        # Process async events every 50ms
        GLib.timeout_add(50, process_async_events)

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

            # Log text changes using available attributes
            field_description = f"text field {text_field.name}"
            if event.type.endswith(':insert'):
                logger.info(f"Text inserted in {
                            field_description}: '{content}'")
            elif event.type.endswith(':delete'):
                logger.info(f"Text deleted in {
                            field_description}: '{content}'")

            # Log details in debug mode
            logger.debug(
                f"Text field details: role={text_field.role}, "
                f"name='{text_field.name}', "
                f"interfaces={len(text_field.interfaces)}, "
                f"length={len(content)}"
            )

            self._debounce_prediction_request(content)

        except Exception as e:
            logger.error(f"Error handling text change: {e}", exc_info=True)

    def _on_key(self, event):
        """Handle keyboard events"""
        try:
            if not self.current_field or not self.current_prediction:
                return False

            if self._is_trigger_key(event):
                if event.type == pyatspi.KEY_PRESSED_EVENT:
                    logger.info(f"Trigger key pressed, accepting prediction: '{
                                self.current_prediction}'")
                    self._insert_prediction(self.current_prediction)
                return True

            return False
        except Exception as e:
            logger.error(f"Error handling key event: {e}", exc_info=True)
            return False

    def _is_trigger_key(self, event) -> bool:
        """Check if event matches trigger key"""
        return (
            event.event_string == self.config.trigger_key.event_string or
            getattr(event, 'id', None) == self.config.trigger_key.key_code
        )

    def _insert_prediction(self, text: str):
        """Insert prediction text"""
        try:
            logger.info(f"Inserting prediction: '{text}'")
            subprocess.run(['ydotool', 'type', ' ' + text], check=True)
            self.current_prediction = None
            self.overlay.hide()
        except Exception as e:
            logger.error(f"Error inserting prediction: {e}", exc_info=True)

    def _debounce_prediction_request(self, content: str):
        """Debounce prediction requests using time-based approach"""
        current_time = time.time()

        # Cancel any existing pending timer
        if self._pending_timer:
            try:
                GLib.source_remove(self._pending_timer)
                self._pending_timer = None
            except Exception:
                pass

        # Don't cancel existing task if it's still processing
        if self._current_task and not self._current_task.done() and self._processing_prediction:
            logger.debug(
                "Skipping prediction request - previous task still processing")
            return

        # Store the pending content
        self._pending_content = content

        # Calculate time until next allowed request
        time_since_last = current_time - self.last_request_time
        delay = max(0, int((self.debounce_delay - time_since_last) * 1000))

        logger.debug(f"Scheduling prediction request with {delay}ms delay")

        # Schedule the request
        self._pending_timer = GLib.timeout_add(
            delay,
            self._execute_prediction_request
        )

    def _execute_prediction_request(self):
        """Execute the pending prediction request"""
        self._pending_timer = None
        if not self._pending_content:
            return False

        content = self._pending_content
        self._pending_content = None
        self.last_request_time = time.time()

        if self._processing_prediction:
            logger.debug(
                "Skipping prediction - previous prediction in progress")
            return False

        logger.debug(f"Executing prediction request for content of length {
                     len(content)}")

        self._processing_prediction = True
        self._current_task = self.loop.create_task(
            self._async_predict(content))

        def handle_task_result(task):
            self._processing_prediction = False
            try:
                task.result()
            except asyncio.CancelledError:
                logger.debug("Prediction task cancelled")
            except Exception as e:
                logger.error(f"Prediction task failed: {e}", exc_info=True)

        self._current_task.add_done_callback(handle_task_result)
        return False

    async def _async_predict(self, content: str):
        """Asynchronously get prediction and update UI"""
        try:
            logger.debug(f"Starting async prediction for: '{content}'")

            # Get prediction
            result = await self.predictor.predict(content)

            if result.text:
                logger.info(f"Prediction received: '{result.text}'")
                logger.debug(f"Prediction metadata: {result.metadata}")
                # Update UI in main thread
                GLib.idle_add(lambda: self._handle_prediction(result.text))
            else:
                logger.debug(f"No prediction available: {
                             result.metadata['reason']}")

        except asyncio.CancelledError:
            logger.debug("Prediction cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in prediction: {e}", exc_info=True)
            raise

    def _handle_prediction(self, prediction: str) -> bool:
        """Handle prediction result"""
        try:
            self.current_prediction = prediction
            if self.current_field:
                x, y = self._get_cursor_position(self.current_field)
                logger.debug(
                    f"Showing prediction overlay at coordinates ({x}, {y})")
                self.overlay.show(prediction, x, y)
            return False
        except Exception as e:
            logger.error(f"Error handling prediction result: {
                         e}", exc_info=True)
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
            logger.error(f"Error getting cursor position: {e}", exc_info=True)
            return 0, 0

    def _update_overlay(self):
        """Update the overlay window"""
        try:
            self.overlay.update()
        except Exception as e:
            logger.error(f"Error updating overlay: {e}", exc_info=True)
        return True

    def cleanup(self):
        """Cleanup resources"""
        try:
            logger.info("Starting application cleanup")

            # Cancel current task if it exists
            if self._current_task and not self._current_task.done():
                logger.debug("Cancelling current prediction task")
                self._current_task.cancel()

            # Cancel pending timer
            if self._pending_timer:
                try:
                    logger.debug("Removing pending timer")
                    GLib.source_remove(self._pending_timer)
                except Exception:
                    pass

            # Close aiohttp session
            if hasattr(self, 'session'):
                logger.debug("Closing aiohttp session")
                self.loop.run_until_complete(self.session.close())

            # Run cleanup tasks
            logger.debug("Running predictor cleanup")
            self.loop.run_until_complete(self.predictor.cleanup())

            # Close the loop
            logger.debug("Closing asyncio loop")
            self.loop.close()

            # Clean up parent class
            logger.debug("Running parent cleanup")
            super().cleanup()

            logger.info("Cleanup complete")

        except Exception as e:
            logger.error(f"Error during cleanup: {e}", exc_info=True)

from abc import ABC, abstractmethod
import pyatspi
from gi.repository import GLib, Atspi
import gi
import os
import signal
import sys
import logging

gi.require_version('Atspi', '2.0')

logger = logging.getLogger(__name__)


class AccessibilityManager(ABC):
    """Base class for handling accessibility events and registry"""

    def __init__(self):
        self.main_loop = GLib.MainLoop()
        self._event_handlers = {}
        self._cleanup_done = False

    def register_event(self, event_type, handler):
        """Register an event handler"""
        self._event_handlers[event_type] = handler
        pyatspi.Registry.registerEventListener(handler, event_type)

    def register_keystroke(self, handler, **kwargs):
        """Register a keystroke handler"""
        pyatspi.Registry.registerKeystrokeListener(
            handler,
            key_set=kwargs.get('key_set', None),
            mask=kwargs.get('mask', 0),
            kind=kwargs.get('kind', [0])
        )

    def cleanup(self):
        """Cleanup registered handlers"""
        if self._cleanup_done:
            return

        self._cleanup_done = True
        for event_type, handler in self._event_handlers.items():
            pyatspi.Registry.deregisterEventListener(handler, event_type)
        pyatspi.Registry.stop()
        if self.main_loop.is_running():
            self.main_loop.quit()
        sys.exit(0)  # Add explicit exit here

    def run(self):
        """Start the event loop"""
        for sig in (signal.SIGINT, signal.SIGTERM):
            GLib.unix_signal_add(GLib.PRIORITY_HIGH, sig, self._handle_signal)

        try:
            pyatspi.Registry.start()
            self.main_loop.run()
        except KeyboardInterrupt:
            self.cleanup()
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
            self.cleanup()

    def _handle_signal(self, *args):
        """Handle interrupt signals"""
        self.cleanup()
        return GLib.SOURCE_REMOVE  # Ensures the signal handler is removed

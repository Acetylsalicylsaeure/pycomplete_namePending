from abc import ABC, abstractmethod
import pyatspi
from gi.repository import GLib, Atspi
import gi
import os
import signal

gi.require_version('Atspi', '2.0')


class AccessibilityManager(ABC):
    """Base class for handling accessibility events and registry"""

    def __init__(self):
        self.main_loop = GLib.MainLoop()
        self._event_handlers = {}

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
        for event_type, handler in self._event_handlers.items():
            pyatspi.Registry.deregisterEventListener(handler, event_type)
        pyatspi.Registry.stop()
        if self.main_loop.is_running():
            self.main_loop.quit()

    def run(self):
        """Start the event loop"""
        GLib.unix_signal_add(GLib.PRIORITY_HIGH,
                             signal.SIGINT, self._handle_signal)
        GLib.unix_signal_add(GLib.PRIORITY_HIGH,
                             signal.SIGTERM, self._handle_signal)

        try:
            pyatspi.Registry.start()
            self.main_loop.run()
        finally:
            self.cleanup()

    def _handle_signal(self, *args):
        """Handle interrupt signals"""
        self.cleanup()
        return GLib.SOURCE_REMOVE

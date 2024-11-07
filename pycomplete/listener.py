#!/usr/bin/env python3

import pyatspi
from gi.repository import GLib, Atspi
import json
import signal
import sys
import os
import gi

# Set required versions before importing
gi.require_version('Atspi', '2.0')


class TextFieldListener:
    def __init__(self):
        self.debug_level = 0  # 0: minimal, 1: normal, 2: verbose
        self.main_loop = GLib.MainLoop()
        self.target_file = "text_field_targets.json"
        self.targets = self.load_targets()
        self.current_field = None

    def log(self, message, level=1):
        """Log message based on debug level"""
        if self.debug_level >= level:
            print(message)

    def log_debug(self, message):
        """Log detailed debug information"""
        if self.debug_level >= 2:
            print(f"DEBUG: {message}")

    def load_targets(self):
        try:
            if os.path.exists(self.target_file):
                with open(self.target_file, 'r') as f:
                    targets = json.load(f)
                self.log(f"Loaded {len(targets)} targets", 1)
                return targets
            else:
                print(f"No targets file found at {self.target_file}")
                sys.exit(1)
        except Exception as e:
            print(f"Error loading targets: {e}")
            sys.exit(1)

    def get_object_path(self, obj):
        """Get the accessibility path to this object"""
        path = []
        current = obj
        try:
            while current:
                component = {
                    'role': current.getRole(),
                    'name': current.name,
                    'index': current.getIndexInParent(),
                    'role_name': current.getRoleName()
                }
                path.append(component)
                current = current.parent
        except Exception as e:
            self.log_debug(f"Error getting object path: {e}")
        return path[::-1]  # Reverse to get path from root to leaf

    def matches_target(self, obj, target):
        """Check if object matches a target"""
        try:
            # Get the current object's path
            current_path = self.get_object_path(obj)
            target_path = target['path']

            self.log_debug(f"\nComparing paths:")
            self.log_debug(f"Current path length: {len(current_path)}")
            self.log_debug(f"Target path length: {len(target_path)}")

            # First check if it's the same application and frame
            if len(current_path) < 2 or len(target_path) < 2:
                self.log_debug("Path too short")
                return False

            # Match the application (usually the first or second element)
            app_matched = False
            for current_comp in current_path[:2]:
                for target_comp in target_path[:2]:
                    if (current_comp['role'] == target_comp['role'] and
                            current_comp.get('name') == target_comp.get('name')):
                        app_matched = True
                        break
                if app_matched:
                    break

            if not app_matched:
                self.log_debug("Application didn't match")
                return False

            # For the actual text field (last element), check role and interfaces
            current_obj = current_path[-1]
            target_obj = target_path[-1]

            role_matches = current_obj['role'] == target['role']
            self.log_debug(f"Role match: {role_matches} (current: {
                           current_obj['role']}, target: {target['role']})")

            # Check interfaces
            current_interfaces = set(pyatspi.listInterfaces(obj))
            target_interfaces = set(target['interfaces'])
            interfaces_match = target_interfaces.issubset(current_interfaces)
            self.log_debug(f"Interfaces match: {interfaces_match}")
            self.log_debug(f"Current interfaces: {current_interfaces}")
            self.log_debug(f"Target interfaces: {target_interfaces}")

            return role_matches and interfaces_match

        except Exception as e:
            self.log_debug(f"Error in matches_target: {e}")
            return False

    def is_target_field(self, obj):
        try:
            # Check against all targets
            for target in self.targets:
                if self.matches_target(obj, target):
                    return True
            return False

        except Exception as e:
            self.log(f"Error checking target field: {e}", 1)
            return False

    def on_focus(self, event):
        try:
            if event.source is None:
                return

            self.log_debug("\n=== Focus Event ===")
            self.log_debug(f"Source role: {event.source.getRoleName()}")
            self.log_debug(f"Source name: {event.source.name}")

            if self.is_target_field(event.source):
                self.current_field = event.source
                text = event.source.queryText()
                content = text.getText(0, text.characterCount)
                if len(content) > 0 or self.debug_level > 0:
                    self.log(f"\n=== Target Field Focused ===", 1)
                    self.log(f"Content: {content}", 1)
            else:
                self.current_field = None

        except Exception as e:
            self.log(f"Error in focus handler: {e}", 1)

    def on_text_changed(self, event):
        try:
            if event.source is None:
                return

            if self.is_target_field(event.source):
                text = event.source.queryText()
                content = text.getText(0, text.characterCount)

                if len(content) > 0 or self.debug_level > 0:
                    self.log(f"\n=== Target Field Content Changed ===", 0)
                    self.log(f"Content: {content}", 0)
                    self.log(f"Change type: {event.type}", 1)

                # Try to get specific changed portion
                try:
                    if hasattr(event, 'detail1') and hasattr(event, 'detail2'):
                        offset = event.detail1
                        length = event.detail2
                        changed_text = text.getText(offset, offset + length)
                        self.log(f"Changed portion: {changed_text}", 1)
                except Exception:
                    pass

        except Exception as e:
            self.log(f"Error in text change handler: {e}", 1)

    def on_key(self, event):
        try:
            if not self.current_field or not self.is_target_field(self.current_field):
                return

            # Get key event details
            self.log(f"\n=== Key Event ===", 1)
            self.log(f"Key event type: {event.type}", 1)
            self.log(f"Key ID: {event.id}", 1)
            self.log(f"Key event string: {event.event_string}", 1)

            # Try to get current text content after key press
            try:
                text = self.current_field.queryText()
                content = text.getText(0, text.characterCount)
                if len(content) > 0 or self.debug_level > 0:
                    self.log(f"Current content: {content}", 1)
            except Exception as e:
                self.log(f"Error getting current content: {e}", 1)

        except Exception as e:
            self.log(f"Error in key handler: {e}", 1)

    def quit(self):
        if self.main_loop.is_running():
            self.main_loop.quit()

    def run(self):
        GLib.unix_signal_add(GLib.PRIORITY_HIGH,
                             signal.SIGINT, self.handle_sigint)
        GLib.unix_signal_add(GLib.PRIORITY_HIGH,
                             signal.SIGTERM, self.handle_sigint)

        try:
            self.log("Starting text field listener...", 1)
            self.log(f"Monitoring {len(self.targets)} target fields...", 1)
            self.log("Press Ctrl+C to exit", 1)

            # Register all event listeners
            pyatspi.Registry.registerEventListener(
                self.on_focus,
                'focus'
            )

            pyatspi.Registry.registerEventListener(
                self.on_text_changed,
                'object:text-changed:insert'
            )

            pyatspi.Registry.registerEventListener(
                self.on_text_changed,
                'object:text-changed:delete'
            )

            pyatspi.Registry.registerEventListener(
                self.on_key,
                'object:text-caret-moved'
            )

            pyatspi.Registry.start(synchronous=False, gil=False)
            self.main_loop.run()

        except Exception as e:
            self.log(f"Error: {e}", 1)
        finally:
            self.cleanup()

    def handle_sigint(self, *args):
        self.log("\nReceived interrupt signal", 1)
        self.cleanup()
        return GLib.SOURCE_REMOVE

    def cleanup(self):
        self.log("Cleaning up...", 1)
        try:
            pyatspi.Registry.deregisterEventListener(
                self.on_focus,
                'focus'
            )
            pyatspi.Registry.deregisterEventListener(
                self.on_text_changed,
                'object:text-changed:insert'
            )
            pyatspi.Registry.deregisterEventListener(
                self.on_text_changed,
                'object:text-changed:delete'
            )
            pyatspi.Registry.deregisterEventListener(
                self.on_key,
                'object:text-caret-moved'
            )
            pyatspi.Registry.stop()
            self.quit()
        except Exception as e:
            self.log(f"Error during cleanup: {e}", 1)

        os._exit(0)


if __name__ == "__main__":
    TextFieldListener().run()

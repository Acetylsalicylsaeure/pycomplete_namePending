#!/usr/bin/env python3

import pyatspi
from gi.repository import GLib, Gio, Atspi
import json
import signal
import sys
import os
import gi
import subprocess
import tkinter as tk
import time

# Set required versions before importing
gi.require_version('Atspi', '2.0')


class OverlayWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.setup_window()
        self.label = None

    def setup_window(self):
        # Make window borderless and transparent
        self.root.attributes('-type', 'dock')  # Unmanaged window
        self.root.attributes('-alpha', 0.7)    # Semi-transparent
        self.root.config(bg='black')
        self.root.overrideredirect(True)       # No window decorations
        self.root.lift()                       # Stay on top
        self.root.withdraw()                   # Initially hidden

    def show_prediction(self, text, x, y):
        if self.label is None:
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

        # Position window
        self.root.geometry(f'+{x}+{y-30}')  # 30 pixels above cursor
        self.root.deiconify()
        self.root.update()

    def hide_prediction(self):
        self.root.withdraw()
        self.root.update()

    def update(self):
        self.root.update()
        return True


class TextPredictor:
    def __init__(self):
        self.debug_level = 2
        self.main_loop = GLib.MainLoop()
        self.target_file = "text_field_targets.json"
        self.config_file = "text_field_config.json"
        self.targets = self.load_targets()
        self.trigger_key = self.load_trigger_key()
        self.current_field = None
        self.current_prediction = None
        self.overlay = OverlayWindow()
        self.last_key_time = 0
        self.last_text_change_time = 0

        try:
            self.init_input_tool()
        except Exception as e:
            self.log(f"Error initializing input tool: {e}", 1)
            sys.exit(1)

    def init_input_tool(self):
        if not self.check_command_exists("ydotool"):
            print("Error: 'ydotool' command not found. Please install it.")
            sys.exit(1)

        if not self.is_ydotoold_running():
            print("Error: ydotoold service is not running.")
            print("Start it with: systemctl --user start ydotool.service")
            sys.exit(1)

    def check_command_exists(self, command):
        return subprocess.run(['which', command],
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE).returncode == 0

    def is_ydotoold_running(self):
        try:
            result = subprocess.run(
                ['systemctl', '--user', 'is-active', 'ydotool.service'],
                capture_output=True,
                text=True
            )
            return result.returncode == 0
        except Exception:
            return False

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

    def load_trigger_key(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    trigger_key = config.get('trigger_key')
                    if trigger_key:
                        self.log(f"Loaded trigger key config: {
                                 trigger_key}", 1)
                        return trigger_key

            print(f"No trigger key config found at {self.config_file}")
            print("Please run the key capture utility first to set up your trigger key.")
            sys.exit(1)
        except Exception as e:
            print(f"Error loading trigger key config: {e}")
            sys.exit(1)

    def log(self, message, level=1):
        if self.debug_level >= level:
            print(message)

    def matches_target(self, obj, target):
        try:
            current_interfaces = set(pyatspi.listInterfaces(obj))
            target_interfaces = set(target['interfaces'])

            role_matches = obj.getRole() == target['role']
            interfaces_match = target_interfaces.issubset(current_interfaces)

            return role_matches and interfaces_match
        except Exception as e:
            self.log(f"Error in matches_target: {e}")
            return False

    def is_target_field(self, obj):
        try:
            for target in self.targets:
                if self.matches_target(obj, target):
                    return True
            return False
        except Exception as e:
            self.log(f"Error checking target field: {e}")
            return False

    def is_trigger_key(self, event):
        try:
            current_time = time.time()
            if current_time - self.last_key_time < 0.1:  # 100ms debounce
                return False

            key_matches = any([
                event.event_string == self.trigger_key['event_string'],
                getattr(event, 'key_code', None) == self.trigger_key.get(
                    'key_code'),
                getattr(event, 'hw_code', None) == self.trigger_key.get(
                    'hw_code', None)
            ])

            if key_matches:
                self.last_key_time = current_time

            return key_matches
        except Exception as e:
            self.log(f"Error checking trigger key: {e}", 2)
            return False

    def predict_text(self, current_text):
        if current_text.strip().lower().endswith("hello"):
            return "world"
        return None

    def insert_prediction(self, text):
        try:
            subprocess.run(['ydotool', 'type', ' ' + text], check=True)
            self.log(f"Inserted prediction: {text}")
            self.current_prediction = None
            self.overlay.hide_prediction()
        except Exception as e:
            self.log(f"Error inserting prediction: {e}")

    def get_cursor_position(self, obj):
        try:
            text = obj.queryText()
            caretOffset = text.caretOffset

            component = obj.queryComponent()
            abs_x, abs_y = component.getPosition(0)
            x, y, width, height = text.getRangeExtents(
                caretOffset, caretOffset + 1, 0)

            return abs_x + x, abs_y + y
        except Exception as e:
            self.log(f"Error getting cursor position: {e}")
            return 0, 0

    def handle_keyboard_event(self, event):
        try:
            self.log(f"""
Key Event Details:
  Type: {event.type}
  ID: {event.id}
  Event string: {getattr(event, 'event_string', 'N/A')}
  Key code: {getattr(event, 'key_code', 'N/A')}
            """, 2)

            # Check if we're in a target field
            if not self.current_field or not self.is_target_field(self.current_field):
                return False

            # Handle trigger key
            if self.is_trigger_key(event):
                self.log("Trigger key detected!")

                # Only block and handle the trigger key if there's an active prediction
                if self.current_prediction:
                    self.insert_prediction(self.current_prediction)
                    return True  # Consume the event only when we have a prediction

                return False  # Let the trigger key through if no prediction

            return False

        except Exception as e:
            self.log(f"Error in keyboard handler: {e}")
            return False

    def on_text_changed(self, event):
        try:
            if event.source is None or not self.is_target_field(event.source):
                return

            # Add debouncing for text changes
            current_time = time.time()
            if current_time - self.last_text_change_time < 0.1:  # 100ms debounce
                return
            self.last_text_change_time = current_time

            self.current_field = event.source
            text = event.source.queryText()
            current_content = text.getText(0, text.characterCount)

            # Update prediction
            if self.current_prediction:
                self.current_prediction = None
                self.overlay.hide_prediction()

            prediction = self.predict_text(current_content)
            if prediction:
                self.current_prediction = prediction
                x, y = self.get_cursor_position(event.source)
                self.log(f"Showing prediction at {x}, {y}")
                self.overlay.show_prediction(prediction, x, y)

            self.log(f"Updated text: {current_content}")

        except Exception as e:
            self.log(f"Error in text change handler: {e}")

    def update_overlay(self):
        self.overlay.update()
        return True

    def run(self):
        GLib.unix_signal_add(GLib.PRIORITY_HIGH,
                             signal.SIGINT, self.handle_sigint)
        GLib.unix_signal_add(GLib.PRIORITY_HIGH,
                             signal.SIGTERM, self.handle_sigint)

        try:
            self.log("Starting text predictor...")
            self.log(f"Monitoring {len(self.targets)} target fields...")
            self.log(f"Using trigger key: {self.trigger_key['event_string']}")
            self.log("Press Ctrl+C to exit")

            # Register for both text change events
            pyatspi.Registry.registerEventListener(
                self.on_text_changed,
                'object:text-changed:insert'
            )
            pyatspi.Registry.registerEventListener(
                self.on_text_changed,
                'object:text-changed:delete'
            )

            # Register keystroke listener
            pyatspi.Registry.registerKeystrokeListener(
                self.handle_keyboard_event,
                key_set=None,
                mask=0,
                kind=(pyatspi.KEY_PRESSED_EVENT, pyatspi.KEY_RELEASED_EVENT),
                synchronous=True,
                preemptive=True
            )

            GLib.timeout_add(50, self.update_overlay)

            pyatspi.Registry.start()
            self.main_loop.run()

        except Exception as e:
            self.log(f"Error: {e}")
        finally:
            self.cleanup()

    def handle_sigint(self, *args):
        self.log("\nReceived interrupt signal")
        self.cleanup()
        return GLib.SOURCE_REMOVE

    def cleanup(self):
        self.log("Cleaning up...")
        try:
            self.overlay.hide_prediction()

            pyatspi.Registry.deregisterKeystrokeListener(
                self.handle_keyboard_event,
                key_set=None,
                mask=0,
                kind=(pyatspi.KEY_PRESSED_EVENT, pyatspi.KEY_RELEASED_EVENT)
            )

            pyatspi.Registry.deregisterEventListener(
                self.on_text_changed,
                'object:text-changed:insert'
            )
            pyatspi.Registry.deregisterEventListener(
                self.on_text_changed,
                'object:text-changed:delete'
            )

            pyatspi.Registry.stop()
            if self.main_loop.is_running():
                self.main_loop.quit()
        except Exception as e:
            self.log(f"Error during cleanup: {e}")

        os._exit(0)


if __name__ == "__main__":
    TextPredictor().run()

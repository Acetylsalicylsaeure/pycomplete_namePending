#!/usr/bin/env python3

import pyatspi
from gi.repository import GLib
import signal
import sys
import json
import os


class KeyLogger:
    def __init__(self):
        self.main_loop = GLib.MainLoop()
        self.config_file = "text_field_config.json"
        self.captured = False

    def on_key(self, event):
        try:
            print(f"\nKey Event: {event.event_string}")
            print(f"Key code: {event.id}")

            if not self.captured:
                key_info = {
                    "event_string": event.event_string,
                    "key_code": event.id
                }

                with open(self.config_file, 'w') as f:
                    json.dump({"trigger_key": key_info}, f, indent=2)
                print(f"\nSaved trigger key: {key_info}")
                self.captured = True
                self.cleanup()

        except Exception as e:
            print(f"Error: {e}")

    def run(self):
        pyatspi.Registry.registerKeystrokeListener(
            self.on_key,
            key_set=None,
            mask=0,
            kind=[0]
        )

        print("Press the key you want to use for completion...")
        GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGINT, self.cleanup)
        pyatspi.Registry.start()
        self.main_loop.run()

    def cleanup(self, *args):
        print("Cleaning up...")
        try:
            pyatspi.Registry.deregisterKeystrokeListener(
                self.on_key,
                key_set=None,
                mask=0,
                kind=[0]
            )
            pyatspi.Registry.stop()
            self.main_loop.quit()
        except Exception as e:
            print(f"Error during cleanup: {e}")
        finally:
            os._exit(0)


if __name__ == "__main__":
    KeyLogger().run()

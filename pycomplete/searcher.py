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


class TextFieldSearcher:
    def __init__(self):
        self.main_loop = GLib.MainLoop()
        self.target_file = "text_field_targets.json"
        self.waiting_for_here = True
        self.current_text_field = None

        # Define roles that typically represent text fields
        self.text_field_roles = {
            pyatspi.ROLE_TEXT,
            pyatspi.ROLE_ENTRY,
            pyatspi.ROLE_DOCUMENT_TEXT,
            pyatspi.ROLE_PARAGRAPH,
            pyatspi.ROLE_DOCUMENT_FRAME,
            pyatspi.ROLE_EDITBAR,  # Changed from ROLE_EDITOR
            pyatspi.ROLE_TERMINAL,
            pyatspi.ROLE_VIEWPORT,
            pyatspi.ROLE_SCROLL_PANE,
            pyatspi.ROLE_APPLICATION

        }

        # Define required interfaces for text fields
        self.required_interfaces = {
            'Text',
            'EditableText',
            'Component'
        }

    def is_text_field(self, obj):
        try:
            role = obj.getRole()
            states = obj.getState()
            interfaces = pyatspi.listInterfaces(obj)

            # Special handling for terminals - much more permissive
            if role == pyatspi.ROLE_TERMINAL:
                # Only check if it's enabled and visible/showing
                basic_conditions = {
                    'enabled': states.contains(pyatspi.STATE_ENABLED),
                    'visible': states.contains(pyatspi.STATE_VISIBLE),
                    'showing': states.contains(pyatspi.STATE_SHOWING)
                }

                if basic_conditions['enabled'] and (basic_conditions['visible'] or basic_conditions['showing']):
                    return {
                        'role': role,
                        'interfaces': interfaces,
                        'path': self.get_simplified_path(obj),
                        'name': obj.name if obj.name else 'unnamed',
                        'attributes': {}
                    }
                return None

            # Regular text field handling
            attributes = {}
            try:
                attributes = dict([attr.split(':', 1)
                                  for attr in obj.getAttributes()])
            except Exception:
                pass

            # Relaxed interface requirements
            basic_text_interfaces = {
                'Accessible',  # Most basic interface
                'Component'    # For position/size info
            }

            # More permissive conditions
            conditions = {
                'role_match': role in self.text_field_roles,
                'has_basic_interfaces': all(interface in interfaces for interface in basic_text_interfaces),
                'has_text_interface': 'Text' in interfaces,
                'is_editable': (states.contains(pyatspi.STATE_EDITABLE) or
                                'EditableText' in interfaces or
                                attributes.get('contenteditable') == 'true'),
                'not_read_only': not states.contains(pyatspi.STATE_READ_ONLY),
                'enabled': states.contains(pyatspi.STATE_ENABLED),
                'visible': states.contains(pyatspi.STATE_VISIBLE),
                'showing': states.contains(pyatspi.STATE_SHOWING)
            }

            # Debug information
            debug_info = {
                'role': role,
                'role_name': obj.getRoleName(),
                'states': [str(state) for state in states.getStates()],
                'interfaces': interfaces,
                'conditions': conditions,
                'name': obj.name if obj.name else 'unnamed',
                'attributes': attributes
            }

            print("\nElement Debug Info:")
            for key, value in debug_info.items():
                print(f"  {key}: {value}")

            # More permissive field detection
            is_text_field = (
                (conditions['role_match'] or conditions['is_editable']) and
                conditions['has_basic_interfaces'] and
                (conditions['has_text_interface'] or role == pyatspi.ROLE_TERMINAL) and
                conditions['enabled'] and
                (conditions['visible'] or conditions['showing'])
            )

            if is_text_field:
                return {
                    'role': role,
                    'interfaces': interfaces,
                    'path': self.get_simplified_path(obj),
                    'name': obj.name if obj.name else 'unnamed',
                    'attributes': attributes
                }
            return None

        except Exception as e:
            print(f"Error checking text field: {e}")
            return None

    def get_simplified_path(self, obj):
        """Get a simplified accessibility path focusing on role and application context"""
        path = []
        current = obj
        try:
            while current:
                # Only include significant components in the path
                if self.is_significant_component(current):
                    component = {
                        'role': current.getRole(),
                        'name': current.name if current.name else None,
                        'index': current.getIndexInParent(),
                        'role_name': current.getRoleName()
                    }
                    path.append(component)
                current = current.parent
        except Exception as e:
            print(f"Error getting path: {e}")
            pass
        return path[::-1]  # Reverse to get path from root to leaf

    def is_significant_component(self, obj):
        """Determine if a component should be included in the path"""
        try:
            # Always include the application and main window
            if obj.getRole() in {pyatspi.ROLE_APPLICATION, pyatspi.ROLE_FRAME}:
                return True

            # Include components that help identify the context
            significant_roles = {
                pyatspi.ROLE_DIALOG,
                pyatspi.ROLE_DOCUMENT_FRAME,
                pyatspi.ROLE_TOOL_BAR,
                pyatspi.ROLE_MENU_BAR,
                pyatspi.ROLE_PANEL,
                pyatspi.ROLE_INTERNAL_FRAME
            }

            # Include if it has a specific name or is a significant role
            return bool(obj.name) or obj.getRole() in significant_roles

        except Exception:
            return False

    def on_text_change(self, event):
        try:
            print(f"\nText Change Event: {event.type}")
            print(f"Source role name: {
                  event.source.getRoleName() if event.source else 'None'}")

            if event.source:
                # Try to get text content through different means
                try:
                    if hasattr(event, 'any_data'):
                        print(f"Changed text (any_data): {event.any_data}")

                    if 'Text' in pyatspi.listInterfaces(event.source):
                        text = event.source.queryText()
                        offset_start = max(0, event.detail1)
                        length = max(0, event.detail2)

                        if text.characterCount > 0:
                            # Try to get the specific changed portion
                            try:
                                changed_text = text.getText(
                                    offset_start, offset_start + length)
                                print(f"Changed portion: {changed_text}")
                            except Exception:
                                pass

                            # Try to get the full content
                            try:
                                full_text = text.getText(
                                    0, text.characterCount)
                                print(f"Full content: {full_text}")

                                if self.waiting_for_here and full_text.strip().lower() == "here":
                                    print(
                                        "\nFound 'here' marker! Saving target...")
                                    text_field_info = self.is_text_field(
                                        event.source)
                                    if text_field_info:
                                        self.save_target(text_field_info)
                                    self.cleanup()
                            except Exception as e:
                                print(f"Error getting full text: {e}")
                except Exception as e:
                    print(f"Error accessing text content: {e}")

        except Exception as e:
            print(f"Error in text change handler: {e}")

    def save_target(self, target_info):
        try:
            # Load existing targets if file exists
            targets = []
            if os.path.exists(self.target_file):
                with open(self.target_file, 'r') as f:
                    targets = json.load(f)

            # Add new target
            targets.append(target_info)

            # Save updated targets
            with open(self.target_file, 'w') as f:
                json.dump(targets, f, indent=2)

            print(f"Saved target to {self.target_file}")

        except Exception as e:
            print(f"Error saving target: {e}")

    def quit(self):
        if self.main_loop.is_running():
            self.main_loop.quit()

    def run(self):
        GLib.unix_signal_add(GLib.PRIORITY_HIGH,
                             signal.SIGINT, self.handle_sigint)
        GLib.unix_signal_add(GLib.PRIORITY_HIGH,
                             signal.SIGTERM, self.handle_sigint)

        try:
            print("Starting text field searcher...")
            print("Focus on a text field and type 'here' to mark it as a target.")
            print("Press Ctrl+C to exit without saving.")

            # Register for both text change events
            pyatspi.Registry.registerEventListener(
                self.on_text_change,
                'object:text-changed:insert'
            )
            pyatspi.Registry.registerEventListener(
                self.on_text_change,
                'object:text-changed:delete'
            )

            pyatspi.Registry.start(synchronous=False, gil=False)
            self.main_loop.run()

        except Exception as e:
            print(f"Error: {e}")
        finally:
            self.cleanup()

    def handle_sigint(self, *args):
        print("\nReceived interrupt signal")
        self.cleanup()
        return GLib.SOURCE_REMOVE

    def cleanup(self):
        print("Cleaning up...")
        try:
            pyatspi.Registry.deregisterEventListener(
                self.on_text_change,
                'object:text-changed:insert'
            )
            pyatspi.Registry.deregisterEventListener(
                self.on_text_change,
                'object:text-changed:delete'
            )
            pyatspi.Registry.stop()
            self.quit()
        except Exception as e:
            print(f"Error during cleanup: {e}")

        os._exit(0)


if __name__ == "__main__":
    TextFieldSearcher().run()

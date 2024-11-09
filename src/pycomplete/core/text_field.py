from dataclasses import dataclass
from typing import List, Dict, Set, Optional
import pyatspi
import logging

logger = logging.getLogger(__name__)


@dataclass
class TextFieldPath:
    role: int
    name: str
    index: int
    role_name: str


@dataclass
class TextField:
    role: int
    interfaces: Set[str]
    path: List[TextFieldPath]
    name: str
    attributes: Dict[str, str]


class TextFieldManager:
    """Manages text field detection and validation"""

    def __init__(self):
        self.text_field_roles = {
            pyatspi.ROLE_TEXT,
            pyatspi.ROLE_ENTRY,
            pyatspi.ROLE_DOCUMENT_TEXT,
            pyatspi.ROLE_PARAGRAPH,
            pyatspi.ROLE_DOCUMENT_FRAME,
            pyatspi.ROLE_EDITBAR,
            pyatspi.ROLE_TERMINAL,
            pyatspi.ROLE_VIEWPORT,
            pyatspi.ROLE_SCROLL_PANE,
            pyatspi.ROLE_APPLICATION
        }

        self.required_interfaces = {
            'Text',
            'EditableText',
            'Component'
        }

    def is_text_field(self, obj) -> Optional[TextField]:
        """Detect if an object is a valid text field"""
        try:
            role = obj.getRole()
            states = obj.getState()
            interfaces = set(pyatspi.listInterfaces(obj))

            # Special handling for terminals
            if role == pyatspi.ROLE_TERMINAL:
                return self._handle_terminal(obj, states, interfaces)

            # Check basic conditions
            conditions = {
                'role_match': role in self.text_field_roles,
                'has_interfaces': self.required_interfaces.issubset(interfaces),
                'enabled': states.contains(pyatspi.STATE_ENABLED),
                'visible': states.contains(pyatspi.STATE_VISIBLE)
            }

            if all(conditions.values()):
                return TextField(
                    role=role,
                    interfaces=interfaces,
                    path=self._get_path(obj),
                    name=obj.name or 'unnamed',
                    attributes=self._get_attributes(obj)
                )
        except Exception as e:
            logger.debug(f"Error checking text field: {e}")
        return None

    def _handle_terminal(self, obj, states, interfaces):
        """Special handling for terminal windows"""
        if states.contains(pyatspi.STATE_ENABLED) and states.contains(pyatspi.STATE_VISIBLE):
            return TextField(
                role=obj.getRole(),
                interfaces=interfaces,
                path=self._get_path(obj),
                name=obj.name or 'unnamed',
                attributes={}
            )
        return None

    def _get_path(self, obj) -> List[TextFieldPath]:
        """Get accessibility path for an object"""
        path = []
        current = obj
        while current:
            try:
                path.append(TextFieldPath(
                    role=current.getRole(),
                    name=current.name,
                    index=current.getIndexInParent(),
                    role_name=current.getRoleName()
                ))
                current = current.parent
            except Exception:
                break
        return path[::-1]

    def _get_attributes(self, obj) -> Dict[str, str]:
        """Get object attributes"""
        try:
            return dict([attr.split(':', 1) for attr in obj.getAttributes()])
        except Exception:
            return {}

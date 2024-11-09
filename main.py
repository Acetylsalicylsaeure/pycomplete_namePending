from src.pycomplete.app.predictor_app import TextPredictorApp
import argparse
import sys
import logging
import os
import json
import subprocess  # Added missing import


def check_dependencies():
    """Check if required system dependencies are installed"""
    # Check for ydotool
    try:
        subprocess.run(['which', 'ydotool'], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        print("Error: 'ydotool' command not found. Please install it.")
        print("On Ubuntu/Debian: sudo apt install ydotool")
        print("On Arch: sudo pacman -S ydotool")
        return False

    # Check if ydotool service is running
    try:
        result = subprocess.run(
            ['systemctl', '--user', 'is-active', 'ydotool.service'],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print("Error: ydotool service is not running.")
            print("Start it with: systemctl --user start ydotool.service")
            print("To enable on startup: systemctl --user enable ydotool.service")
            return False
    except Exception as e:
        print(f"Error checking ydotool service: {e}")
        return False

    return True


def init_logging(debug_level):
    """Initialize logging configuration"""
    log_level = logging.DEBUG if debug_level > 0 else logging.INFO

    # Create logs directory if it doesn't exist
    log_dir = os.path.expanduser(
        '~/.local/share/pycomplete/logs')  # Updated path
    os.makedirs(log_dir, exist_ok=True)

    # Set up logging to both file and console
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(os.path.join(
                log_dir, 'pycomplete.log')),  # Updated filename
            logging.StreamHandler()
        ]
    )


def get_config_path():
    """Get the path to the config file, creating default if needed"""
    # Use XDG config directory if available
    config_dir = os.getenv('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
    config_dir = os.path.join(config_dir, 'pycomplete')  # Updated path

    # Create config directory if it doesn't exist
    os.makedirs(config_dir, exist_ok=True)

    config_path = os.path.join(config_dir, 'text_field_config.json')

    # Create default config if it doesn't exist
    if not os.path.exists(config_path):
        default_config = {
            'trigger_key': {
                'event_string': 'Tab',
                'key_code': 65289
            }
        }
        with open(config_path, 'w') as f:
            json.dump(default_config, f, indent=2)

    return config_path


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='PyComplete Text Predictor')  # Updated description
    parser.add_argument('-d', '--debug', action='store_true',
                        help='Enable debug logging')
    parser.add_argument('--config', type=str,
                        # Updated help text
                        help='Path to config file (default: ~/.config/pycomplete/text_field_config.json)')
    args = parser.parse_args()

    try:
        # Check dependencies first
        if not check_dependencies():
            sys.exit(1)

        # Initialize logging
        init_logging(1 if args.debug else 0)
        logger = logging.getLogger(__name__)

        # Get config path
        config_path = args.config if args.config else get_config_path()
        logger.info(f"Using config file: {config_path}")

        # Start the application
        logger.info("Starting PyComplete...")  # Updated message
        app = TextPredictorApp(config_path)

        # Print startup message
        print("\nPyComplete is running!")  # Updated message
        print("Type in any supported text field to see predictions.")
        print("Press Tab (or configured key) to accept predictions.")
        print("Press Ctrl+C to exit.")

        # Run the application
        app.run()

    except KeyboardInterrupt:
        print("\nShutting down...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
import argparse
import sys
import logging
import os
import json
import subprocess

logger = logging.getLogger(__name__)


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


def get_config_path():
    """Get the path to the config file, creating default if needed"""
    # Use XDG config directory if available
    config_dir = os.getenv('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
    config_dir = os.path.join(config_dir, 'pycomplete')

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


def setup_logging(debug_level: int):
    """Set up logging configuration"""
    log_levels = {
        0: logging.WARNING,
        1: logging.INFO,
        2: logging.DEBUG
    }
    log_level = log_levels.get(debug_level, logging.DEBUG)

    # Create logs directory if it doesn't exist
    log_dir = os.path.expanduser('~/.local/share/pycomplete/logs')
    os.makedirs(log_dir, exist_ok=True)

    # Configure logging
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(os.path.join(log_dir, 'pycomplete.log')),
            logging.StreamHandler()
        ]
    )

    # Set level for specific loggers
    logging.getLogger('src.pycomplete').setLevel(log_level)

    if debug_level >= 2:
        logging.getLogger('asyncio').setLevel(logging.DEBUG)


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='PyComplete Text Predictor')
    parser.add_argument('-d', '--debug', type=int, default=0,
                        help='Debug level (0=WARNING, 1=INFO, 2=DEBUG)')
    parser.add_argument('--config', type=str,
                        help='Path to config file (default: ~/.config/pycomplete/text_field_config.json)')
    return parser.parse_args()


if __name__ == "__main__":
    # Parse command line arguments
    args = parse_args()

    # Set up logging first
    setup_logging(args.debug)

    try:
        # Check dependencies first
        if not check_dependencies():
            sys.exit(1)

        # Get config path
        config_path = args.config if args.config else get_config_path()
        logger.info(f"Using config file: {config_path}")

        # Import app after logging is configured
        from src.pycomplete.app.predictor_app import TextPredictorApp

        # Start the application
        logger.info("Starting PyComplete...")
        app = TextPredictorApp(config_path, debug_level=args.debug)

        # Print startup message
        print("\nPyComplete is running!")
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

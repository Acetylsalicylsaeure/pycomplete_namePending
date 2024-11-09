import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
import aiohttp
import json
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PredictionResult:
    """Holds the result of a prediction attempt"""
    text: Optional[str]
    metadata: Dict[str, Any]


class TextPredictor(ABC):
    """Abstract base class for text prediction"""

    @abstractmethod
    async def predict(self, text: str) -> PredictionResult:
        """Generate prediction for given text"""
        pass


class LlmPredictor(TextPredictor):
    """Base class for LLM-based predictors"""

    def __init__(self,
                 trigger: str = " ",
                 min_chars: int = 3,
                 idle_delay: float = 1.0):
        """
        Initialize LLM predictor

        Args:
            trigger (str): Character that triggers prediction (default: space)
            min_chars (int): Minimum characters needed before predictions start
            idle_delay (float): Time in seconds to wait before predicting without trigger
        """
        self.trigger = trigger
        self.min_chars = min_chars
        self.idle_delay = idle_delay
        self.last_input_time = 0.0
        self.last_text = ""
        self.logger = logging.getLogger(__name__)
        self.logger.info(
            f"Initialized LLM predictor with: trigger='{trigger}', "
            f"min_chars={min_chars}, idle_delay={idle_delay}s"
        )

    async def predict(self, text: str) -> PredictionResult:
        """Generate prediction using configured LLM"""
        metadata = {
            'trigger_type': None,
            'segment_length': 0,
            'prediction_time': 0,
            'reason': None,
            'input_text': text
        }

        current_time = time.time()
        text_changed = text != self.last_text

        # Update input timing if text changed
        if text_changed:
            self.last_input_time = current_time
            self.last_text = text

        # Check if we should predict
        should_predict, trigger_type, reason = self._should_predict(
            text, current_time)
        metadata.update({
            'trigger_type': trigger_type,
            'reason': reason
        })

        if not should_predict:
            self.logger.debug(f"Skipping prediction: {
                              reason} for text '{text}'")
            return PredictionResult(None, metadata)

        try:
            start_time = time.time()

            # Get the relevant segment for prediction
            segment = self._get_prediction_segment(text)
            if not segment:
                metadata['reason'] = "No valid segment found"
                return PredictionResult(None, metadata)

            metadata['segment_length'] = len(segment)
            self.logger.info(
                f"Starting prediction for '{segment}' "
                f"(trigger: {trigger_type})"
            )

            # Get prediction from specific LLM implementation
            completion = await self._get_llm_prediction(segment)

            if completion:
                metadata['prediction_time'] = time.time() - start_time
                self.logger.info(
                    f"Prediction successful: '{completion}' "
                    f"(took {metadata['prediction_time']:.3f}s)"
                )
                return PredictionResult(completion, metadata)
            else:
                metadata['reason'] = "No completion received"
                self.logger.debug(
                    f"No completion received from LLM for '{segment}'")

        except Exception as e:
            metadata['reason'] = f"Error: {str(e)}"
            self.logger.error(f"Error generating prediction: {
                              e}", exc_info=True)

        return PredictionResult(None, metadata)

    def _should_predict(self, text: str, current_time: float) -> tuple[bool, Optional[str], str]:
        """
        Check if prediction should be attempted

        Returns:
            tuple: (should_predict, trigger_type, reason)
        """
        if not text:
            return False, None, "Empty text"

        if len(text) < self.min_chars:
            return False, None, f"Text too short ({len(text)} < {self.min_chars})"

        # Check for trigger character
        if text.endswith(self.trigger):
            self.logger.debug(
                f"Trigger character detected at end of: '{text}'")
            return True, "trigger_char", "Trigger character detected"

        # Check for idle timeout
        time_since_input = current_time - self.last_input_time
        if time_since_input >= self.idle_delay:
            if not text.endswith(self.trigger):
                self.logger.debug(
                    f"Idle timeout ({time_since_input:.2f}s) for text: '{text}'")
                return True, "idle_timeout", f"Idle timeout ({time_since_input:.2f}s)"

        return False, None, "No trigger condition met"

    def _get_prediction_segment(self, text: str) -> Optional[str]:
        """Get the appropriate text segment for prediction"""
        if text.endswith(self.trigger):
            # If triggered by space, use last complete segment
            segments = text.split(self.trigger)
            segments = [s.strip() for s in segments if s.strip()]
            return segments[-1] if segments else None
        else:
            # If triggered by idle timeout, use current incomplete segment
            segments = text.split(self.trigger)
            last_segment = segments[-1].strip()
            return last_segment if last_segment else None


class OllamaPredictor(LlmPredictor):
    """Predictor that uses Ollama server for text completion"""

    def __init__(self,
                 model: str = "mistral",
                 base_url: str = "http://localhost:11434",
                 session: Optional[aiohttp.ClientSession] = None,
                 trigger: str = " ",
                 min_chars: int = 3,
                 idle_delay: float = 1.0):
        """Initialize Ollama predictor"""
        super().__init__(trigger=trigger, min_chars=min_chars, idle_delay=idle_delay)
        self.model = model
        self.base_url = base_url.rstrip('/')
        self.session = session
        self._connection_verified = False

        # Ensure session is available
        if not self.session:
            raise ValueError("aiohttp session is required")

        self.logger.info(
            f"Initialized Ollama predictor with model '{model}' "
            f"(trigger='{trigger}', idle_delay={idle_delay}s)"
        )

    async def verify_connection(self) -> bool:
        """Verify connection to Ollama server"""
        try:
            self.logger.debug("Verifying connection to Ollama server...")
            url = f"{self.base_url}/api/generate"
            data = {
                "model": self.model,
                "prompt": "test",
                "options": {"max_tokens": 1}
            }

            async with self.session.post(url, json=data) as response:
                if response.status != 200:
                    self.logger.error(f"Failed to connect to Ollama server: Status {
                                      response.status}")
                    return False
                self.logger.info("Successfully connected to Ollama server")
                return True
        except Exception as e:
            self.logger.error(f"Failed to connect to Ollama server: {e}")
            return False

    async def _get_llm_prediction(self, text: str) -> Optional[str]:
        """Generate prediction using Ollama server"""
        try:
            # Verify connection before first prediction
            if not self._connection_verified:
                if not await self.verify_connection():
                    self.logger.error(
                        "Cannot generate prediction: Ollama server not available")
                    return None
                self._connection_verified = True

            self.logger.info(f"Sending request to Ollama for text: '{text}'")
            url = f"{self.base_url}/api/generate"
            data = {
                "model": self.model,
                "prompt": f"Complete this sentence naturally and briefly: {text}",
                "stream": True,
                "options": {
                    "temperature": 0.7,
                    "top_k": 50,
                    "top_p": 0.9,
                    "max_tokens": 20,
                }
            }

            completion = ""
            start_time = time.time()

            async with self.session.post(url, json=data) as response:
                if response.status != 200:
                    self.logger.error(f"Ollama server returned status {
                                      response.status}")
                    return None

                async for line in response.content:
                    try:
                        chunk = json.loads(line)
                        if 'response' in chunk:
                            completion += chunk['response']
                        if chunk.get('done', False):
                            break
                    except json.JSONDecodeError as e:
                        self.logger.error(f"Error decoding JSON chunk: {e}")
                        continue

            elapsed = time.time() - start_time
            if completion.strip():
                self.logger.info(
                    f"Ollama response received in {
                        elapsed:.3f}s: '{completion.strip()}'"
                )
            else:
                self.logger.warning(
                    f"Empty completion received from Ollama after {elapsed:.3f}s")
            return completion.strip()

        except Exception as e:
            self.logger.error(f"Error in Ollama prediction: {
                              e}", exc_info=True)
            return None

    async def cleanup(self):
        """Cleanup resources - nothing to do as session is managed externally"""
        pass

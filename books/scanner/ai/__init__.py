"""AI-powered filename pattern recognition module."""

from .filename_recognizer import FilenamePatternRecognizer, initialize_ai_system

# Flag indicating if AI module is available
ai_module_available = True

__all__ = ["FilenamePatternRecognizer", "initialize_ai_system", "ai_module_available"]

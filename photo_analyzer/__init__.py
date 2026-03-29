"""Photo analyzer package."""

from .core import ANALYSIS_VERSION, AnalysisError, AnalysisResult, analyze_image

__version__ = ANALYSIS_VERSION

__all__ = ["ANALYSIS_VERSION", "AnalysisError", "AnalysisResult", "__version__", "analyze_image"]

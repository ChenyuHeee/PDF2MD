"""PDF2MD: convert text-based PDFs (papers, ebooks) to clean Markdown."""

from .converter import Converter, ConvertOptions, convert

__all__ = ["Converter", "ConvertOptions", "convert"]
__version__ = "0.1.0"

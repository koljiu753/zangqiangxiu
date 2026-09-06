from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .similarity import ALGORITHM_VERSION, extract_feature


class ProviderNotConfigured(RuntimeError):
    """Raised when an optional AI provider has not been installed/configured."""


class EmbeddingProvider(ABC):
    name = "unconfigured"
    model_version: str | None = None
    dimensions: int | None = None
    semantic = False

    @abstractmethod
    def embed(self, image_path: Path) -> list[float]: ...


class ClassificationProvider(ABC):
    name = "unconfigured"
    model_version: str | None = None

    @abstractmethod
    def classify(self, image_path: Path) -> list[dict[str, Any]]: ...


class GenerationProvider(ABC):
    name = "unconfigured"
    model_version: str | None = None

    @abstractmethod
    def generate(self, prompt: str, reference_paths: list[Path], parameters: dict[str, Any]) -> list[Path]: ...


class UnconfiguredEmbeddingProvider(EmbeddingProvider):
    def embed(self, image_path: Path) -> list[float]:
        raise ProviderNotConfigured("Embedding provider is not configured")


class UnconfiguredClassificationProvider(ClassificationProvider):
    def classify(self, image_path: Path) -> list[dict[str, Any]]:
        raise ProviderNotConfigured("Classification provider is not configured")


class UnconfiguredGenerationProvider(GenerationProvider):
    def generate(self, prompt: str, reference_paths: list[Path], parameters: dict[str, Any]) -> list[Path]:
        raise ProviderNotConfigured("Generation provider is not configured")


class InterpretableEmbeddingProvider(EmbeddingProvider):
    """Deterministic image embedding used by the built-in similarity baseline."""

    name = "zhixiu-interpretable-image-feature"
    model_version = ALGORITHM_VERSION
    dimensions = 128

    def embed(self, image_path: Path) -> list[float]:
        return extract_feature(image_path)

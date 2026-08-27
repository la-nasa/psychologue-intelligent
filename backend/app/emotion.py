from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

_TOKEN_PATTERN = re.compile(r"(?u)\b\w\w+\b")


class EmotionModel(Protocol):
    version: str
    def predict(self, text: str) -> dict[str, float]: ...


@dataclass(frozen=True)
class EmotionPrediction:
    label: str
    confidence: float
    distribution: dict[str, float]


class TfidfLogisticEmotionModel:
    """Pure-Python inference for a linear (TF-IDF + logistic regression) model
    trained by ml/train_emotion_classifier.py. Deliberately reimplements TF-IDF
    scoring and the linear decision function by hand instead of depending on
    scikit-learn/numpy at runtime, so the deployed app keeps its zero-dependency
    footprint (ADR-003) -- scikit-learn is a training-time tool only.

    This is a research-grade signal, never a clinical one: see ml/MODEL_CARD.md.
    It has no path into backend/app/crisis.py and cannot affect an alert level."""

    def __init__(self, artifact_path: Path):
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        self.version: str = data["version"]
        self.labels: list[str] = data["labels"]
        self.vocabulary: dict[str, int] = data["vocabulary"]
        self.idf: list[float] = data["idf"]
        self.coefficients: list[list[float]] = data["coefficients"]
        self.intercept: list[float] = data["intercept"]

    def _tfidf_vector(self, text: str) -> dict[int, float]:
        tokens = _TOKEN_PATTERN.findall(text.lower())
        counts = Counter(tokens)
        weighted = {
            self.vocabulary[token]: count * self.idf[self.vocabulary[token]]
            for token, count in counts.items()
            if token in self.vocabulary
        }
        norm = math.sqrt(sum(value * value for value in weighted.values()))
        if norm == 0:
            return {}
        return {index: value / norm for index, value in weighted.items()}

    def predict(self, text: str) -> dict[str, float]:
        vector = self._tfidf_vector(text)
        scores = []
        for class_index, class_coefficients in enumerate(self.coefficients):
            score = self.intercept[class_index] + sum(
                class_coefficients[feature_index] * value for feature_index, value in vector.items()
            )
            scores.append(score)
        max_score = max(scores)
        exponentials = [math.exp(score - max_score) for score in scores]
        total = sum(exponentials)
        probabilities = [value / total for value in exponentials]
        return dict(zip(self.labels, probabilities, strict=True))


def top_prediction(model: EmotionModel, text: str) -> EmotionPrediction:
    distribution = model.predict(text)
    label, confidence = max(distribution.items(), key=lambda item: item[1])
    return EmotionPrediction(label=label, confidence=confidence, distribution=distribution)

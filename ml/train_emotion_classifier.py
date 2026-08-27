#!/usr/bin/env python
"""Train a small, honestly-scoped emotion classifier.

This demonstrates a real, working training/evaluation pipeline behind the
ModelProvider abstraction the master prompt asks for (Section 13). It is NOT
a clinical risk model and NEVER decides crisis framing: backend/app/crisis.py
and backend/app/responder.py do not consume its output at all. It is wired
in (backend/app/emotion.py) purely as an additional, clearly-labeled,
research-grade signal recorded for future clinical review -- see the model
card written alongside the exported artifact for the full scope and limits.

Dataset: GoEmotions (Demszky et al., 2020, ACL) -- Google Research,
Apache-2.0 license, ~58k human-annotated Reddit comments. Fetched at train
time directly from the public GitHub mirror; never redistributed by this
repo (only the trained weights are committed, as plain JSON, not the text).
The 27 fine-grained labels are collapsed to Ekman's 6 basic emotions using
Google's own published mapping; multi-label and neutral-only rows are
dropped to keep this a clean single-label task appropriate for a linear
model. Requires scikit-learn (a training-time tool, not a runtime
dependency of the application -- see pyproject.toml's dev extra).
"""
from __future__ import annotations

import csv
import json
import sys
import time
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix

BASE_URL = "https://raw.githubusercontent.com/google-research/google-research/master/goemotions/data"
ML_DIR = Path(__file__).resolve().parent
DATA_DIR = ML_DIR / "data"
ARTIFACT_PATH = ML_DIR / "artifacts" / "emotion-classifier-v1.json"
MODEL_CARD_PATH = ML_DIR / "MODEL_CARD.md"
VERSION = "emotion-classifier-dev-1"
MAX_FEATURES = 8000


def _fetch(name: str) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = DATA_DIR / name
    if not dest.exists():
        last_error: Exception | None = None
        for _attempt in range(5):
            try:
                urllib.request.urlretrieve(f"{BASE_URL}/{name}", dest)
                last_error = None
                break
            except Exception as error:  # network resets happen; retry with backoff
                last_error = error
                time.sleep(2)
        if last_error is not None:
            raise RuntimeError(f"failed to fetch {name}") from last_error
    return dest


def load_split(name: str, emotion_names: list[str], ekman_mapping: dict[str, str]) -> tuple[list[str], list[str]]:
    path = _fetch(name)
    texts, labels = [], []
    with path.open(encoding="utf-8") as handle:
        for row in csv.reader(handle, delimiter="\t"):
            text, label_ids, _ = row
            fine_names = {emotion_names[int(i)] for i in label_ids.split(",")}
            ekman_labels = {ekman_mapping[fine] for fine in fine_names if fine in ekman_mapping}
            if len(ekman_labels) == 1:
                texts.append(text)
                labels.append(next(iter(ekman_labels)))
    return texts, labels


def export_artifact(vectorizer: TfidfVectorizer, classifier: LogisticRegression, test_accuracy: float, test_macro_f1: float) -> None:
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": VERSION,
        "trained_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "dataset": "GoEmotions (Demszky et al. 2020, Apache-2.0), Ekman 6-category collapse",
        "labels": classifier.classes_.tolist(),
        "vocabulary": {term: int(index) for term, index in vectorizer.vocabulary_.items()},
        "idf": vectorizer.idf_.tolist(),
        "coefficients": classifier.coef_.tolist(),
        "intercept": classifier.intercept_.tolist(),
        "test_accuracy": test_accuracy,
        "test_macro_f1": test_macro_f1,
    }
    ARTIFACT_PATH.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {ARTIFACT_PATH} ({ARTIFACT_PATH.stat().st_size:,} bytes)")


def write_model_card(counts: dict[str, int], distribution: Counter, report_text: str, confusion: list[list[int]], labels: list[str]) -> None:
    confusion_rows = "\n".join(
        "| " + label + " | " + " | ".join(str(v) for v in row) + " |"
        for label, row in zip(labels, confusion, strict=True)
    )
    MODEL_CARD_PATH.write_text(f"""# Model card -- {VERSION}

## What this is

A small, linear (TF-IDF + logistic regression) text emotion classifier. It is
a research-grade demonstration of a real, working training/evaluation
pipeline behind the project's `ModelProvider` abstraction -- **not a
clinical tool**.

## What this is NOT

- Not a suicide-risk or crisis-detection model. It never runs inside
  `backend/app/crisis.py` and has no influence on ORANGE/RED decisions or
  alert thresholds. Those come exclusively from the independent rule engine
  and the (separate, unrelated) `RiskModel` port, per ADR-004.
- Not clinically validated. No psychologist, psychiatrist, or clinical
  reviewer has assessed its outputs. It must never be described to a
  patient or clinician as diagnostic or authoritative.
- Not fine-tuned or adapted to therapy-chat language: it is trained on
  Reddit comments (see Limitations).

## Dataset

[GoEmotions](https://github.com/google-research/google-research/tree/master/goemotions)
(Demszky et al., 2020, ACL) -- ~58k Reddit comments, human-annotated,
27 fine-grained emotions + neutral, Apache-2.0 license, Google Research.
Chosen over the more commonly cited `dair-ai/emotion` dataset because its
license is unambiguous (Apache-2.0 vs. dair-ai's "other") and its labels
are human-annotated rather than derived by distant supervision from
hashtags. The raw dataset text is not redistributed by this repository;
only the trained weights are committed.

The 27 fine-grained labels are collapsed to Ekman's 6 basic emotions
(anger, disgust, fear, joy, sadness, surprise) using Google's own published
mapping (`ekman_mapping.json` in the GoEmotions repo). Rows labeled only
`neutral`, or with labels spanning more than one Ekman category, are
dropped to keep this a clean single-label classification task.

## Data split sizes (after collapsing and filtering)

| Split | Rows |
| --- | --- |
| train | {counts['train']} |
| dev | {counts['dev']} |
| test | {counts['test']} |

Train label distribution: {dict(distribution)}

## Model

TF-IDF (unigrams, max {MAX_FEATURES} features, min_df=2) + multinomial
logistic regression (`class_weight="balanced"`, `C=2.0`). Chosen over a
larger neural/transformer model deliberately: it is fast enough to run
without any runtime ML dependency (see `backend/app/emotion.py`, which
reimplements TF-IDF scoring and the linear decision function in pure
Python from the exported weights -- scikit-learn is only needed at
training time), and its coefficients are directly inspectable.

## Held-out test set results

```
{report_text}
```

Confusion matrix (rows = true label, columns = predicted, order: {labels}):

| true \\ pred | {" | ".join(labels)} |
| --- | {" | ".join("---" for _ in labels)} |
{confusion_rows}

## Limitations

- English only; trained on Reddit comments, a different register than a
  therapeutic chat message. Accuracy on this project's actual traffic is
  unmeasured and likely lower than the held-out numbers above.
- The Ekman 6-category collapse loses the nuance of GoEmotions' original
  27 labels (e.g. "grief" and "disappointment" both become "sadness").
- A linear bag-of-words model cannot capture negation, sarcasm, or
  multi-sentence context well.
- Class imbalance in the source data (see distribution above) means
  rarer classes (e.g. surprise, disgust) are less reliably predicted.

## Governance

Per ADR-002/ADR-004, no unvalidated model output may influence a clinical
or safety decision. This model's predictions are recorded for observability
and future clinician review only (see `risk_assessments.emotion_label` /
`emotion_confidence`); they do not feed into `crisis.CrisisDetector` and
cannot change an alert level. Promoting this signal to something that does
influence a decision would require the same approval workflow as any other
clinical policy change.
""", encoding="utf-8")
    print(f"wrote {MODEL_CARD_PATH}")


def main() -> None:
    emotion_names = _fetch("emotions.txt").read_text(encoding="utf-8").splitlines()
    ekman_raw = json.loads(_fetch("ekman_mapping.json").read_text(encoding="utf-8"))
    ekman_mapping = {fine: coarse for coarse, fines in ekman_raw.items() for fine in fines}

    train_texts, train_labels = load_split("train.tsv", emotion_names, ekman_mapping)
    dev_texts, dev_labels = load_split("dev.tsv", emotion_names, ekman_mapping)
    test_texts, test_labels = load_split("test.tsv", emotion_names, ekman_mapping)

    counts = {"train": len(train_texts), "dev": len(dev_texts), "test": len(test_texts)}
    print(f"rows: {counts}")
    distribution = Counter(train_labels)
    print("train label distribution:", dict(distribution))

    vectorizer = TfidfVectorizer(max_features=MAX_FEATURES, ngram_range=(1, 1), min_df=2, lowercase=True)
    x_train = vectorizer.fit_transform(train_texts)
    x_dev = vectorizer.transform(dev_texts)
    x_test = vectorizer.transform(test_texts)

    classifier = LogisticRegression(max_iter=2000, class_weight="balanced", C=2.0)
    classifier.fit(x_train, train_labels)

    dev_accuracy = classifier.score(x_dev, dev_labels)
    print(f"dev accuracy: {dev_accuracy:.4f}")

    test_predictions = classifier.predict(x_test)
    report_dict = classification_report(test_labels, test_predictions, output_dict=True)
    report_text = classification_report(test_labels, test_predictions)
    print(report_text)

    labels = classifier.classes_.tolist()
    confusion = confusion_matrix(test_labels, test_predictions, labels=labels).tolist()

    export_artifact(vectorizer, classifier, report_dict["accuracy"], report_dict["macro avg"]["f1-score"])
    write_model_card(counts, distribution, report_text, confusion, labels)


if __name__ == "__main__":
    sys.exit(main())

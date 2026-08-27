# Model card -- emotion-classifier-dev-1

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
| train | 28104 |
| dev | 3527 |
| test | 3539 |

Train label distribution: {'anger': 4590, 'fear': 566, 'surprise': 4160, 'joy': 15809, 'sadness': 2455, 'disgust': 524}

## Model

TF-IDF (unigrams, max 8000 features, min_df=2) + multinomial
logistic regression (`class_weight="balanced"`, `C=2.0`). Chosen over a
larger neural/transformer model deliberately: it is fast enough to run
without any runtime ML dependency (see `backend/app/emotion.py`, which
reimplements TF-IDF scoring and the linear decision function in pure
Python from the exported weights -- scikit-learn is only needed at
training time), and its coefficients are directly inspectable.

## Held-out test set results

```
              precision    recall  f1-score   support

       anger       0.54      0.59      0.57       609
     disgust       0.32      0.55      0.40        77
        fear       0.49      0.69      0.58        85
         joy       0.91      0.75      0.82      1937
     sadness       0.50      0.57      0.53       298
    surprise       0.52      0.66      0.58       533

    accuracy                           0.69      3539
   macro avg       0.55      0.64      0.58      3539
weighted avg       0.73      0.69      0.70      3539

```

Confusion matrix (rows = true label, columns = predicted, order: ['anger', 'disgust', 'fear', 'joy', 'sadness', 'surprise']):

| true \ pred | anger | disgust | fear | joy | sadness | surprise |
| --- | --- | --- | --- | --- | --- | --- |
| anger | 362 | 39 | 12 | 50 | 48 | 98 |
| disgust | 15 | 42 | 4 | 4 | 7 | 5 |
| fear | 9 | 4 | 59 | 5 | 6 | 2 |
| joy | 173 | 21 | 25 | 1454 | 77 | 187 |
| sadness | 40 | 12 | 12 | 27 | 170 | 37 |
| surprise | 71 | 15 | 8 | 54 | 31 | 354 |

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

from __future__ import annotations

from dataclasses import dataclass

PHQ9_VERSION = "PHQ-9-1"


@dataclass(frozen=True)
class Phq9Result:
    total_score: int
    item9_score: int


def calculate(answers: list[int]) -> Phq9Result:
    if not isinstance(answers, list) or len(answers) != 9 or any(type(value) is not int or not 0 <= value <= 3 for value in answers):
        raise ValueError("PHQ-9 requires exactly nine integer answers between 0 and 3")
    return Phq9Result(total_score=sum(answers), item9_score=answers[8])

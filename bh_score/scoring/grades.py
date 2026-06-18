"""Grade ladder (data-driven, Phase-0 FROZEN; SCORING_SPEC §5). grade 0 = COMPLETE.

Each ladder is (score_field, [(comparator, threshold, grade), ...]) evaluated top to
bottom; the first matching rung wins. The live ladders in SCORING_SPEC §5 are venue
keyed (Charcoalroom / Office / Kiyoung / Jungsooksung), but our capture key carries no
venue, so we key by meat and ship the beef maillard ladder verbatim; other meats fall
through to an "approx" label. This is P1 context, not the demo hero, so the honest
minimum (no fabricated venue mapping) is correct here.
"""
from __future__ import annotations

GRADE_LABELS = {
    0: "COMPLETE",
    1: "RAW",
    2: "RARE",
    3: "MEDIUM",
    4: "WELL",
    5: "OVER",
}

# (score_field, [(op, threshold, grade)]) — op is 'gt' or 'ge'.
GRADE_LADDERS = {
    # Charcoalroom beef on maillard_score (SCORING_SPEC §5).
    "beef": ("maillard_score", [
        ("gt", 50, 5),
        ("gt", 30, 0),
        ("gt", 12, 4),
        ("gt", 8, 3),
        ("gt", 5, 2),
    ]),
}
_DEFAULT_GRADE = 1  # falls through to the else rung


def gradeFor(menu, scoreFields):
    """Return (grade, grade_label). scoreFields is a dict of score-field values
    (e.g. {'maillard_score': 18.0}). Unknown meats return (-1, 'approx')."""
    meat = menu.split("/", 1)[0]
    ladder = GRADE_LADDERS.get(meat)
    if ladder is None:
        return -1, "approx"
    field, rungs = ladder
    value = scoreFields.get(field, 0.0)
    for op, threshold, grade in rungs:
        if (op == "gt" and value > threshold) or (op == "ge" and value >= threshold):
            return grade, GRADE_LABELS.get(grade, str(grade))
    return _DEFAULT_GRADE, GRADE_LABELS[_DEFAULT_GRADE]

import re
import math
from collections import Counter
import cv2
import numpy as np
import os

FED = {
    "A": "Boston",
    "B": "New York",
    "C": "Philadelphia",
    "D": "Cleveland",
    "E": "Richmond",
    "F": "Atlanta",
    "G": "Chicago",
    "H": "St. Louis",
    "I": "Minneapolis",
    "J": "Kansas City",
    "K": "Dallas",
    "L": "San Francisco",
}

DENOMS = [1, 2, 5, 10, 20, 50, 100]

DAMPEN = {
    1: 1,
    2: 0.9,
    5: 0.5,
    10: 0.3,
    20: 0.2,
    50: 0.12,
    100: 0.08,
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def preprocess_star(image, size=(60, 60)):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, size)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    gray = cv2.threshold(
        gray,
        0,
        255,
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )[1]

    return gray


def load_star_samples(folder):
    samples = []

    if not os.path.exists(folder):
        return samples

    for filename in os.listdir(folder):
        path = os.path.join(folder, filename)
        image = cv2.imread(path)

        if image is None:
            continue

        samples.append(preprocess_star(image))

    return samples


def compare_image(sample, reference):
    result = cv2.matchTemplate(
        sample,
        reference,
        cv2.TM_CCOEFF_NORMED
    )

    return float(result[0][0])


def detect_star(star_crop, star_folder=None, no_star_folder=None):
    if star_folder is None:
        star_folder = os.path.join(BASE_DIR, "Samples", "star")

    if no_star_folder is None:
        no_star_folder = os.path.join(BASE_DIR, "Samples", "no_star")

    image = preprocess_star(star_crop)

    star_samples = load_star_samples(star_folder)
    no_star_samples = load_star_samples(no_star_folder)

    if not star_samples or not no_star_samples:
        return None

    star_scores = [
        compare_image(image, sample)
        for sample in star_samples
    ]

    no_star_scores = [
        compare_image(image, sample)
        for sample in no_star_samples
    ]

    star_scores.sort(reverse=True)
    no_star_scores.sort(reverse=True)

    star_score = np.mean(star_scores[:3])
    no_star_score = np.mean(no_star_scores[:3])

    has_star = star_score > no_star_score

    return {
        "has_star": bool(has_star),
        "star_score": float(star_score),
        "no_star_score": float(no_star_score),
        "confidence": float(abs(star_score - no_star_score))
    }


def parse_serial(raw):
    s = re.sub(r"[\s-]", "", str(raw).upper())

    match = re.fullmatch(
        r"([A-Z]{1,2})(\d{8})([A-Z*])",
        s
    )

    if not match:
        return {
            "ok": False,
            "cleaned": s
        }

    return {
        "ok": True,
        "cleaned": s,
        "prefix": match.group(1),
        "digits": match.group(2),
        "suffix": match.group(3),
    }


def valid_date(mm, dd, yyyy):
    if mm < 1 or mm > 12 or dd < 1:
        return False

    leap_year = (
        yyyy % 4 == 0
        and (yyyy % 100 != 0 or yyyy % 400 == 0)
    )

    days_in_month = [
        31,
        29 if leap_year else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31
    ]

    return dd <= days_in_month[mm - 1]


def analyze(p):
    d = p["digits"]
    n = int(d)

    out = []

    def add(feature_id, label, mult, desc):
        out.append({
            "id": feature_id,
            "label": label,
            "mult": mult,
            "desc": desc,
        })

    counts = Counter(d)
    max_same = max(counts.values())
    solid = max_same == 8

    if solid:
        add(
            "solid",
            "Solid",
            400,
            "All eight digits are identical."
        )

    elif max_same == 7:
        add(
            "near",
            "Near-solid",
            30,
            "Seven of the eight digits are the same."
        )

    going_up = all(
        i == 0 or int(d[i]) - int(d[i - 1]) == 1
        for i in range(len(d))
    )

    going_down = all(
        i == 0 or int(d[i]) - int(d[i - 1]) == -1
        for i in range(len(d))
    )

    if going_up:
        add(
            "ladder",
            "True ladder",
            60,
            f"Digits count up in order, like {d}."
        )

    elif going_down:
        add(
            "ladder",
            "Descending ladder",
            60,
            f"Digits count down in order, like {d}."
        )

    if not solid and re.fullmatch(r"[01]{8}", d):
        add(
            "binary",
            "Binary",
            40,
            "Only 0s and 1s."
        )

    if not solid and d == d[::-1]:
        add(
            "radar",
            "Radar",
            6,
            "Reads the same forwards and backwards."
        )

    if not solid:
        if d[:2] * 4 == d:
            add(
                "repeater2",
                "Quad repeater",
                8,
                "A two-digit pair repeats four times."
            )

        elif d[:4] == d[4:]:
            add(
                "repeater",
                "Repeater",
                5,
                "The first four digits repeat."
            )

    rot = {
        "0": "0",
        "1": "1",
        "6": "9",
        "8": "8",
        "9": "6",
    }

    if not solid and all(c in rot for c in d):
        rotated = "".join(
            rot[c]
            for c in reversed(d)
        )

        if rotated == d:
            add(
                "rotator",
                "Rotator",
                8,
                "Reads the same upside down."
            )

    if 1 <= n <= 100:
        add(
            "low",
            "Ultra-low serial",
            100,
            "Among the first 100 printed for its series."
        )

    elif n <= 1000:
        add(
            "low",
            "Low serial",
            12,
            "Under 1,000."
        )

    elif n <= 10000:
        add(
            "low",
            "Low-ish serial",
            2.5,
            "Under 10,000."
        )

    if n >= 99_999_000:
        add(
            "high",
            "High serial",
            3,
            "Within the last thousand of the run."
        )

    mm = int(d[:2])
    dd = int(d[2:4])
    yy = int(d[4:])

    if (
        ((1900 <= yy <= 2026) or yy == 1776)
        and valid_date(mm, dd, yy)
    ):
        add(
            "date",
            "Date serial",
            3,
            f"Reads as a date: {mm}/{dd}/{yy}."
        )

    if p["suffix"] == "*":
        add(
            "star",
            "Star note",
            4,
            "A replacement note, printed to replace a damaged sheet."
        )

    return sorted(
        out,
        key=lambda x: x["mult"],
        reverse=True
    )


def combined_multiplier(features):
    if not features:
        return 1

    main_multiplier = features[0]["mult"]

    extras = sum(
        feature["mult"] - 1
        for feature in features[1:]
    )

    return main_multiplier + 0.3 * extras


def value_bill(features, denom, condition=1.0):
    multiplier = combined_multiplier(features)

    premium = (
        (multiplier - 1)
        * denom
        * DAMPEN[denom]
        * condition
    )

    estimate = denom + premium

    if features:
        low = max(denom, estimate * 0.7)
        high = estimate * 1.6
    else:
        low = denom
        high = denom

    score = min(
        100,
        round(
            100 * math.log(multiplier)
            / math.log(500)
        )
    )

    if multiplier <= 1:
        tier = "Common"
    elif multiplier < 4:
        tier = "Uncommon"
    elif multiplier < 15:
        tier = "Rare"
    elif multiplier < 80:
        tier = "Very rare"
    else:
        tier = "Legendary"

    return {
        "m": multiplier,
        "est": estimate,
        "low": low,
        "high": high,
        "score": score,
        "tier": tier,
    }
import cv2
import numpy as np
import easyocr
import json
import os
import re
import processing

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PLACEMENT_FILE = os.path.join(BASE_DIR, "placement.json")

reader = easyocr.Reader(["en"], gpu=False)


# Make a flat bill image
def transform_bill(image, corners, width=1000, height=420):
    rect = order_points(corners)

    destination = np.array([
        [0, 0],
        [width - 1, 0],
        [width - 1, height - 1],
        [0, height - 1]
    ], dtype=np.float32)

    matrix = cv2.getPerspectiveTransform(rect, destination)
    return cv2.warpPerspective(image, matrix, (width, height))

def order_points(pts):
    rect = np.zeros((4, 2), dtype=np.float32)

    s = pts.sum(axis=1)

    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]

    diff = np.diff(pts, axis=1).flatten()

    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]

    return rect

def find_bill(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Blur to reduce noise
    gray = cv2.GaussianBlur(gray, (5, 5), 0)

    # Find edges
    edges = cv2.Canny(gray, 50, 150)

    # Make edge boundaries more connected
    kernel = np.ones((5, 5), np.uint8)
    edges = cv2.dilate(edges, kernel, iterations=1)


    # Find contours
    contours, _ = cv2.findContours(
        edges,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    # Check biggest contours first
    contours = sorted(
        contours,
        key=cv2.contourArea,
        reverse=True
    )

    for contour in contours:
        perimeter = cv2.arcLength(contour, True)

        approx = cv2.approxPolyDP(
            contour,
            0.02 * perimeter,
            True
        )

        if len(approx) == 4:
            area = cv2.contourArea(approx)

            if area > image.shape[0] * image.shape[1] * 0.1:
                return approx.reshape(4, 2).astype(np.float32)

    return None

def load_placement():
    with open(PLACEMENT_FILE, "r") as file:
        return json.load(file)


def get_bounds(data, denom, name):
    if denom is not None:
        section = data.get(str(denom), {})

        if name in section:
            return section[name]

    default = data.get("default", {})
    return default.get(name)


def crop_bill(bill, bounds):
    if not bounds:
        return None

    y1, y2, x1, x2 = bounds
    return bill[y1:y2, x1:x2]


def read_text(crop, allowlist):
    if crop is None or crop.size == 0:
        return ""

    results = reader.readtext(
        crop,
        allowlist=allowlist
    )

    results.sort(
        key=lambda result: min(point[0] for point in result[0])
    )

    return "".join(result[1] for result in results)


def read_denomination(bill, data):
    bounds = get_bounds(
        data,
        None,
        "Denom"
    )

    crop = crop_bill(
        bill,
        bounds
    )

    text = read_text(
        crop,
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ "
    )

    text = text.upper()

    print(
        "Denomination text:",
        text
    )

    if "HUNDRED" in text:
        return 100

    if "FIFTY" in text:
        return 50

    if "TWENTY" in text:
        return 20

    if "TEN" in text:
        return 10

    if "FIVE" in text:
        return 5

    if "TWO" in text:
        return 2

    return 1


def clean_serial(raw):
    return re.sub(r"[^A-Z0-9*]", "", raw.upper())


def read_serial(bill, data, denom):
    bounds = get_bounds(data, denom, "Serial")
    crop = crop_bill(bill, bounds)

    text = read_text(
        crop,
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789*"
    )

    return clean_serial(text)


def apply_star(serial, has_star):
    if not has_star:
        return serial

    match = re.search(r"([A-Z]{1,2})(\d{8})", serial)

    if not match:
        return serial

    return match.group(1) + match.group(2) + "*"


def get_star_result(bill, data, denom):
    bounds = get_bounds(data, denom, "Star")
    crop = crop_bill(bill, bounds)

    if crop is None or crop.size == 0:
        return None

    return processing.detect_star(crop)


def evaluate_serial(serial, denom, condition=1.0):
    p = processing.parse_serial(serial)

    if not p["ok"]:
        return {
            "ok": False,
            "error": "Could not read a valid serial number.",
            "serial": p["cleaned"],
            "denom": denom
        }

    if denom not in processing.DENOMS:
        return {
            "ok": False,
            "error": "Could not read the denomination. Pick it manually below.",
            "serial": p["cleaned"],
            "denom": None
        }

    features = processing.analyze(p)
    value = processing.value_bill(features, denom, condition)

    district = processing.FED.get(p["prefix"][0], "Unknown")

    return {
        "ok": True,
        "serial": p["cleaned"],
        "denom": denom,
        "district": district,
        "features": features,
        "value": value
    }


def analyze_image(image, condition=1.0):
    if image is None:
        return {
            "ok": False,
            "error": "Could not load image."
        }

    print("Image size:", image.shape)

    corners = find_bill(image)

    if corners is None:
        print("Could not get corners of bill")

        return {
            "ok": False,
            "error": "Could not get corners of bill."
        }

    print("Corners:")
    print(corners)

    debug = image.copy()

    for point in corners:
        x = int(point[0])
        y = int(point[1])

        cv2.circle(
            debug,
            (x, y),
            15,
            (0, 0, 255),
            -1
        )

    bill = transform_bill(
        image,
        corners
    )

    cv2.imwrite(
        "bill_flat.jpg",
        bill
    )

    data = load_placement()

    denom = read_denomination(
        bill,
        data
    )

    serial = read_serial(
        bill,
        data,
        denom
    )

    star_result = get_star_result(
        bill,
        data,
        denom
    )

    if star_result is not None:
        serial = apply_star(
            serial,
            star_result["has_star"]
        )

    result = evaluate_serial(
        serial,
        denom,
        condition
    )

    result["star_detection"] = star_result

    return result
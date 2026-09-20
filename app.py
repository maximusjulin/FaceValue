from flask import Flask, render_template, request, jsonify
import cv2
import numpy as np
import detector

app = Flask(__name__)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    file = request.files.get("image")

    if file is None:
        return jsonify({
            "ok": False,
            "error": "No image was sent."
        })

    image_bytes = file.read()
    image_array = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

    if image is None:
        return jsonify({
            "ok": False,
            "error": "That file could not be opened as an image."
        })

    try:
        condition = float(request.form.get("condition", 1.0))
    except ValueError:
        condition = 1.0

    result = detector.analyze_image(image, condition)
    return jsonify(result)


@app.route("/evaluate", methods=["POST"])
def evaluate():
    data = request.get_json() or {}

    serial = data.get("serial", "")
    denom = data.get("denom")
    condition = data.get("condition", 1.0)

    try:
        denom = int(denom)
        condition = float(condition)
    except (TypeError, ValueError):
        return jsonify({
            "ok": False,
            "error": "Invalid denomination or condition."
        })

    result = detector.evaluate_serial(serial, denom, condition)
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
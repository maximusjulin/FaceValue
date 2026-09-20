const fileInput = document.getElementById("file")
const previewArea = document.getElementById("previewArea")
const canvas = document.getElementById("preview")
const ctx = canvas.getContext("2d")

const leftButton = document.getElementById("left")
const rightButton = document.getElementById("right")
const analyzeButton = document.getElementById("analyze")
const recalculateButton = document.getElementById("recalculate")

const statusText = document.getElementById("status")
const serialInput = document.getElementById("serial")
const denomInput = document.getElementById("denom")
const conditionInput = document.getElementById("cond")
const resultBox = document.getElementById("result")

const drop = document.getElementById("drop")

let currentImage = null
let rotation = 0


// -----------------------------------------
// Basic helpers
// -----------------------------------------

function escapeHTML(text) {
    text = String(text)

    text = text.replaceAll("&", "&amp;")
    text = text.replaceAll("<", "&lt;")
    text = text.replaceAll(">", "&gt;")
    text = text.replaceAll('"', "&quot;")
    text = text.replaceAll("'", "&#39;")

    return text
}


function money(value) {
    value = Number(value)

    if (value >= 100) {
        return "$" + Math.round(value).toLocaleString()
    }

    let text = value.toFixed(2)

    if (text.endsWith(".00")) {
        text = text.slice(0, -3)
    }

    return "$" + text
}


// -----------------------------------------
// IMAGE PREVIEW
// -----------------------------------------

function loadImage(file) {
    if (!file) {
        return
    }

    const url = URL.createObjectURL(file)
    const image = new Image()

    statusText.textContent = "Loading image..."

    image.onload = function() {
        currentImage = image
        rotation = 0

        previewArea.classList.remove("hidden")
        analyzeButton.disabled = false

        drawImage()

        statusText.textContent =
            "Rotate the bill if needed, then press Analyze photo."

        URL.revokeObjectURL(url)
    }

    image.onerror = function() {
        statusText.textContent =
            "Could not open that image."

        URL.revokeObjectURL(url)
    }

    image.src = url
}


function drawImage() {
    if (!currentImage) {
        return
    }

    let width = currentImage.naturalWidth
    let height = currentImage.naturalHeight

    let sideways = (
        rotation == 90 ||
        rotation == 270
    )

    if (sideways) {
        canvas.width = height
        canvas.height = width
    }
    else {
        canvas.width = width
        canvas.height = height
    }

    ctx.clearRect(
        0,
        0,
        canvas.width,
        canvas.height
    )

    ctx.save()

    ctx.translate(
        canvas.width / 2,
        canvas.height / 2
    )

    ctx.rotate(
        rotation * Math.PI / 180
    )

    ctx.drawImage(
        currentImage,
        -width / 2,
        -height / 2,
        width,
        height
    )

    ctx.restore()
}


// -----------------------------------------
// ROTATION
// -----------------------------------------

function rotateLeft() {
    rotation -= 90

    if (rotation < 0) {
        rotation = 270
    }

    drawImage()
}


function rotateRight() {
    rotation += 90

    if (rotation >= 360) {
        rotation = 0
    }

    drawImage()
}


// -----------------------------------------
// TURN CANVAS INTO IMAGE FILE
// -----------------------------------------

function getCanvasBlob() {
    return new Promise(function(resolve) {

        canvas.toBlob(
            function(blob) {
                resolve(blob)
            },
            "image/jpeg",
            0.92
        )

    })
}


// -----------------------------------------
// SEND IMAGE TO PYTHON
// -----------------------------------------

async function analyzePhoto() {
    if (!currentImage) {
        statusText.textContent =
            "Upload a photo first."

        return
    }

    analyzeButton.disabled = true

    statusText.textContent =
        "Finding and reading bill..."

    const blob = await getCanvasBlob()

    if (!blob) {
        statusText.textContent =
            "Could not prepare image."

        analyzeButton.disabled = false

        return
    }

    const form = new FormData()

    form.append(
        "image",
        blob,
        "bill.jpg"
    )

    form.append(
        "condition",
        conditionInput.value
    )

    try {

        const response = await fetch(
            "/analyze",
            {
                method: "POST",
                body: form
            }
        )

        const data = await response.json()

        if (data.serial) {
            serialInput.value = data.serial
        }

        if (data.denom) {
            denomInput.value = data.denom
        }

        renderResult(data)

        if (data.ok) {
            statusText.textContent =
                "Scan complete. Check that the serial and denomination are correct."
        }
        else {
            statusText.textContent =
                data.error || "Could not analyze bill."
        }

    }
    catch (error) {

        console.log(error)

        statusText.textContent =
            "Could not connect to Python server."

    }

    analyzeButton.disabled = false
}


// -----------------------------------------
// RECALCULATE AFTER USER CORRECTION
// -----------------------------------------

async function recalculate() {
    const serial = serialInput.value
    const denom = denomInput.value
    const condition = conditionInput.value

    if (!serial) {
        statusText.textContent =
            "Enter a serial number."

        return
    }

    statusText.textContent =
        "Recalculating..."

    const body = {
        serial: serial,
        denom: denom,
        condition: condition
    }

    try {

        const response = await fetch(
            "/evaluate",
            {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify(body)
            }
        )

        const data = await response.json()

        renderResult(data)

        if (data.ok) {
            statusText.textContent =
                "Updated."
        }
        else {
            statusText.textContent =
                data.error || "Could not recalculate."
        }

    }
    catch (error) {

        console.log(error)

        statusText.textContent =
            "Could not connect to Python server."

    }
}


// -----------------------------------------
// DISPLAY RESULTS
// -----------------------------------------

function renderResult(data) {

    if (!data.ok) {

        resultBox.innerHTML = `
            <div class="empty">
                <b>Could not fully read bill</b>
                ${escapeHTML(
                    data.error || "Unknown error."
                )}
            </div>
        `

        return
    }


    const value = data.value
    const features = data.features

    let hasPremium = false

    if (value.high > data.denom) {
        hasPremium = true
    }


    // ---------------------------
    // Features
    // ---------------------------

    let featureHTML = ""

    if (!features || features.length == 0) {

        featureHTML += `
            <li class="feature">
                <div>
                    <b>No special serial pattern</b>
                    <span>
                        This serial does not add a collectible premium.
                    </span>
                </div>

                <div class="mult">
                    ×1
                </div>
            </li>
        `

    }
    else {

        for (let i = 0; i < features.length; i++) {

            const feature = features[i]

            featureHTML += `
                <li class="feature">

                    <div>
                        <b>
                            ${escapeHTML(feature.label)}
                        </b>

                        <span>
                            ${escapeHTML(feature.desc)}
                        </span>
                    </div>

                    <div class="mult">
                        ×${feature.mult}
                    </div>

                </li>
            `
        }
    }


    // ---------------------------
    // Star result
    // ---------------------------

    let starHTML = ""

    if (data.star_detection) {

        const star = data.star_detection

        let starText = "Normal note"

        if (star.has_star) {
            starText = "Star note detected"
        }

        let confidence =
            Number(star.confidence).toFixed(3)

        starHTML = `
            <div class="cv-check">

                <b>
                    ${starText}
                </b>

                <br>

                Star confidence difference:
                ${confidence}

            </div>
        `
    }


    // ---------------------------
    // Serial
    // ---------------------------

    let serialHTML =
        escapeHTML(data.serial)

    serialHTML =
        serialHTML.replace(
            "*",
            '<span class="star">*</span>'
        )


    // ---------------------------
    // Price
    // ---------------------------

    let mainPrice =
        money(data.denom)

    let rangeText =
        "Estimated at face value"

    if (hasPremium) {

        mainPrice =
            money(value.est)

        rangeText =
            "Estimated range " +
            money(value.low) +
            " to " +
            money(value.high)
    }


    // ---------------------------
    // Entire result
    // ---------------------------

    resultBox.innerHTML = `

        <div class="note">

            <div class="note-top">

                <span>
                    $${data.denom} note
                </span>

            </div>

            <div class="serial-show">
                ${serialHTML}
            </div>

            <div class="district">
                Federal Reserve Bank:
                ${escapeHTML(data.district)}
            </div>

        </div>


        <div class="tierline">

            <div class="tier">
                ${escapeHTML(value.tier)}
            </div>

            <div class="meter">
                <span style="
                    width:
                    ${Math.max(value.score, 4)}%
                ">
                </span>
            </div>

        </div>


        <div class="worth">

            <div class="big">
                ${mainPrice}
            </div>

            <div class="range">
                ${rangeText}
            </div>

        </div>


        ${starHTML}


        <h3>
            Why it scored this way
        </h3>

        <ul class="features">
            ${featureHTML}
        </ul>
    `
}


// -----------------------------------------
// FILE UPLOAD
// -----------------------------------------

fileInput.addEventListener(
    "change",
    function() {

        const file =
            fileInput.files[0]

        if (file) {
            loadImage(file)
        }

    }
)


// -----------------------------------------
// BUTTONS
// -----------------------------------------

leftButton.onclick = function() {
    rotateLeft()
}


rightButton.onclick = function() {
    rotateRight()
}


analyzeButton.onclick = function() {
    analyzePhoto()
}


recalculateButton.onclick = function() {
    recalculate()
}


// -----------------------------------------
// DRAG AND DROP
// -----------------------------------------

drop.addEventListener(
    "dragover",
    function(event) {

        event.preventDefault()

        drop.classList.add("drag")
    }
)


drop.addEventListener(
    "dragleave",
    function() {

        drop.classList.remove("drag")
    }
)


drop.addEventListener(
    "drop",
    function(event) {

        event.preventDefault()

        drop.classList.remove("drag")

        const file =
            event.dataTransfer.files[0]

        if (file) {
            loadImage(file)
        }

    }
)

const sampleButtons =
    document.querySelectorAll(
        ".sample-image"
    )


function loadSample(url) {
    const image = new Image()

    statusText.textContent =
        "Loading sample..."

    image.onload = function() {
        currentImage = image
        rotation = 0

        previewArea.classList.remove(
            "hidden"
        )

        analyzeButton.disabled = false

        drawImage()

        statusText.textContent =
            "Sample loaded. Rotate if needed, then press Analyze photo."
    }

    image.onerror = function() {
        statusText.textContent =
            "Could not load sample."
    }

    image.src = url
}


for (
    let i = 0;
    i < sampleButtons.length;
    i++
) {
    const button =
        sampleButtons[i]

    button.onclick = function() {
        loadSample(
            button.dataset.image
        )
    }
}
import os
import json
import time
import sqlite3
import threading

from flask import Flask, jsonify, render_template_string
import paho.mqtt.client as mqtt


# ================= CONFIGURATION =================

BROKER = "79038d94d76e4fcd9425ff49bf850c63.s1.eu.hivemq.cloud"
PORT = 8883

USERNAME = os.getenv("MQTT_USERNAME")
PASSWORD = os.getenv("MQTT_PASSWORD")

GPS_TOPIC = "pothole/gps"
WARNING_TOPIC = "pothole/warnings"
EVENT_TOPIC = "pothole/events"

DATABASE = "hazards.db"

# ==================================================


app = Flask(__name__)

lock = threading.Lock()

system_data = {
    "latitude": None,
    "longitude": None,
    "heading": None,
    "distance": None,
    "hazard_id": None,
    "event_type": None,

    "detection_status": "NO HAZARD DETECTED",
    "detection_time": None,

    "warning": "WAITING",
    "mqtt_status": "Disconnected",
    "last_update": None,
    "gps_accuracy": None
}


# ================= DATABASE =================

def get_hazard_count():

    try:
        db = sqlite3.connect(DATABASE)

        result = db.execute(
            "SELECT COUNT(*) FROM hazards"
        ).fetchone()

        db.close()

        return result[0]

    except sqlite3.Error:
        return 0


# ================= MQTT =================

def on_connect(client, userdata, flags, rc):

    with lock:
        system_data["mqtt_status"] = (
            "Connected" if rc == 0 else "Disconnected"
        )

    if rc == 0:

        print("Dashboard connected to HiveMQ")

        client.subscribe([
            (GPS_TOPIC, 0),
            (WARNING_TOPIC, 0),
            (EVENT_TOPIC, 0)
        ])


def on_disconnect(client, userdata, rc):

    with lock:
        system_data["mqtt_status"] = "Disconnected"


def on_message(client, userdata, message):

    try:

        payload = message.payload.decode().strip()

        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            data = {"event_type": payload}

        if not isinstance(data, dict):
            data = {"event_type": str(data)}

        with lock:

            # -------- GPS DATA --------

            if message.topic == GPS_TOPIC:

                lat = data.get(
                    "latitude",
                    data.get("lat")
                )

                lon = data.get(
                    "longitude",
                    data.get("lon", data.get("lng"))
                )

                if lat is not None and lon is not None:

                    system_data["latitude"] = float(lat)
                    system_data["longitude"] = float(lon)

                    system_data["gps_accuracy"] = data.get(
                        "accuracy"
                    )

                    system_data["last_update"] = time.time()

            # -------- WARNING DATA --------

            elif message.topic == WARNING_TOPIC:

                system_data["warning"] = data.get(
                    "level",
                    "UNKNOWN"
                )

                system_data["distance"] = data.get(
                    "distance_m"
                )

                system_data["hazard_id"] = data.get(
                    "hazard_id"
                )

                system_data["event_type"] = data.get(
                    "event_type"
                )

                system_data["heading"] = data.get(
                    "bearing"
                )

                system_data["last_update"] = time.time()

            # -------- HAZARD DETECTION DATA --------

            elif message.topic == EVENT_TOPIC:

                event_type = str(
                    data.get("event_type")
                    or data.get("type")
                    or data.get("event")
                    or data.get("message")
                    or payload
                ).upper()

                if "POTHOLE" in event_type:

                    system_data["event_type"] = "POTHOLE"

                    system_data["detection_status"] = (
                        "POTHOLE DETECTED"
                    )

                    print("Pothole detection received")

                elif (
                    "SPEED_BUMP" in event_type
                    or "SPEED BUMP" in event_type
                ):

                    system_data["event_type"] = "SPEED_BUMP"

                    system_data["detection_status"] = (
                        "SPEED BUMP DETECTED"
                    )

                    print("Speed bump detection received")

                else:

                    system_data["event_type"] = event_type

                    system_data["detection_status"] = (
                        "HAZARD DETECTED"
                    )

                system_data["detection_time"] = time.time()
                system_data["last_update"] = time.time()

    except (ValueError, TypeError) as error:

        print("MQTT message error:", error)


# ================= WEB PAGE =================

HTML = """
<!DOCTYPE html>
<html lang="en">

<head>

<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">

<title>Pothole Detection Dashboard</title>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    padding: 25px;
    font-family: Arial, sans-serif;
    background: #0b1120;
    color: white;
}

.container {
    max-width: 1100px;
    margin: auto;
}

.header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 15px;
    margin-bottom: 30px;
}

.header h1 {
    font-size: 27px;
    margin: 0;
}

.subtitle {
    color: #94a3b8;
    margin-top: 8px;
}

.status {
    background: #172554;
    padding: 12px 18px;
    border-radius: 10px;
    font-size: 14px;
}

.grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 18px;
}

.card {
    background: #151f32;
    border: 1px solid #263449;
    border-radius: 14px;
    padding: 22px;
    min-width: 0;
}

.card h3 {
    color: #94a3b8;
    font-size: 14px;
    font-weight: normal;
    margin: 0 0 16px;
}

.value {
    font-size: 25px;
    font-weight: bold;
    overflow-wrap: anywhere;
}

.unit {
    color: #94a3b8;
    font-size: 13px;
    margin-top: 7px;
}

.warning-card {
    grid-column: span 3;
    text-align: center;
    padding: 30px;
}

.warning {
    font-size: 32px;
    font-weight: bold;
    margin-top: 12px;
}

.detection-card {
    grid-column: span 3;
    text-align: center;
    padding: 30px;
    border: 1px solid #334155;
}

.detection {
    font-size: 30px;
    font-weight: bold;
    margin-top: 12px;
}

.POTHOLE {
    color: #f87171;
}

.SPEED_BUMP {
    color: #facc15;
}

.NO_HAZARD {
    color: #4ade80;
}

.AHEAD {
    color: #38bdf8;
}

.CAUTION {
    color: #facc15;
}

.DANGER {
    color: #f87171;
}

.CLEAR {
    color: #4ade80;
}

.WAITING, .GPS_LOST, .UNKNOWN {
    color: #94a3b8;
}

.footer {
    text-align: center;
    color: #64748b;
    margin-top: 35px;
    font-size: 13px;
}

@media(max-width: 700px) {

    body {
        padding: 16px;
    }

    .grid {
        grid-template-columns: repeat(2, 1fr);
    }

    .warning-card,
    .detection-card {
        grid-column: span 2;
    }

    .value {
        font-size: 21px;
    }

    .detection,
    .warning {
        font-size: 24px;
    }

}

</style>

</head>

<body>

<div class="container">

    <div class="header">

        <div>
            <h1>🚗 Pothole Detection System</h1>

            <div class="subtitle">
                Live Vehicle Monitoring Dashboard
            </div>
        </div>

        <div class="status">
            MQTT: <strong id="mqtt">Connecting...</strong>
        </div>

    </div>


    <div class="grid">

        <!-- LIVE HAZARD DETECTION -->

        <div class="card detection-card">

            <h3>🔍 LIVE HAZARD DETECTION</h3>

            <div class="detection NO_HAZARD" id="detection">
                NO HAZARD DETECTED
            </div>

            <div class="unit" id="detectionTime">
                Waiting for detection...
            </div>

        </div>


        <!-- GPS -->

        <div class="card">
            <h3>📍 Latitude</h3>
            <div class="value" id="latitude">--</div>
        </div>

        <div class="card">
            <h3>📍 Longitude</h3>
            <div class="value" id="longitude">--</div>
        </div>

        <div class="card">
            <h3>🧭 Vehicle Heading</h3>
            <div class="value" id="heading">--</div>
            <div class="unit">Degrees</div>
        </div>


        <!-- NEAREST HAZARD -->

        <div class="card">
            <h3>⚠️ Nearest Hazard</h3>
            <div class="value" id="hazard">--</div>
            <div class="unit" id="eventType">
                No hazard selected
            </div>
        </div>

        <div class="card">
            <h3>📏 Distance</h3>
            <div class="value" id="distance">--</div>
            <div class="unit">Metres</div>
        </div>

        <div class="card">
            <h3>🕒 GPS Accuracy</h3>
            <div class="value" id="accuracy">--</div>
            <div class="unit">Metres</div>
        </div>


        <!-- ADVANCE WARNING -->

        <div class="card warning-card">

            <h3>⚠️ LIVE WARNING STATUS</h3>

            <div class="warning WAITING" id="warning">
                WAITING FOR GPS
            </div>

            <div class="unit" id="lastUpdate">
                Waiting for data...
            </div>

        </div>


        <!-- SYSTEM INFORMATION -->

        <div class="card">
            <h3>🕳️ Total Saved Hazards</h3>
            <div class="value" id="totalHazards">0</div>
        </div>

        <div class="card">
            <h3>📡 MQTT Connection</h3>
            <div class="value" id="mqttCard">--</div>
        </div>

        <div class="card">
            <h3>⚙️ System</h3>
            <div class="value" id="system">Running</div>
        </div>

    </div>


    <div class="footer">

        Smart Pothole Detection and Advance Warning System

        <br><br>

        Raspberry Pi + Arduino Nano 33 IoT + HiveMQ

    </div>

</div>


<script>

async function updateDashboard() {

    try {

        const response = await fetch("/api/status");

        const data = await response.json();


        // GPS INFORMATION

        document.getElementById("latitude").textContent =
            data.latitude ?? "--";

        document.getElementById("longitude").textContent =
            data.longitude ?? "--";

        document.getElementById("heading").textContent =
            data.heading !== null ? data.heading + "°" : "--";


        // HAZARD INFORMATION

        document.getElementById("hazard").textContent =
            data.hazard_id !== null ? "ID " + data.hazard_id : "--";

        document.getElementById("eventType").textContent =
            data.event_type ?? "No hazard selected";

        document.getElementById("distance").textContent =
            data.distance !== null ? data.distance : "--";

        document.getElementById("accuracy").textContent =
            data.gps_accuracy !== null ? data.gps_accuracy : "--";


        // LIVE DETECTION

        const detection = document.getElementById("detection");

        detection.textContent = data.detection_status;

        detection.className = "detection";

        if (data.detection_status === "POTHOLE DETECTED") {

            detection.classList.add("POTHOLE");

        }
        else if (
            data.detection_status === "SPEED BUMP DETECTED"
        ) {

            detection.classList.add("SPEED_BUMP");

        }
        else {

            detection.classList.add("NO_HAZARD");

        }


        if (data.detection_time) {

            const detectionDate = new Date(
                data.detection_time * 1000
            );

            document.getElementById("detectionTime").textContent =
                "Last detected: " +
                detectionDate.toLocaleTimeString();

        }
        else {

            document.getElementById("detectionTime").textContent =
                "Waiting for detection...";

        }


        // SYSTEM INFORMATION

        document.getElementById("totalHazards").textContent =
            data.total_hazards;

        document.getElementById("mqtt").textContent =
            data.mqtt_status;

        document.getElementById("mqttCard").textContent =
            data.mqtt_status;


        // WARNING STATUS

        const warning = document.getElementById("warning");

        warning.textContent = data.warning;

        warning.className = "warning " + data.warning;


        if (data.last_update) {

            const date = new Date(
                data.last_update * 1000
            );

            document.getElementById("lastUpdate").textContent =
                "Last update: " + date.toLocaleTimeString();

        }
        else {

            document.getElementById("lastUpdate").textContent =
                "Waiting for GPS data";

        }


        // GPS TIMEOUT

        if (
            data.last_update &&
            Date.now() / 1000 - data.last_update > 15
        ) {

            warning.textContent = "GPS SIGNAL LOST";

            warning.className = "warning GPS_LOST";

        }

    }
    catch (error) {

        console.error("Dashboard update failed:", error);

    }

}


updateDashboard();

setInterval(updateDashboard, 1000);

</script>

</body>
</html>
"""


# ================= FLASK ROUTES =================

@app.route("/")
def home():

    return render_template_string(HTML)


@app.route("/api/status")
def status():

    with lock:

        data = system_data.copy()

    data["total_hazards"] = get_hazard_count()

    return jsonify(data)


# ================= START APPLICATION =================

if __name__ == "__main__":

    if not USERNAME or not PASSWORD:

        raise RuntimeError(
            "MQTT credentials are missing."
        )

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION1
    )

    client.username_pw_set(USERNAME, PASSWORD)

    client.tls_set()

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    print("Connecting dashboard to HiveMQ...")

    client.connect(BROKER, PORT, 60)

    client.loop_start()

    print("Starting web dashboard...")

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False
    )

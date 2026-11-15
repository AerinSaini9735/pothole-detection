import json
import os
import time
import math
import sqlite3
import serial
import serial.tools.list_ports
import paho.mqtt.client as mqtt

# ================= CONFIGURATION =================

BROKER = "79038d94d76e4fcd9425ff49bf850c63.s1.eu.hivemq.cloud"
PORT = 8883

USERNAME = os.getenv("MQTT_USERNAME")
PASSWORD = os.getenv("MQTT_PASSWORD")

GPS_TOPIC = "pothole/gps"
WARNING_TOPIC = "pothole/warnings"

DATABASE = "hazards.db"
BAUD_RATE = 115200

WARNING_DISTANCE = 200
CAUTION_DISTANCE = 100
DANGER_DISTANCE = 50

GPS_TIMEOUT = 15
PASSED_RADIUS = 8

# A hazard must be within this angle of travel direction.
MAX_BEARING_ANGLE = 60

# GPS movement must exceed this before updating direction.
MIN_MOVEMENT = 3.0

# =================================================

latest_gps = None
previous_gps = None

last_gps_time = 0
last_heading = None

arduino = None
current_hazard_id = None
last_command = None

passed_hazards = set()


# ================= DISTANCE =================

def calculate_distance(lat1, lon1, lat2, lon2):

    R = 6371000

    lat1 = math.radians(lat1)
    lon1 = math.radians(lon1)
    lat2 = math.radians(lat2)
    lon2 = math.radians(lon2)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2)
        * math.sin(dlon / 2) ** 2
    )

    return 2 * R * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )


# ================= BEARING =================

def calculate_bearing(lat1, lon1, lat2, lon2):

    lat1 = math.radians(lat1)
    lat2 = math.radians(lat2)

    dlon = math.radians(lon2 - lon1)

    y = math.sin(dlon) * math.cos(lat2)

    x = (
        math.cos(lat1) * math.sin(lat2)
        - math.sin(lat1) * math.cos(lat2)
        * math.cos(dlon)
    )

    bearing = math.degrees(math.atan2(y, x))

    return (bearing + 360) % 360


def bearing_difference(b1, b2):

    return abs((b1 - b2 + 180) % 360 - 180)


# ================= DATABASE =================

def get_hazards():

    db = sqlite3.connect(DATABASE)

    hazards = db.execute("""
        SELECT id, event_type, latitude, longitude
        FROM hazards
        WHERE latitude IS NOT NULL
        AND longitude IS NOT NULL
    """).fetchall()

    db.close()

    return hazards


# ================= ARDUINO =================

def connect_arduino():

    global arduino

    while arduino is None:

        for port in serial.tools.list_ports.comports():

            try:

                connection = serial.Serial(
                    port.device,
                    BAUD_RATE,
                    timeout=1
                )

                time.sleep(2)

                arduino = connection

                print("\nArduino connected:", port.device)

                return

            except (serial.SerialException, OSError):
                continue

        print("Arduino not found. Retrying...")
        time.sleep(3)


def send_to_arduino(message):

    global arduino, last_command

    if message == last_command:
        return

    if arduino is None:
        connect_arduino()

    try:

        arduino.write((message + "\n").encode())

        last_command = message

        print("\nArduino:", message)

    except (serial.SerialException, OSError):

        arduino = None
        last_command = None

        print("Arduino disconnected.")


# ================= WARNING LEVEL =================

def get_warning_level(distance):

    if distance <= DANGER_DISTANCE:
        return "DANGER"

    elif distance <= CAUTION_DISTANCE:
        return "CAUTION"

    elif distance <= WARNING_DISTANCE:
        return "AHEAD"

    return "CLEAR"


# ================= GPS DIRECTION =================

def update_heading():

    global previous_gps, last_heading

    if latest_gps is None:
        return

    if previous_gps is None:

        previous_gps = latest_gps.copy()
        return

    movement = calculate_distance(
        previous_gps["latitude"],
        previous_gps["longitude"],
        latest_gps["latitude"],
        latest_gps["longitude"]
    )

    if movement >= MIN_MOVEMENT:

        last_heading = calculate_bearing(
            previous_gps["latitude"],
            previous_gps["longitude"],
            latest_gps["latitude"],
            latest_gps["longitude"]
        )

        previous_gps = latest_gps.copy()


# ================= HAZARD DETECTION =================

def process_hazards():

    global current_hazard_id

    if latest_gps is None:
        return

    if time.time() - last_gps_time > GPS_TIMEOUT:

        print("\nGPS signal lost.")

        send_to_arduino("CLEAR")

        current_hazard_id = None

        return

    if last_heading is None:

        print("\nWaiting for vehicle movement to determine direction...")

        send_to_arduino("CLEAR")

        return

    hazards = get_hazards()

    available_hazards = []

    current_lat = latest_gps["latitude"]
    current_lon = latest_gps["longitude"]

    for hazard in hazards:

        hazard_id, event_type, lat, lon = hazard

        if hazard_id in passed_hazards:
            continue

        distance = calculate_distance(
            current_lat,
            current_lon,
            lat,
            lon
        )

        if distance <= PASSED_RADIUS:

            passed_hazards.add(hazard_id)

            print("\nPassed hazard:", hazard_id)

            continue

        hazard_bearing = calculate_bearing(
            current_lat,
            current_lon,
            lat,
            lon
        )

        angle = bearing_difference(
            last_heading,
            hazard_bearing
        )

        # Ignore hazards outside the forward direction.
        if angle <= MAX_BEARING_ANGLE:

            available_hazards.append(
                (distance, hazard)
            )

    if not available_hazards:

        print("\nNo hazards ahead.")

        send_to_arduino("CLEAR")

        current_hazard_id = None

        client.publish(
            WARNING_TOPIC,
            json.dumps({"level": "CLEAR"})
        )

        return

    # Select nearest hazard ahead.
    available_hazards.sort(
        key=lambda item: item[0]
    )

    distance, hazard = available_hazards[0]

    hazard_id, event_type, lat, lon = hazard

    current_hazard_id = hazard_id

    level = get_warning_level(distance)

    print(
        f"\nHazard ID: {hazard_id} | "
        f"Type: {event_type} | "
        f"Distance: {distance:.1f} m | "
        f"Direction: AHEAD | "
        f"Warning: {level}"
    )

    if level == "CLEAR":

        send_to_arduino("CLEAR")

    else:

        distance_cm = round(distance * 100)

        command = (
            f"WARNING:{event_type},"
            f"{distance_cm},{level}"
        )

        send_to_arduino(command)

    client.publish(
        WARNING_TOPIC,
        json.dumps({
            "hazard_id": hazard_id,
            "event_type": event_type,
            "distance_m": round(distance, 2),
            "bearing": round(last_heading, 2),
            "level": level
        })
    )


# ================= MQTT =================

def on_connect(client, userdata, flags, rc):

    if rc == 0:

        print("\nConnected to HiveMQ!")

        client.subscribe(GPS_TOPIC)

        print("Waiting for GPS coordinates...")

    else:

        print("MQTT connection failed:", rc)


def on_message(client, userdata, message):

    global latest_gps, last_gps_time

    try:

        data = json.loads(
            message.payload.decode()
        )

        latitude = data.get(
            "latitude",
            data.get("lat")
        )

        longitude = data.get(
            "longitude",
            data.get("lon", data.get("lng"))
        )

        if latitude is None or longitude is None:
            return

        latitude = float(latitude)
        longitude = float(longitude)

        if not (-90 <= latitude <= 90):
            return

        if not (-180 <= longitude <= 180):
            return

        latest_gps = {
            "latitude": latitude,
            "longitude": longitude
        }

        last_gps_time = time.time()

        update_heading()

        process_hazards()

    except (ValueError, TypeError, json.JSONDecodeError) as error:

        print("\nGPS error:", error)


# ================= MAIN =================

if not USERNAME or not PASSWORD:

    raise RuntimeError(
        "MQTT credentials are missing."
    )

hazards = get_hazards()

print("\n===================================")
print(" DIRECTION-BASED POTHOLE DETECTION")
print("===================================")

print("Saved hazards:", len(hazards))

if not hazards:
    raise SystemExit("No saved hazards found.")

connect_arduino()

client = mqtt.Client(
    callback_api_version=mqtt.CallbackAPIVersion.VERSION1
)

client.username_pw_set(USERNAME, PASSWORD)

client.tls_set()

client.on_connect = on_connect
client.on_message = on_message

try:

    print("\nConnecting to HiveMQ...")

    client.connect(BROKER, PORT, 60)

    client.loop_forever()

except KeyboardInterrupt:

    print("\nStopping system...")

finally:

    try:

        if arduino is not None:

            arduino.write(b"CLEAR\n")
            arduino.close()

    except Exception:
        pass

    client.disconnect()

    print("System stopped.")

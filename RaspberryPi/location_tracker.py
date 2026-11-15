
import serial
import serial.tools.list_ports
import paho.mqtt.client as mqtt
import json
import sqlite3
import time
import os

# MQTT CONFIGURATION
BROKER = "79038d94d76e4fcd9425ff49bf850c63.s1.eu.hivemq.cloud"
PORT = 8883
GPS_TOPIC = "pothole/gps"
EVENT_TOPIC = "pothole/events"

USERNAME = os.getenv("MQTT_USERNAME")
PASSWORD = os.getenv("MQTT_PASSWORD")

BAUD_RATE = 115200
DATABASE = "hazards.db"

latest_gps = None
gps_time = 0
arduino = None

# DATABASE
db = sqlite3.connect(DATABASE, check_same_thread=False)

db.execute("""
CREATE TABLE IF NOT EXISTS hazards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT,
    latitude REAL,
    longitude REAL,
    timestamp TEXT
)
""")

db.commit()


# GPS CALLBACK
def on_message(client, userdata, message):
    global latest_gps, gps_time

    try:
        data = json.loads(message.payload.decode())

        lat = float(data["latitude"])
        lon = float(data["longitude"])

        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return

        latest_gps = {
            "latitude": lat,
            "longitude": lon
        }

        gps_time = time.time()

        print(f"GPS: {lat}, {lon}")

    except Exception as error:
        print("GPS error:", error)


# MQTT SETUP
client = mqtt.Client()
client.username_pw_set(USERNAME, PASSWORD)
client.tls_set()
client.on_message = on_message


# ARDUINO DETECTION
def find_arduino():
    for port in serial.tools.list_ports.comports():
        description = (port.description or "").lower()

        if "arduino" in description:
            return port.device

    for port in serial.tools.list_ports.comports():
        if port.device.startswith(("/dev/ttyACM", "/dev/ttyUSB")):
            return port.device

    return None


def connect_arduino():
    global arduino

    while arduino is None:
        port = find_arduino()

        if port:
            try:
                arduino = serial.Serial(port, BAUD_RATE, timeout=1)
                time.sleep(2)
                print("Arduino connected:", port)
            except Exception as error:
                print("Arduino connection error:", error)

        else:
            print("Waiting for Arduino...")
            time.sleep(2)


# EVENT PROCESSING
def process_event(line):
    if not line.startswith("EVENT:"):
        return

    event_type = line.split(",")[0].replace("EVENT:", "").strip()

    if event_type not in ("POTHOLE", "SPEED_BUMP"):
        return

    if latest_gps is None or time.time() - gps_time > 30:
        print("Event detected, but GPS unavailable. Location not saved.")
        return

    lat = latest_gps["latitude"]
    lon = latest_gps["longitude"]

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    db.execute("""
        INSERT INTO hazards
        (event_type, latitude, longitude, timestamp)
        VALUES (?, ?, ?, ?)
    """, (event_type, lat, lon, timestamp))

    db.commit()

    event = {
        "event": event_type,
        "latitude": lat,
        "longitude": lon,
        "timestamp": timestamp
    }

    client.publish(EVENT_TOPIC, json.dumps(event), qos=1)

    print("\nHAZARD LOCATION SAVED")
    print("Type:", event_type)
    print("Latitude:", lat)
    print("Longitude:", lon)
    print("Time:", timestamp)


# MAIN
def main():
    if not USERNAME or not PASSWORD:
        print("MQTT credentials missing!")
        return

    print("Connecting to HiveMQ...")

    client.connect(BROKER, PORT, 60)
    client.subscribe(GPS_TOPIC)
    client.loop_start()

    connect_arduino()

    print("Location tracker running!")

    try:
        while True:
            if arduino.in_waiting:
                line = arduino.readline().decode(
                    "utf-8", errors="ignore"
                ).strip()

                if line:
                    print("Arduino:", line)
                    process_event(line)

            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nLocation tracker stopped.")

    finally:
        if arduino and arduino.is_open:
            arduino.close()

        client.loop_stop()
        client.disconnect()
        db.close()


if __name__ == "__main__":
    main()

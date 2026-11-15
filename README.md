# Smart Pothole Detection and Advance Warning System

## 1. Project Overview

The Smart Pothole Detection and Advance Warning System is an IoT-based solution designed to detect road potholes and speed bumps and provide advance warnings to vehicle drivers.

The system uses an Arduino Nano 33 IoT for sensor-based detection, a Raspberry Pi for processing and communication, GPS for location tracking, and MQTT for real-time data exchange.

## 2. Technologies Used

### Hardware
- Arduino Nano 33 IoT
- Raspberry Pi 4
- IMU sensor (LSM6DS3)
- GPS-enabled smartphone
- LCD display (16x2)
- LEDs
- Buzzer

### Software
- Python
- Arduino IDE
- MQTT
- HiveMQ Cloud
- SQLite
- Flask
- HTML, CSS and JavaScript

## 3. System Features

- Real-time pothole detection.
- Speed bump detection.
- GPS-based hazard location recording.
- SQLite database for storing detected hazards.
- Live distance calculation between the vehicle and saved hazards.
- Multiple-hazard detection.
- Direction-based hazard filtering.
- Automatic warning selection.
- LCD, LED and buzzer notifications.
- Live web dashboard for system monitoring.

## 4. System Architecture

1. The Arduino Nano 33 IoT collects motion data using its onboard IMU.
2. The Arduino detects potholes and speed bumps.
3. Detection events are transmitted to the Raspberry Pi through Serial communication.
4. The iPhone provides GPS coordinates through a browser-based GPS publisher.
5. The Raspberry Pi receives GPS data through HiveMQ MQTT.
6. Detected hazard locations are stored in SQLite.
7. The Raspberry Pi calculates distances to saved hazards and identifies the nearest hazard ahead.
8. Warning commands are transmitted to the Arduino.
9. The Arduino activates the LCD, LEDs and buzzer.
10. A Flask dashboard displays live system information.

## 5. Project Structure

```text
pothole-detection/
│
├── live_distance_tracker.py
├── location_tracker.py
├── dashboard.py
│
└── README.md
```


## 6. Installation

Clone the repository:

```bash
git clone https://github.com/AerinSaini9735/pothole-detection.git
cd pothole-detection
```

Create a virtual environment:

```bash
python -m venv venv
source venv/bin/activate
```

Install dependencies:

```bash
pip install flask paho-mqtt pyserial
```

## 7. MQTT Configuration

Configure HiveMQ Cloud credentials using environment variables:

```bash
export MQTT_USERNAME="MY_USERNAME"
export MQTT_PASSWORD="MY_PASSWORD"
```

The system uses these MQTT topics:

| Topic | Purpose |
|---|---|
| pothole/gps | Receives GPS coordinates |
| pothole/events | Publishes detected hazards |
| pothole/warnings | Publishes warning information |

## 8. Running the System

Start the location recording program:

```bash
python location_tracker.py
```

Start the live distance tracking program in a separate terminal:

```bash
python live_distance_tracker.py
```

Start the web dashboard in another terminal:

```bash
python dashboard.py
```

Open the dashboard using:

```text
http://RASPBERRY_PI_IP:5000
```

Start the GPS publisher on the smartphone and allow location access.

## 9. Warning Levels

| Distance | Warning |
|---|---|
| More than 200 metres | No warning |
| 100–200 metres | AHEAD |
| 50–100 metres | CAUTION |
| 0–50 metres | DANGER |

## 10. Limitations

- GPS accuracy depends on environmental conditions and smartphone hardware.
- GPS-based distance measurements are not suitable for centimetre-level tracking.
- Direction estimation depends on consecutive GPS positions.
- GPS alone cannot reliably identify the correct road lane.
- The system is a prototype and requires further testing before real-world deployment.

## 11. Future Improvements

- Integration with dedicated GPS hardware.
- Improved vehicle direction and route detection.
- Cloud-based hazard sharing.
- Map-based hazard visualisation.
- Machine learning-based pothole classification.
- Improved GPS accuracy.

## 12. Conclusion

The project demonstrates how embedded systems, GPS technology, MQTT communication and IoT platforms can be integrated to develop a smart road hazard detection and warning solution.

The system aims to improve driver awareness by detecting road hazards, recording their locations and providing advance warnings.

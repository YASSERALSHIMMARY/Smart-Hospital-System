# Smart Hospital System

A final-year project for the BSc in Computer Science at TU Dublin.  
This system combines a smart hospital room with a mobile robot to monitor a patient’s breathing and room conditions in real time.  
It uses Raspberry Pi sensors, Kalman Filter, and Isolation Forest to filter noise, detect anomalies, and alert staff via a live dashboard.

---


## Video
Watch the system in action: [Full System](https://youtu.be/rUh_WAEogOs)
Watch the robot in move:     [Robot] (https://youtu.be/J6L9eNOmw_o)

## Overview
- **Smart Room (Raspberry Pi / CrowPi)**  
  Collects light and sound data → publishes via MQTT.
- **Server (Node.js + PostgreSQL)**  
  Stores sensor data and provides REST API endpoints.
- **Anomaly Detection (Python)**  
  Kalman filter + Isolation Forest → real-time detection of abnormal breathing sounds.
- **Mobile Robot (MasterPi)**  
  Moves near the patient when alerts are triggered → obstacle avoidance and sound sampling.
- **Web Dashboard (HTML/JS/CSS)**  
  Displays live charts, logs, and plays audible alarms.

---

## Main Features
- Real-time monitoring of light and sound
- Noise filtering and anomaly detection
- Robot navigation with MQTT commands
- PostgreSQL storage for sensor data
- Web dashboard with live charts + alerts

---

## Project Structure
```
Smart-Hospital-System/
│── server.js              # Node.js API server
│── sensors/sensors.js     # MQTT → PostgreSQL bridge
│── data_filtering.py      # ML anomaly detection
│── smart_room/sensors.py  # Raspberry Pi publisher
│── robot/move.py          # Robot navigation
│── public/                # Dashboard (HTML, CSS, JS)
│── requirements.txt       # Python dependencies
│── requirements-pi.txt    # Pi dependencies
│── .env.example           # Example env config
```

---

## Requirements
- **Node.js** and npm
- **Python 3.8+**
- **PostgreSQL** database
- **MQTT broker** (e.g. Mosquitto)
- Raspberry Pi with:
  - Microphone  
  - BH1750 light sensor  

---

## Installation
```bash
# Install Node packages
npm install

# Install Python dependencies
pip install -r requirements.txt
```

For Raspberry Pi:
```bash
pip install -r requirements-pi.txt
```

---

## Running the System
1. **Start PostgreSQL** and create tables.  
2. Copy `.env.example` → `.env` and fill in DB credentials + MQTT broker.  
3. **Run the server**  
   ```bash
   node server.js
   ```
4. **Run anomaly detection**  
   ```bash
   python data_filtering.py
   ```
5. **Run Raspberry Pi sensor publisher**  
   ```bash
   python smart_room/sensors.py
   ```
6. **Run robot controller**  
   ```bash
   python robot/move.py
   ```
7. Open the **dashboard** in browser:  
   ```
   http://localhost:3000
   ```

---

## API Endpoints
- `GET /api/light` → Latest light readings  
- `GET /api/sound` → Latest sound readings  
- `GET /api/sound-charts` → Historical sound data  

---

## Architecture (text)
```
Smart Room (Pi) → MQTT → Node.js Server → PostgreSQL → ML Detection → Alerts
      ↓                                                             ↑
   Sensors (light, sound)                                  Robot (movement, extra readings)
```

---

## Safety Note
This project is for **academic demonstration only**.  
No patient-identifiable health data (PHI) is used.  

---

## License
MIT License — free to use, modify, and distribute.

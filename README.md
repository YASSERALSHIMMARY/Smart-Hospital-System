# Smart Hospital System

A final-year project for the BSc in Computer Science at TU Dublin.  
This system joins a smart hospital room with a mobile robot to watch a patient’s breathing and room conditions in real time.

## Overview
- **Smart Room (CrowPi Raspberry Pi)**  
  Collects light and sound data and sends it to a server.
- **Anomaly Detection**  
  Kalman Filter and Isolation Forest methods clean the data and find abnormal sounds.
- **Mobile Robot (MasterPi)**  
  Moves near the patient to take clearer sound readings when an alert is sent.
- **Web Dashboard**  
  Shows live sensor data and alerts for hospital staff.

## Main Features
- Real-time light and sound monitoring
- Noise filtering to reduce false alarms
- Robot navigation and obstacle avoidance
- PostgreSQL database for storing readings
- Node.js web server and dashboard

## Requirements
- **Node.js** and npm
- **Python 3.8+**
- PostgreSQL database
- MQTT broker (e.g. Mosquitto)
- Raspberry Pi with microphone and BH1750 light sensor

## Installation
```bash
# Install Node packages
npm install

# Install Python packages
pip install -r requirements.txt

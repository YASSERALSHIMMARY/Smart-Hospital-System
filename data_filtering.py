"""
data_filtering.py
-------------------------------------------------------------------------------
Purpose:
- Connects to PostgreSQL and an MQTT broker.
- Train an Isolation Forest model on known-normal data (from CSV).
- Track each feature with a simple 1D Kalman Filter.
- Reads the latest sensor row, evaluates with both methods, and writes any
  detected anomalies to the database.
- If both sound checks agree (Isolation Forest + Kalman), publish MQTT alerts
    and a small robot move command.
    
Inputs
  - DB_* env vars for PostgreSQL connection (see .env).
  - trainingData.csv file with a 'label' column and feature columns.
  - Latest sensor rows in table smart_room_readings.

Outputs
  - Inserts into 'anomalies' table when an anomaly is detected.
  - MQTT messages to 'robot/move' and 'web/alert' when abnormal sound is
    confirmed by both methods.

Dependencies
  - psycopg2, numpy, pandas, scikit-learn, paho-mqtt, python-dotenv
  
References (methods adapted/informed by):
  - Kalman filtering explanations/implementations: L. Kleeman; M. Laaraiedh[21],[22].
  - Isolation Forest (algorithm & Python API): scikit-learn docs; tutorial guide[24],[25];.
   - Audio feature context (RMS, ZCR, dB): Ampedstudio; DataSpoof; SuperKogito[32],[33],[34].
"""

import os
import time
import psycopg2
import numpy as np
import pandas as pd
import json
from datetime import datetime
from sklearn.ensemble import IsolationForest
from dotenv import load_dotenv
import paho.mqtt.client as mqtt

# -----------------------------------------------------------------------------
# Load environment variables
# -----------------------------------------------------------------------------
# Loads DB credentials and other settings from .env
load_dotenv()

patient_id = 10                # Static demo id; replace with dynamic mapping in production
robot_moved = False            # Tracks whether the robot has already been commanded after a confirmed alert  
abnormal_detected = False      # Blocks duplicate anomaly processing until reset
# -----------------------------------------------------------------------------
# MQTT setup (used to notify robot and web dashboard)
# -----------------------------------------------------------------------------
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
# Broker address/port should be parameterized in real deployments
mqtt_client.connect("172.20.10.14", 1883, 60)

# -----------------------------------------------------------------------------
# Database connection (PostgreSQL)
# -----------------------------------------------------------------------------
try:
    conn = psycopg2.connect(
        dbname=os.getenv("DB_DATABASE"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT")
    )
    cursor = conn.cursor()
except Exception as e:
    # Fail fast if DB is not reachable
    print("Database connection error:", e)
    exit(1)

# -----------------------------------------------------------------------------
# Simple 1D Kalman Filter for scalar time series (e.g., rms, zcr, light_level)
# -----------------------------------------------------------------------------
class KalmanFilter:
    def __init__(self, F, H, Q, R, P, x0):
        # State transition (F), observation (H), process noise (Q),
        # measurement noise (R), estimate covariance (P), initial state (x0)
        self.F = F
        self.H = H
        self.Q = Q
        self.R = R
        self.P = P
        self.x = x0

    def predict(self):
        # Predicts next state and error covariance
        self.x = np.dot(self.F, self.x)
        self.P = np.dot(np.dot(self.F, self.P), self.F.T) + self.Q

    def update(self, z):
        # Update with new measurement z, then shrink uncertainty
        S = np.dot(self.H, np.dot(self.P, self.H.T)) + self.R
        K = np.dot(np.dot(self.P, self.H.T), np.linalg.inv(S))
        y = z - np.dot(self.H, self.x)          # residual (measurement residual)
        self.x = self.x + np.dot(K, y)          
        I = np.eye(self.F.shape[1])
        self.P = np.dot(I - np.dot(K, self.H), self.P)  # updated covariance

def initialize_kalman_filter(sensor_type, feature):
    """
    Returns a KalmanFilter instance with a reasonable initial state for the
    given sensor/feature. Initial values are based on observed "quiet" ranges.
    """
    if sensor_type == "sound":
        if feature == "rms":
            x0 = np.array([[0.008]])  # small energy for quiet room
        elif feature == "zcr":
            x0 = np.array([[0.010]])  # low zero-crossing rate for steady noise
        else:
            x0 = np.array([[0]])
    elif sensor_type == "light" and feature == "light_level":
        x0 = np.array([[12]])          # dim room baseline (lux)
    else:
        x0 = np.array([[0]])
    
    return KalmanFilter(
        F=np.array([[1]]),  # random-walk model
        H=np.array([[1]]),
        Q=np.array([[0.05]]),  # process noise
        R=np.array([[0.1]]),   # measurement noise
        P=np.array([[1]]),
        x0=x0
    )

# -----------------------------------------------------------------------------
# Configuration for each sensor type used by this script
# -----------------------------------------------------------------------------
sensor_config = {
    "light": {
        "columns": ["light_level"],
        "csv_file": "trainingData.csv",
        "training_source": "csv",
    },
    "sound": {
        "columns": ["rms", "zcr"],
        "csv_file": "trainingData.csv",
        "training_source": "csv",
    }
}

# -----------------------------------------------------------------------------
# Train Isolation Forest from CSV rows labeled "normal" (simple, reproducible)
# -----------------------------------------------------------------------------
def train_model(sensor_name, cfg):
    try:
        if cfg["training_source"] == "csv":
            df = pd.read_csv(cfg["csv_file"])

            # Use only normal rows to model typical behaviour
            df = df[df['label'] == 'normal']

            # Basic range filtering to remove outliers from training set
            if sensor_name == "sound":
                df = df[
                    (df["rms"] >= 0.001) & (df["rms"] <= 0.03) &
                    (df["zcr"] >= 0.009) & (df["zcr"] <= 0.04)
                ]
            elif sensor_name == "light":
                df = df[(df["light_level"] >= 0) & (df["light_level"] <= 25)]

            values = df[cfg["columns"]].values
        else:
            values = np.array([])

        if len(values) >= 3:
            model = IsolationForest(contamination=0.1)
            model.fit(values)
            return model
        else:
            # Not enough training samples to build a stable model
            return None

    except Exception as e:
        print(f"[{sensor_name}] Training error:", e)
        return None



# -----------------------------------------------------------------------------
# Core detection routine
#  - fetch latest row,
#  - skip if already recorded as anomaly,
#  - run Isolation Forest and Kalman residual checks,
#  - record anomaly and send MQTT if confirmed by both (for sound).
# -----------------------------------------------------------------------------
def run_detection(sensor_type, columns, table, model, kf_list):
    global robot_moved, abnormal_detected
    try:
        # Stop early if an abnormal sound event already locked the system
        if abnormal_detected:
            return

        # Get most recent reading for this sensor type
        cursor.execute(f"""
            SELECT id, patient_id, {', '.join(columns)}, timestamp FROM {table}
            WHERE {columns[0]} IS NOT NULL
            ORDER BY timestamp DESC LIMIT 1
        """)
        row = cursor.fetchone()
        if not row:
            return

        record_id, patient_id, *values, timestamp = row

        # Avoid double-inserting the same anomaly (same timestamp)
        cursor.execute("""
            SELECT COUNT(*) FROM anomalies 
            WHERE timestamp = %s AND sensor_type = %s
        """, (timestamp, sensor_type))
        if cursor.fetchone()[0] > 0:
            return

        # Convert all features to float for model input
        values = [float(v) for v in values]
        print(f"\n[INFO] {sensor_type} at {timestamp}:")
        for col, val in zip(columns, values):
            print(f"  {col} = {val}")

        isolation_forest_abnormal = False
        kalman_filter_abnormal = False

        # ------------------------ Isolation Forest ----------------------------
        # Predicts -1 for outlier (anomaly), 1 for inlier (normal)
        pred = model.predict([values])
        if pred[0] == -1:
            if sensor_type == "sound":
                # Require both features look out-of-range
                abnormal_count = 0
                abnormal_features = []
                for i, val in enumerate(values):
                    if (columns[i] == "rms" and (val < 0.01 or val > 0.03)) or \
                       (columns[i] == "zcr" and (val < 0.003 or val > 0.02)):
                        abnormal_count += 1
                        abnormal_features.append(f"{columns[i]}={val:.5f}")
                if abnormal_count == len(columns):
                    print(
                        "[ALERT] Isolation Forest abnormal "
                        f"{sensor_type}: both RMS and ZCR abnormal ("
                        + ", ".join(abnormal_features) + ")"
                    )
                    cursor.execute("""
                        INSERT INTO anomalies(patient_id, sensor_type, db, rms, zcr, detection_method, timestamp)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (patient_id, sensor_type, None,
                          values[0] if len(values) > 0 else None,
                          values[1] if len(values) > 1 else None,
                          "Isolation Forest", timestamp))
                    conn.commit()
                    isolation_forest_abnormal = True

            elif sensor_type == "light":
                print(f"[ALERT] Isolation Forest abnormal light: light_level={values[0]:.2f}")
                cursor.execute("""
                    INSERT INTO anomalies(patient_id, sensor_type, db, rms, zcr, detection_method, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (patient_id, "light", None, None, None, "Isolation Forest", timestamp))
                conn.commit()
                isolation_forest_abnormal = True

        # -------------------------- Kalman Filter -----------------------------
        # For each feature, compute residual and compare to a small threshold.
        abnormal_count = 0
        abnormal_features = []
        for i, val in enumerate(values):
            kf_list[i].predict()
            kf_list[i].update(np.array([[val]]))
            residual = abs(kf_list[i].x[0][0] - val)

            # Per-feature thresholds (tuned for testing)
            if columns[i] == "rms":
                threshold = 0.001
            elif columns[i] == "zcr":
                threshold = 0.001
            else:
                threshold = 1

            if residual > threshold:
                abnormal_count += 1
                abnormal_features.append(f"{columns[i]}={val:.5f} (residual={residual:.5f})")

        if abnormal_count == len(columns):
            print(
                f"[ALERT] Kalman Filter abnormal {sensor_type}: all features abnormal ("
                + ", ".join(abnormal_features) + ")"
            )
            cursor.execute("""
                INSERT INTO anomalies(patient_id, sensor_type, db, rms, zcr, detection_method, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (patient_id, sensor_type, None,
                  values[0] if len(values) > 0 else None,
                  values[1] if len(values) > 1 else None,
                  "Kalman Filter", timestamp))
            conn.commit()
            kalman_filter_abnormal = True

        # ---------------------- Act only when both agree ---------------------
        # Robot move + web alert are sent once per confirmed abnormal sound. 
        if sensor_type == "sound" and isolation_forest_abnormal and kalman_filter_abnormal:
            if not robot_moved:
                abnormal_detected = True
                robot_moved = True
                move_command = {"x": 0, "y": 1}  # simple forward move command
                mqtt_client.publish("robot/move", json.dumps(move_command))
                mqtt_client.publish("web/alert", json.dumps({"alert": "Patient abnormal sound detected!"}))
            else:
                print("[INFO] Alarm already sent. Waiting for manual reset.")

    except Exception as e:        
        print("Detection error:", e)
        conn.rollback()

# -----------------------------------------------------------------------------
# Kalman filter initialization per sensor/feature
# -----------------------------------------------------------------------------
kalman_filters = {
    sensor: [initialize_kalman_filter(sensor, feature) for feature in cfg["columns"]]
    for sensor, cfg in sensor_config.items()
}

# -----------------------------------------------------------------------------
# Train one Isolation Forest per sensor type
# -----------------------------------------------------------------------------
models = {}
for sensor, cfg in sensor_config.items():
    model = train_model(sensor, cfg)
    if model:
        models[sensor] = model
    else:
        print(f"[ERROR] Model training failed for {sensor}.")

print("Monitoring started...")

# -----------------------------------------------------------------------------
# Main loop (Run a single detection pass per sensor type).
# In a real service, this block would run on a schedule or be called by the server.
# -----------------------------------------------------------------------------
try:
    for sensor, cfg in sensor_config.items():
        if sensor in models:
            run_detection(sensor, cfg["columns"], cfg.get("table", "smart_room_readings"), models[sensor], kalman_filters[sensor])
except KeyboardInterrupt:
    print("Stopped by user.")
finally:
    # Always close DB resources cleanly
    cursor.close()
    conn.close()
    print("Database closed.")

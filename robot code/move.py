# move.py
# -----------------------------------------------------------------------------
# Purpose:
#   - Listen for simple move commands over MQTT (topic: "robot/move").
#   - Drive a MasterPi mecanum chassis in straight lines and 90° rotations.
#   - Avoid obstacles using the ultrasonic sensor before continuing.
#   - Perform a short arm action after reaching the target.
#
# How it works (high level):
#   1) Create robot objects (mecanum chassis, ultrasonic, servos).
#   2) Convert target (x, y) in meters to centimeters and move in Y then X.
#   3) Before each step, check distance; if too close, sidestep to avoid.
#   4) Correct drift with small step corrections, then run a short arm routine.
#   5) Expose an MQTT listener that decodes {"x": ?, "y": ?} and executes moves.
#
# References:
#   - MasterPi / HiwonderSDK usage and API patterns. [11] 
#   - Basic obstacle avoidance with ultrasonic on mobile robots (concept). [11]
#   - Safe-speed, stop-on-command principles in human–robot spaces (safety context). [28]  
# -----------------------------------------------------------------------------

import time
import sys
import signal
import json
import paho.mqtt.client as mqtt
import numpy as np

# Add robot SDK path
# Adds local SDK path so robot modules can be imported on-device.
sys.path.append('/home/pi/MasterPi/')

# Import robot and sensor modules
# MecanumChassis: omnidirectional drive; Ultrasonic: front distance check; Board: servo control.
import HiwonderSDK.mecanum as mecanum
from HiwonderSDK.Ultrasonic import Ultrasonic
import HiwonderSDK.Board as Board

# Create robot and sensor objects
# Single shared instances used across movement functions.
chassis = mecanum.MecanumChassis()
ultrasonic_sensor = Ultrasonic()

# Robot settings
# Width used to decide how far to sidestep; thresholds in cm; step size and base speed.
ROBOT_WIDTH_CM = 15
OBSTACLE_THRESHOLD = 19
STEP = 3
SIDE_STEP_CM = 5
REAL_SPEED = 25

is_running = True

# --- Signal Handler ---
# Ensures a clean stop when the process gets Ctrl+C or kill signals.
def signal_handler(sig, frame):
    global is_running
    print("Stop signal received. Stopping robot.")
    is_running = False
    chassis.stop()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# --- Obstacle Detection ---
# Returns True when a measured distance is below the configured threshold.
def is_obstacle_detected(threshold_cm=OBSTACLE_THRESHOLD):
    try:
        distance = ultrasonic_sensor.getDistance()
    except:
        # If sensor read fails, assume no reliable distance; use a large number.
        distance = 999
    print(f"Distance from obstacle: {distance} cm")
    return distance < threshold_cm

# --- Movement Functions ---
# Each function computes a duration from distance (cm / linear speed),
# commands velocity, waits, and then stops.

def move_forward(cm):
    print(f"Robot moves forward {cm} cm")
    duration = cm / REAL_SPEED
    chassis.set_velocity(50, 90, 0)  # speed, heading(deg), yaw_rate
    time.sleep(duration)
    chassis.stop()

def move_right(cm):
    print(f"Robot moves right {cm} cm")
    duration = cm / REAL_SPEED
    chassis.set_velocity(50, 0, 0)
    time.sleep(duration)
    chassis.stop()

def move_left(cm):
    print(f"Robot moves left {cm} cm")
    duration = cm / REAL_SPEED
    chassis.set_velocity(50, 180, 0)
    time.sleep(duration)
    chassis.stop()

def rotate_90(direction):
    # Rotates in place by approximated timing; no IMU feedback here.
    print(f"Robot rotates 90 degrees to the {direction}")
    target_angle = 90 if direction == "right" else -90 if direction == "left" else 0
    if target_angle == 0:
        print("Invalid rotation direction")
        return
    speed_deg_per_sec = 90
    correction = 0.57   # simple timing correction factor from bench tests
    duration = abs(target_angle) / speed_deg_per_sec
    duration *= correction
    angular_rate = speed_deg_per_sec if target_angle > 0 else -speed_deg_per_sec
    chassis.set_velocity(0, 0, angular_rate)
    time.sleep(duration)
    chassis.stop()
    print("Rotation complete")

# --- Obstacle Avoidance ---
# Sidesteps right in small chunks until the front is clear by a margin.
def avoid_obstacle(step_cm=SIDE_STEP_CM):
    print("Obstacle detected. Robot starts avoiding to the right.")
    moved_cm = 0
    while is_obstacle_detected(OBSTACLE_THRESHOLD + ROBOT_WIDTH_CM) and is_running:

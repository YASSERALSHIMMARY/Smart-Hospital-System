# Sensors.py
# -----------------------------------------------------------------------------
# Purpose:
#   - Read light and sound from the smart room.
#   - Convert raw signals to simple features (light in lux, sound: dB, RMS, ZCR).
#   - Publish readings to the MQTT broker so the server can store and analyze them.
#
# How it works:
#   1) Create a light sensor helper (BH1750 over I2C).
#   2) Record a short audio clip and extract features (RMS, dB, ZCR).
#   3) Build small JSON messages with a timestamp.
#   4) Publish to MQTT topics: "smartroom/light" and "smartroom/sound".
#   5) Repeat every few seconds.

# References:
# - RMS, ZCR, and dB usage for audio features: Ampedstudio; DataSpoof; SuperKogito[32],[33],[34].
# -----------------------------------------------------------------------------

import paho.mqtt.client as mqtt
import json
import time
from time import strftime
import numpy as np
import sounddevice as sd
import smbus

# --- Light Sensor Class ---
# The sensor returns 2 bytes that represent lux.
bus = smbus.SMBus(1)
class LightSensor:
    def __init__(self):
        self.DEVICE = 0x5c
        self.ONE_TIME_HIGH_RES_MODE_1 = 0x20
        
    def convertToNumber(self, data):
        # Convert two bytes to lux value (datasheet scale factor 1.2)
        return ((data[1] + (256 * data[0])) / 1.2)

    def readLight(self):
        # Read two bytes in one-time high-res mode and convert to lux
        data = bus.read_i2c_block_data(self.DEVICE, self.ONE_TIME_HIGH_RES_MODE_1)
        return self.convertToNumber(data)

# --- Sound Feature Extraction ---
# Records a short audio window and extracts:
#   - RMS: signal energy (helps estimate loudness)
#   - dB : log scale loudness (shifted +100 to keep positive numbers)
#   - ZCR: zero crossing rate (how often the waveform changes sign)
def extract_sound_features(duration=1, fs=44100):
    recording = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='float64')
    sd.wait()

    # Flatten the array to 1D for feature math
    signal = recording.flatten()

    # RMS and dB (small epsilon avoids log of zero)
    rms = np.sqrt(np.mean(signal**2))
    db = 20 * np.log10(rms + 1e-6) + 100

    # Zero Crossing Rate: count sign changes over the window
    zcr = ((signal[:-1] * signal[1:]) < 0).sum() / len(signal)

    # Round values to reduce message size and keep charts tidy
    return round(db, 2), round(rms, 5), round(zcr, 5)

# --- MQTT Setup ---
# Creates a client, connects to the broker, and prints a small status line.
MQTT_BROKER = "172.20.10.4"
MQTT_PORT = 1883
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(MQTT_BROKER, MQTT_PORT, 60)
print("Connected to MQTT server at", MQTT_BROKER)

# Prepare the light sensor helper
light_sensor = LightSensor()

# --- Main loop ---
# Repeats forever:
#   - Read light (lux)
#   - Record audio and extract db/rms/zcr
#   - Publish both messages with the same timestamp
#   - Sleep for a short period to control sending rate
try:
    while True:
        timestamp = strftime("%Y-%m-%d %H:%M:%S")

        # Read sensors
        light_value = light_sensor.readLight()
        db, rms, zcr = extract_sound_features()

        # Publish light reading to "smartroom/light"
        # Payload fields:
        #   sensor: "light"
        #   value : lux
        #   timestamp: current time string
        light_msg = {
            "sensor": "light",
            "value": light_value,
            "timestamp": timestamp
        }
        client.publish("smartroom/light", json.dumps(light_msg))
        print(f"Light sent: {light_value:.2f} lx")

        # Publish sound features to "smartroom/sound"
        # Payload fields:
        #   sensor: "sound"
        #   db, rms, zcr: sound features
        #   timestamp: same time as light for easier pairing on server
        sound_msg = {
            "sensor": "sound",
            "db": db,
            "rms": rms,
            "zcr": zcr,
            "timestamp": timestamp
        }
        client.publish("smartroom/sound", json.dumps(sound_msg))
        print(f"Sound sent: db={db:.2f}, rms={rms:.5f}, zcr={zcr:.5f}")

        # Wait before reading again to avoid flooding the network and database
        time.sleep(5)

except KeyboardInterrupt:
    # Graceful stop when interrupted from keyboard
    print("Stopped sending sensor data.")

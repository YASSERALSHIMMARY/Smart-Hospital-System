/**
 * sensors.js
 * ---------------------------------------------------------------------------
 * Purpose:
 * Connects to an MQTT broker, listens for sensor messages from the smart
 * hospital room, saves readings to a PostgreSQL database, and launches a
 * Python script for anomaly detection whenever a new timestamp is received.
 *
 * Usage:
 *   const sensors = require('./sensors');
 *   sensors(pgPool); // pgPool is a configured pg.Pool instance.
 *
 * Requirements:
 *   - Environment variable MQTT_BROKER (optional; defaults to mqtt://localhost)
 *   - PostgreSQL table: smart_room_readings
 *   - Python script: ../data_filtering.py
 
 
 * References:
 * - Kalman filtering background: L. Kleeman; M. Laaraiedh[21],[22].
 * - Isolation Forest (API/usage): scikit-learn docs; tutorial guide[24],[25].
 * - Audio features rationale (RMS, ZCR, dB): Ampedstudio; DataSpoof; SuperKogito[32],[33],[34]. 
 */

 */

const mqtt = require('mqtt');
const path = require('path');
const { spawn } = require('child_process');

// Fixed patient identifier used for inserting database records.
// Replace with dynamic assignment in a production system.
const patient_id = 10;

module.exports = (pool) => {
  // -------------------------------------------------------------------------
  // 1. Establish MQTT connection and subscribe to sensor topics
  // -------------------------------------------------------------------------
  const brokerUrl = process.env.MQTT_BROKER || 'mqtt://localhost';
  const mqttClient = mqtt.connect(brokerUrl);

  // Topics to monitor:
  //   smartroom/light : { value: Number, timestamp: String }
  //   smartroom/sound : { rms: Number, zcr: Number, timestamp: String }
  const topics = ['smartroom/light', 'smartroom/sound'];

  // Tracks the latest processed timestamp to prevent duplicate
  // executions of the anomaly detection script.
  let lastProcessedTimestamp = null;

  mqttClient.on('connect', () => {
    console.log('[MQTT] Connected to broker:', brokerUrl);
    mqttClient.subscribe(topics, () => {
      console.log('[MQTT] Subscribed to:', topics.join(', '));
    });
  });

  // -------------------------------------------------------------------------
  // 2. Process incoming MQTT messages
  // -------------------------------------------------------------------------
  mqttClient.on('message', async (topic, message) => {
    try {
      // Parse sensor payload
      const data = JSON.parse(message.toString());
      if (!data.timestamp) return; // Skip if timestamp missing

      const { timestamp } = data;

      // ---------------------------------------------------------------------
      // 3. Insert sensor readings into the PostgreSQL database
      // ---------------------------------------------------------------------
      if (topic === 'smartroom/light') {
        // Expected payload: { value, timestamp }
        const { value } = data;
        if (value !== undefined) {
          await pool.query(
            'INSERT INTO smart_room_readings(patient_id, light_level, timestamp) VALUES ($1, $2, $3)',
            [patient_id, value, timestamp]
          );
        }

      } else if (topic === 'smartroom/sound') {
        // Expected payload: { rms, zcr, timestamp }
        const { rms, zcr } = data;
        if (rms !== undefined && zcr !== undefined) {
          await pool.query(
            'INSERT INTO smart_room_readings(patient_id, rms, zcr, timestamp) VALUES ($1, $2, $3, $4)',
            [patient_id, rms, zcr, timestamp]
          );
        }
      }

      // ---------------------------------------------------------------------
      // 4. Launch anomaly detection script for a new timestamp only
      // ---------------------------------------------------------------------
      if (timestamp !== lastProcessedTimestamp) {
        lastProcessedTimestamp = timestamp;

        const scriptPath = path.join(__dirname, '../data_filtering.py');
        const py = spawn('python', ['-u', scriptPath]);

        // Display key output lines from Python script
        py.stdout.on('data', (chunk) => {
          const text = chunk.toString();
          if (text.includes('[INFO]') || text.includes('[ALERT]')) {
            console.log(text.trim());
          }
        });

        // Log any Python errors for debugging
        py.stderr.on('data', (chunk) => {
          console.error(`Python Error: ${chunk}`);
        });
      }

    } catch (err) {
      // Handle parsing or database errors without stopping the process
      console.error('MQTT message error:', err.message);
    }
  });
};

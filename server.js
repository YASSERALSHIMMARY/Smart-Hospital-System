// server.js
// -----------------------------------------------------------------------------
// Purpose:
//   - Provide HTTP APIs for the Smart Hospital System.
//   - Serve the front-end files from /public.
//   - Query PostgreSQL for latest light/sound readings and anomaly methods.
//   - Expose chart data for charts.html.
//
// How it works:
//   1) Load environment variables and create an Express app.
//   2) Create a PostgreSQL pool and verify the connection.
//   3) Load the MQTT → DB bridge in sensors/sensors.js (subscribes to topics,
//      stores readings, and triggers Python detection).
//   4) /api/light   → latest light value + which detection methods flagged it.
//   5) /api/sound   → latest sound features + which detection methods flagged it.
//   6) /api/sound-charts → last 20 sound rows formatted for Chart.js.
//
// -----------------------------------------------------------------------------

require('dotenv').config();
const express = require('express');
const bodyParser = require('body-parser');
const { Pool } = require('pg');
const path = require('path');
const app = express();
const port = 2021;

// Parse JSON bodies and serve static assets (HTML/CSS/JS) from /public
app.use(bodyParser.json());
app.use(express.static('public'));

// -----------------------------------------------------------------------------
// Connect to PostgreSQL using env configuration
// -----------------------------------------------------------------------------
const pool = new Pool({
    user: process.env.DB_USER,
    host: process.env.DB_HOST,
    database: process.env.DB_DATABASE,
    password: process.env.DB_PASSWORD,
    port: process.env.DB_PORT
});

pool.connect((err, client, release) => {
    if (err) console.error('Database error:', err.stack);
    else {
        console.log('Connected to database');
        release();
    }
});

// -----------------------------------------------------------------------------
// Load sensor handling module (subscribes to MQTT and stores rows in DB)
// -----------------------------------------------------------------------------
require('./sensors/sensors')(pool);

// -----------------------------------------------------------------------------
// Light Status API
// Returns:
//   { light_level, methods[] } where methods is a list of detection methods
//   (e.g., ["Kalman Filter", "Isolation Forest"]) that flagged the same timestamp.
// -----------------------------------------------------------------------------
app.get('/api/light', async (req, res) => {
    try {
        const result = await pool.query(`
            SELECT light_level, timestamp
            FROM smart_room_readings
            WHERE light_level IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 1
        `);

        const latest = result.rows[0];
        if (!latest) return res.json({ light_level: null, methods: [] });

        const anomaly = await pool.query(`
            SELECT DISTINCT detection_method
            FROM anomalies
            WHERE sensor_type = 'light' AND timestamp = $1
        `, [latest.timestamp]);

        res.json({
            light_level: latest.light_level,
            methods: anomaly.rows.map(r => r.detection_method)
        });
    } catch (err) {
        console.error('Error /api/light:', err);
        res.status(500).json({ error: 'DB error' });
    }
});

// -----------------------------------------------------------------------------
// Sound Status API
// Returns:
//   { rms, zcr, methods[] } for the latest sound reading. methods[] lists
//   detection methods that flagged that timestamp as abnormal.
// -----------------------------------------------------------------------------
app.get('/api/sound', async (req, res) => {
    try {
        const result = await pool.query(`
            SELECT rms, zcr, timestamp
            FROM smart_room_readings
            WHERE rms IS NOT NULL AND zcr IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 1
        `);

        const latest = result.rows[0];
        if (!latest) return res.json({ rms: null, zcr: null, methods: [] });

        const anomaly = await pool.query(`
            SELECT DISTINCT detection_method
            FROM anomalies
            WHERE sensor_type = 'sound' AND timestamp = $1
        `, [latest.timestamp]);

        res.json({
            rms: latest.rms,
            zcr: latest.zcr,
            methods: anomaly.rows.map(r => r.detection_method)
        });
    } catch (err) {
        console.error('Error /api/sound:', err);
        res.status(500).json({ error: 'DB error' });
    }
});

// -----------------------------------------------------------------------------
// Sound Charts API
// Returns last 20 rows formatted for Chart.js line charts.
// Each item has: { label: timeString, value: number }.
// Here, both "Kalman" and "Isolation" series reuse the same raw values;
// visual separation is handled by charts.js labeling only.
// -----------------------------------------------------------------------------
app.get('/api/sound-charts', async (req, res) => {
  try {
    const result = await pool.query(`
      SELECT timestamp, rms, zcr
      FROM smart_room_readings
      WHERE rms IS NOT NULL AND zcr IS NOT NULL
      ORDER BY timestamp DESC
      LIMIT 20
    `);

    const reversed = result.rows.reverse();

    const kalman_rms = [], kalman_zcr = [], iso_rms = [], iso_zcr = [];

    reversed.forEach((row) => {
      const label = new Date(row.timestamp).toLocaleTimeString();
      kalman_rms.push({ label, value: parseFloat(row.rms) });
      kalman_zcr.push({ label, value: parseFloat(row.zcr) });
      iso_rms.push({ label, value: parseFloat(row.rms) });
      iso_zcr.push({ label, value: parseFloat(row.zcr) });
    });

    res.json({ kalman_rms, kalman_zcr, iso_rms, iso_zcr });

  } catch (err) {
    console.error('Error /api/sound-charts:', err);
    res.status(500).json({ error: 'Chart data error' });
  }
});

// -----------------------------------------------------------------------------
// Start HTTP server
// -----------------------------------------------------------------------------
app.listen(port, () => {
    console.log(`Server running at http://localhost:${port}`);
});

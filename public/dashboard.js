// dashboard.js (dashboard logic for index.html)
// -----------------------------------------------------------------------------
// Purpose:
//   - Pull latest light and sound statuses from the server.
//   - Show a popup and play an alarm sound when both methods flag abnormal.
//   - Keep a simple alert log and handle real-time server-sent events.
//
// How it works:
//   1) updateDashboard() fetches /api/light and /api/sound.
//   2) A sensor is considered "abnormal" only if BOTH methods agree:
//        "Kalman Filter" AND "Isolation Forest" are present in methods[].
//   3) If any sensor is abnormal, show a popup and play alarm (once per event).
//   4) When values return to normal, hide popup, stop alarm, and log recovery.
//   5) Also listen to /events (Server-Sent Events) and append incoming notes.
//
// -----------------------------------------------------------------------------

let lastAlertActive = false;

async function updateDashboard() {
  try {
    // === Get Light Data ===
    // Fetch last light reading and methods that flagged it
    const lightRes = await fetch('/api/light');
    const lightData = await lightRes.json();
    const light = parseFloat(lightData.light_level);
    const lightBox = document.getElementById("room-light");
    const lightMethods = lightData.methods || [];

    // Light is abnormal only if both models reported it
    const lightAbnormal = lightMethods.includes("Kalman Filter") && lightMethods.includes("Isolation Forest");
    // Show a short text state (mask numeric value to keep UI simple)
    lightBox.textContent = isNaN(light) ? "--" : (lightAbnormal ? "Check Light " : "Normal");

    // === Get Sound Data ===
    // Fetch last sound status and methods that flagged it
    const soundRes = await fetch('/api/sound');
    const soundData = await soundRes.json();
    const soundMethods = soundData.methods || [];
    const statusBox = document.getElementById("sound-status");

    // Sound is abnormal only if both models reported it
    const soundAbnormal = soundMethods.includes("Kalman Filter") && soundMethods.includes("Isolation Forest");
    statusBox.textContent = soundAbnormal ? "Abnormal Sound " : "Everything is OK";

    // === Show Alert if any sensor is abnormal by both methods ===
    const showAlert = lightAbnormal || soundAbnormal;

    const popup = document.getElementById("popup-alert");
    const audio = document.getElementById("alert-sound");

    if (showAlert) {
      // Build a clear message for the popup and log
      const message = lightAbnormal && soundAbnormal
        ? " Both Light & Sound are abnormal!"
        : lightAbnormal
          ? " Abnormal Light Detected!"
          : " Abnormal Sound Detected!";

      // Show the visual popup
      showPopup(message);

      // Play the alarm only on the first abnormal frame (avoid repeated play calls)
      if (!lastAlertActive) {
        audio.play();
        addAlertLog(" " + message + " at " + new Date().toLocaleTimeString());
      }

      lastAlertActive = true;
    } else {
      // No current abnormal state → hide popup and reset audio if it was playing
      hidePopup();
      if (lastAlertActive) {
        audio.pause();
        audio.currentTime = 0;
        addAlertLog(" Back to normal at " + new Date().toLocaleTimeString());
      }

      lastAlertActive = false;
    }

  } catch (error) {
    // Keep UI stable and log the error
    console.error("Dashboard update error:", error);
    document.getElementById("room-light").textContent = "Error";
    document.getElementById("sound-status").textContent = "Error";
  }
}

// Show a simple popup banner with a message
function showPopup(message) {
  const popup = document.getElementById("popup-alert");
  popup.textContent = message;
  popup.classList.remove("hidden");
}

// Hide the popup banner
function hidePopup() {
  const popup = document.getElementById("popup-alert");
  popup.classList.add("hidden");
}

// Append a line to the alert history list
function addAlertLog(message) {
  const li = document.createElement("li");
  li.textContent = message;
  document.getElementById("alert-list").appendChild(li);
}

// Poll the server every 10 seconds
setInterval(updateDashboard, 10000);
updateDashboard();

// Listen for server-sent events (SSE) to add notes in real time
// The server should stream text lines via /events
const eventSource = new EventSource('/events');
eventSource.onmessage = function (event) {
  addAlertLog("" + event.data);
};

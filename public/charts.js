// charts.js
// -----------------------------------------------------------------------------
// Purpose:
//   - Draw live charts for sound features (RMS and ZCR) from Kalman Filter
//     and Isolation Forest methods.
//   - Update charts every few seconds using data from the server.
//
// How it works:
//   1) fetchData() gets JSON from /api/sound-charts.
//   2) createChart() builds a Chart.js line chart with data and thresholds.
//   3) initCharts() creates four charts (Kalman/Isolation × RMS/ZCR).
//   4) refreshCharts() pulls new data and updates the existing charts.
//
// This script uses the Chart.js library (https://www.chartjs.org/)
// to draw and update real-time sound feature charts.
//
// -----------------------------------------------------------------------------

// Get latest chart data from the server API
async function fetchData() {
  const res = await fetch('/api/sound-charts');
  return await res.json();
}

// Build a Chart.js line chart with:
//  - data series
//  - min/max threshold guide lines
//  - basic responsive options
function createChart(ctx, label, color, threshold, dataset) {
  return new Chart(ctx, {
    type: 'line',
    data: {
      // Labels usually hold time or sequence indices
      labels: dataset.map(d => d.label),
      datasets: [
        // Main feature series (RMS or ZCR)
        {
          label: label,
          data: dataset.map(d => d.value),
          borderColor: color,
          tension: 0.2,
          fill: false,
          pointRadius: 3
        },
        // Lower threshold guide (dashed)
        {
          label: 'Min Threshold',
          data: new Array(dataset.length).fill(
            label.includes("RMS") ? 0.004 : 0.003
          ),
          borderColor: 'red',
          borderDash: [5, 5],
          pointRadius: 0,
          fill: false
        },
        // Upper threshold guide (dashed)
        {
          label: 'Max Threshold',
          data: new Array(dataset.length).fill(
            label.includes("RMS") ? 0.055 : 0.02
          ),
          borderColor: 'green',
          borderDash: [5, 5],
          pointRadius: 0,
          fill: false
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        // Different ranges for RMS and ZCR for readability
        y: {
          min: 0,
          max: label.includes("RMS") ? 0.15 : 0.06,
          ticks: {
            stepSize: label.includes("RMS") ? 0.01 : 0.005
          }
        }
      },
      plugins: {
        legend: {
          labels: {
            font: { size: 12 }
          }
        }
      }
    }
  });
}

// Hold chart instances for later updates
let charts = {};

// Create all charts once after page load
async function initCharts() {
  const data = await fetchData();
  charts.kalmanRms = createChart(
    document.getElementById('kalmanRmsChart').getContext('2d'),
    'Kalman RMS',
    'orange',
    0.004,
    data.kalman_rms
  );
  charts.kalmanZcr = createChart(
    document.getElementById('kalmanZcrChart').getContext('2d'),
    'Kalman ZCR',
    'gold',
    0.003,
    data.kalman_zcr
  );
  charts.isoRms = createChart(
    document.getElementById('isoRmsChart').getContext('2d'),
    'Isolation RMS',
    'blue',
    0.004,
    data.iso_rms
  );
  charts.isoZcr = createChart(
    document.getElementById('isoZcrChart').getContext('2d'),
    'Isolation ZCR',
    'navy',
    0.003,
    data.iso_zcr
  );
}

// Pull fresh data and update the existing chart objects
async function refreshCharts() {
  const data = await fetchData();

  // Replace labels and values; keep thresholds aligned with length
  function update(chart, newData) {
    chart.data.labels = newData.map(d => d.label);
    chart.data.datasets[0].data = newData.map(d => d.value);
    chart.data.datasets[1].data = new Array(newData.length).fill(
      chart.config.data.datasets[0].label.includes("RMS") ? 0.004 : 0.003
    );
    chart.data.datasets[2].data = new Array(newData.length).fill(
      chart.config.data.datasets[0].label.includes("RMS") ? 0.055 : 0.02
    );
    chart.update();
  }

  update(charts.kalmanRms, data.kalman_rms);
  update(charts.kalmanZcr, data.kalman_zcr);
  update(charts.isoRms, data.iso_rms);
  update(charts.isoZcr, data.iso_zcr);
}

// Start the charts and refresh on an interval
initCharts();
setInterval(refreshCharts, 10000); // update every 10 seconds

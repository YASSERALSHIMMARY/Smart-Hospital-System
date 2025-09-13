# test_collect_data.py
# -----------------------------------------------------------------------------
# Purpose:
#   - Train an Isolation Forest model on normal sound features (rms, zcr).
#   - Track each feature with a simple 1D Kalman Filter while reading test rows.
#   - Classify each test row as normal/abnormal by both methods.
#   - Save predictions and show simple evaluation metrics (accuracy, precision, recall).
#
# How it works (high level):
#   1) Load training/test CSV files and select feature columns.
#   2) Filter training rows to keep only normal samples in a safe range.
#   3) Fit Isolation Forest on the filtered normal data.
#   4) Create two Kalman filters (one for rms, one for zcr) and update them per row.
#   5) Mark a row abnormal if Isolation Forest predicts -1, or Kalman residual exceeds a small threshold.
#   6) Write results to CSV and print basic metrics.
#
# References :
#   - Kalman filtering background: standard 1D formulation [21], [22].
#   - Isolation Forest algorithm and API usage: scikit-learn docs/tutorial [24],[25].
# -----------------------------------------------------------------------------

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

# === Kalman Filter Class ===
# Minimal scalar (1x1) Kalman filter for a single feature stream (rms or zcr).
class KalmanFilter:
    def __init__(self, F, H, Q, R, P, x0):
        # F: state transition, H: measurement model
        # Q: process noise, R: measurement noise
        # P: estimate covariance, x0: initial state
        self.F = F
        self.H = H
        self.Q = Q
        self.R = R
        self.P = P
        self.x = x0

    def predict(self):
        # Predict next state and uncertainty
        self.x = np.dot(self.F, self.x)
        self.P = np.dot(np.dot(self.F, self.P), self.F.T) + self.Q

    def update(self, z):
        # Incorporate new measurement z and reduce uncertainty
        S = np.dot(self.H, np.dot(self.P, self.H.T)) + self.R
        K = np.dot(np.dot(self.P, self.H.T), np.linalg.inv(S))
        y = z - np.dot(self.H, self.x)  # residual = measurement - estimate
        self.x = self.x + np.dot(K, y)
        I = np.eye(self.F.shape[1])
        self.P = np.dot(I - np.dot(K, self.H), self.P)

def initialize_kalman_filter():
    # 1D random-walk model with small process noise
    F = np.array([[1]])
    H = np.array([[1]])
    Q = np.array([[0.01]])
    R = np.array([[0.1]])
    P = np.array([[1]])
    x0 = np.array([[0]])
    return KalmanFilter(F, H, Q, R, P, x0)

# === Load and Prepare Data ===
# CSV files contain columns: label, rms, zcr, ...
train_file = 'F:/TUDublin Class/4th/2/project/2/final project/final day/Smart Hospital System/Smart Hospital System - 1/trainingData.csv'
test_file  = 'F:/TUDublin Class/4th/2/project/2/final project/final day/Smart Hospital System/Smart Hospital System - 1/Test_Dataset.csv'

features = ["rms", "zcr"]

train_df = pd.read_csv(train_file)
test_df  = pd.read_csv(test_file)

# === Adjusted Filtering to Avoid 0 Samples ===
# Keep only rows labeled "normal" and limit ranges to remove outliers in training set.
filtered_train = train_df[
    (train_df['label'] == 'normal') &
    (train_df["rms"].between(0.002, 0.05)) &
    (train_df["zcr"].between(0.002, 0.03))
]

X_train = filtered_train[features].values
print("Training samples used:", len(X_train))

# === Train Isolation Forest ===
# Contamination rate approximates expected fraction of anomalies in test data.
iso_model = IsolationForest(contamination=0.1)
iso_model.fit(X_train)

# === Initialize Kalman Filters (for rms and zcr) ===
# One independent scalar Kalman filter per feature.
kalman_filters = [initialize_kalman_filter() for _ in features]

# === Run Detection ===
# For each test row: get IF prediction and Kalman residual flags.
iso_preds = []
kalman_preds = []

for _, row in test_df.iterrows():
    values = row[features].values.astype(float)

    # Isolation Forest (-1 → abnormal, 1 → normal)
    iso_result = iso_model.predict([values])[0]
    iso_preds.append("abnormal" if iso_result == -1 else "normal")

    # Kalman Filter (residual > threshold → abnormal for that feature)
    kalman_result = []
    for i, val in enumerate(values):
        kf = kalman_filters[i]
        kf.predict()
        kf.update(np.array([[val]]))
        residual = abs(kf.x[0][0] - val)
        threshold = 0.004 if features[i] == "rms" else 0.003
        kalman_result.append(residual > threshold)

    # If any feature residual is large, mark row abnormal
    kalman_preds.append("abnormal" if any(kalman_result) else "normal")

# === Save Results to CSV ===
# Add predictions to the test dataframe and write out for review.
test_df["isolation_result"] = iso_preds
test_df["kalman_result"]   = kalman_preds
test_df.to_csv("anomaly_detection_results.csv", index=False)
print("Results saved to 'anomaly_detection_results.csv'.")

# === Evaluation Function ===
# Basic counts and metrics for quick comparison (not cross-validated).
def evaluate(true, pred):
    TP = sum((t == "abnormal" and p == "abnormal") for t, p in zip(true, pred))
    TN = sum((t == "normal"  and p == "normal")  for t, p in zip(true, pred))
    FP = sum((t == "normal"  and p == "abnormal") for t, p in zip(true, pred))
    FN = sum((t == "abnormal" and p == "normal")  for t, p in zip(true, pred))

    total = TP + TN + FP + FN
    accuracy  = (TP + TN) / total if total else 0
    precision = TP / (TP + FP) if (TP + FP) else 0
    recall    = TP / (TP + FN) if (TP + FN) else 0

    return {
        "TP": TP, "TN": TN, "FP": FP, "FN": FN,
        "Accuracy": round(accuracy, 2),
        "Precision": round(precision, 2),
        "Recall": round(recall, 2)
    }

# === Print Metrics ===
# Compares predictions to the provided label column in the test CSV.
true_labels   = test_df["label"].values
iso_metrics   = evaluate(true_labels, iso_preds)
kalman_metrics= evaluate(true_labels, kalman_preds)

print("\nIsolation Forest Metrics:")
print(iso_metrics)
print("\nKalman Filter Metrics:")
print(kalman_metrics)

#!/usr/bin/env python3
"""
PhantomSense™ — Confidence Engine
Computes a holistic navigation confidence score (0–100) from:
  - IMU sensor stability (variance analysis)
  - SLAM quality metrics
  - Accumulated drift penalty
  - GNSS availability factor

Publishes to /confidence/score at 10–50 Hz.
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
import numpy as np
from collections import deque
from typing import Optional

from sensor_msgs.msg import Imu
from phantom_msgs.msg import (
    StateEstimate,
    SlamPose,
    FusedPose,
    ConfidenceScore
)


# QoS for sensor streams
SENSOR_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    history=HistoryPolicy.KEEP_LAST,
    depth=10
)


class PhantomSenseNode(Node):
    """Confidence engine for PhantomNav™."""

    # ── Mode thresholds ────────────────────────────────────────
    LEVEL_NOMINAL  = 75.0
    LEVEL_DEGRADED = 40.0
    LEVEL_CRITICAL = 20.0
    # < CRITICAL → UNSAFE

    # ── Exponential moving average alpha ──────────────────────
    EMA_ALPHA = 0.15

    def __init__(self):
        super().__init__('phantom_sense_node')

        self.declare_parameter('publish_rate_hz',       20.0)
        self.declare_parameter('imu_window_size',        50)
        self.declare_parameter('drift_penalty_scale',     5.0)
        self.declare_parameter('max_drift_m',            30.0)
        self.declare_parameter('slam_quality_weight',     0.35)
        self.declare_parameter('imu_stability_weight',    0.35)
        self.declare_parameter('drift_weight',            0.20)
        self.declare_parameter('gnss_weight',             0.10)

        self._imu_win_size    = self.get_parameter('imu_window_size').value
        self._drift_scale     = self.get_parameter('drift_penalty_scale').value
        self._max_drift       = self.get_parameter('max_drift_m').value
        self._w_slam          = self.get_parameter('slam_quality_weight').value
        self._w_imu           = self.get_parameter('imu_stability_weight').value
        self._w_drift         = self.get_parameter('drift_weight').value
        self._w_gnss          = self.get_parameter('gnss_weight').value

        # ── Sliding windows ────────────────────────────────────
        self._accel_buf: deque[np.ndarray] = deque(maxlen=self._imu_win_size)
        self._gyro_buf:  deque[np.ndarray] = deque(maxlen=self._imu_win_size)

        # ── Latest inputs ──────────────────────────────────────
        self._latest_state: Optional[StateEstimate] = None
        self._latest_slam:  Optional[SlamPose]       = None
        self._latest_fused: Optional[FusedPose]      = None

        # ── Smoothed sub-scores (EMA) ──────────────────────────
        self._ema_stability  = 1.0
        self._ema_slam_q     = 1.0
        self._ema_drift_pen  = 1.0
        self._ema_score      = 100.0

        # ── Publisher ──────────────────────────────────────────
        self._pub = self.create_publisher(ConfidenceScore, '/confidence/score', 10)

        # ── Subscribers ───────────────────────────────────────
        self.create_subscription(Imu, '/imu/data', self._on_imu, SENSOR_QOS)
        self.create_subscription(
            StateEstimate, '/state/estimate', self._on_state, SENSOR_QOS)
        self.create_subscription(
            SlamPose, '/slam/pose', self._on_slam, SENSOR_QOS)
        self.create_subscription(
            FusedPose, '/fusion/pose', self._on_fused, SENSOR_QOS)

        # ── Timer ─────────────────────────────────────────────
        hz = self.get_parameter('publish_rate_hz').value
        self.create_timer(1.0 / hz, self._compute_and_publish)

        self.get_logger().info(
            f'PhantomSense™ initialized at {hz:.0f} Hz. '
            f'Weights: IMU={self._w_imu} SLAM={self._w_slam} '
            f'Drift={self._w_drift} GNSS={self._w_gnss}')

    # ── Callbacks ─────────────────────────────────────────────

    def _on_imu(self, msg: Imu):
        a = np.array([msg.linear_acceleration.x,
                      msg.linear_acceleration.y,
                      msg.linear_acceleration.z])
        g = np.array([msg.angular_velocity.x,
                      msg.angular_velocity.y,
                      msg.angular_velocity.z])
        self._accel_buf.append(a)
        self._gyro_buf.append(g)

    def _on_state(self, msg: StateEstimate):
        self._latest_state = msg

    def _on_slam(self, msg: SlamPose):
        self._latest_slam = msg

    def _on_fused(self, msg: FusedPose):
        self._latest_fused = msg

    # ── Sub-score computations ─────────────────────────────────

    def _imu_stability_score(self) -> tuple[float, float, float]:
        """
        Returns (stability_score 0-1, accel_variance, gyro_variance).
        Low variance → high stability.
        """
        if len(self._accel_buf) < 5:
            return 1.0, 0.0, 0.0

        accels = np.array(self._accel_buf)
        gyros  = np.array(self._gyro_buf)

        # Norm of variance across each axis
        accel_var = float(np.mean(np.var(accels, axis=0)))
        gyro_var  = float(np.mean(np.var(gyros,  axis=0)))

        # Score: exponential decay — variance > 1.0 m/s^2 → low score
        stability = np.exp(-accel_var * 2.0) * np.exp(-gyro_var * 10.0)
        stability = float(np.clip(stability, 0.0, 1.0))
        return stability, accel_var, gyro_var

    def _slam_quality_score(self) -> float:
        """SLAM quality directly from PhantomVision™ [0, 1]."""
        if self._latest_slam is None:
            return 0.0
        if not self._latest_slam.slam_initialized:
            return 0.0
        return float(np.clip(self._latest_slam.quality, 0.0, 1.0))

    def _drift_penalty_score(self) -> float:
        """
        Score based on accumulated drift from fusion.
        Large drift → low score.
        """
        if self._latest_fused is None:
            return 1.0
        drift_m = self._latest_fused.drift_estimate_m
        # Normalize: 0 drift → 1.0, max_drift → 0.0
        penalty_ratio = float(drift_m) / self._max_drift
        score = max(0.0, 1.0 - penalty_ratio)
        return float(score)

    def _gnss_factor(self) -> float:
        """GNSS availability and quality factor [0, 1]."""
        if self._latest_state is None:
            return 0.0
        if not self._latest_state.gnss_valid:
            return 0.0
        # Scale by accuracy: 0m → 1.0, 10m → ~0.2
        acc = max(self._latest_state.gnss_accuracy_m, 0.1)
        gnss_factor = float(np.exp(-acc / 5.0))
        return float(np.clip(gnss_factor, 0.0, 1.0))

    # ── Main computation ───────────────────────────────────────

    def _compute_and_publish(self):
        stability, accel_var, gyro_var = self._imu_stability_score()
        slam_q   = self._slam_quality_score()
        drift_s  = self._drift_penalty_score()
        gnss_f   = self._gnss_factor()

        # ── EMA smoothing ──────────────────────────────────────
        α = self.EMA_ALPHA
        self._ema_stability = α * stability + (1 - α) * self._ema_stability
        self._ema_slam_q    = α * slam_q    + (1 - α) * self._ema_slam_q
        self._ema_drift_pen = α * drift_s   + (1 - α) * self._ema_drift_pen

        # ── Weighted composite score ───────────────────────────
        raw_score = (
            self._w_imu   * self._ema_stability +
            self._w_slam  * self._ema_slam_q    +
            self._w_drift * self._ema_drift_pen +
            self._w_gnss  * gnss_f
        ) * 100.0

        self._ema_score = α * raw_score + (1 - α) * self._ema_score
        final_score = float(np.clip(self._ema_score, 0.0, 100.0))

        # ── Classify level ─────────────────────────────────────
        if final_score >= self.LEVEL_NOMINAL:
            level = 'NOMINAL'
        elif final_score >= self.LEVEL_DEGRADED:
            level = 'DEGRADED'
        elif final_score >= self.LEVEL_CRITICAL:
            level = 'CRITICAL'
        else:
            level = 'UNSAFE'

        # ── Publish ───────────────────────────────────────────
        msg = ConfidenceScore()
        msg.header.stamp  = self.get_clock().now().to_msg()
        msg.score         = final_score
        msg.sensor_stability    = float(self._ema_stability)
        msg.slam_quality        = float(self._ema_slam_q)
        msg.drift_penalty       = float(self._ema_drift_pen)
        msg.gnss_factor         = float(gnss_f)
        msg.level               = level
        msg.imu_variance        = float(accel_var)
        msg.accel_norm_variance = float(accel_var)
        msg.slam_feature_count_norm = float(
            self._latest_slam.tracked_features / 1500.0
            if self._latest_slam else 0.0)

        self._pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = PhantomSenseNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

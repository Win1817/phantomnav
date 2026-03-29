#!/usr/bin/env python3
"""
PhantomDecision™ — Autonomous Decision Engine
Rule-based state machine for navigation mode selection and safety triggers.

State Machine:
  GNSS_PRIMARY    ──[GNSS lost]──▶ INS_SLAM_FUSION
  INS_SLAM_FUSION ──[conf<40]───▶ INS_ONLY
  INS_ONLY        ──[conf<20]───▶ SAFE_MODE
  SAFE_MODE       ──[conf<10]───▶ EMERGENCY_HOLD
  Any             ──[GNSS back]──▶ GNSS_PRIMARY (gradual)

Outputs: /nav/mode, /alerts
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
import time
from enum import IntEnum
from typing import Optional

from std_msgs.msg import Bool
from phantom_msgs.msg import (
    ConfidenceScore,
    SlamPose,
    StateEstimate,
    NavMode,
    PhantomAlert
)

SENSOR_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    history=HistoryPolicy.KEEP_LAST,
    depth=10
)


class Mode(IntEnum):
    GNSS_PRIMARY    = 0
    INS_SLAM_FUSION = 1
    INS_ONLY        = 2
    SAFE_MODE       = 3
    EMERGENCY_HOLD  = 4


MODE_NAMES = {
    Mode.GNSS_PRIMARY:    'GNSS_PRIMARY',
    Mode.INS_SLAM_FUSION: 'INS_SLAM_FUSION',
    Mode.INS_ONLY:        'INS_ONLY',
    Mode.SAFE_MODE:       'SAFE_MODE',
    Mode.EMERGENCY_HOLD:  'EMERGENCY_HOLD',
}


class PhantomDecisionNode(Node):
    """Deterministic navigation decision engine."""

    # ── Hysteresis thresholds ──────────────────────────────────
    TH_GNSS_LOST_ENTER  = 5.0    # s without GNSS → switch away
    TH_GNSS_RECOVER_MIN = 15.0   # s of good GNSS before returning
    TH_INS_SLAM_ENTER   = 40.0   # confidence below → exit INS_SLAM
    TH_INS_ONLY_ENTER   = 25.0   # confidence below → exit INS_ONLY
    TH_SAFE_MODE_ENTER  = 12.0   # confidence below → SAFE_MODE
    TH_EMERGENCY_ENTER  = 6.0    # confidence below → EMERGENCY_HOLD
    TH_RECOVER_CONF     = 55.0   # confidence above → try to upgrade

    def __init__(self):
        super().__init__('phantom_decision_node')

        self.declare_parameter('publish_rate_hz',          10.0)
        self.declare_parameter('gnss_timeout_s',            5.0)
        self.declare_parameter('mode_change_debounce_s',    2.0)

        self._gnss_timeout = self.get_parameter('gnss_timeout_s').value
        self._debounce     = self.get_parameter('mode_change_debounce_s').value

        # ── State ──────────────────────────────────────────────
        self._mode: Mode = Mode.GNSS_PRIMARY
        self._pending_mode: Optional[Mode] = None
        self._pending_since: float = 0.0

        # Latest sensor snapshots
        self._confidence: Optional[ConfidenceScore] = None
        self._ins: Optional[StateEstimate] = None
        self._slam: Optional[SlamPose] = None

        # GNSS timing
        self._last_gnss_time: float = time.monotonic()
        self._gnss_recover_since: float = 0.0
        self._gnss_lost: bool = False

        # Alert deduplication
        self._last_alert_code: str = ''
        self._last_alert_time: float = 0.0

        # ── Publishers ─────────────────────────────────────────
        self._mode_pub  = self.create_publisher(NavMode,       '/nav/mode',  10)
        self._alert_pub = self.create_publisher(PhantomAlert,  '/alerts',    10)

        # ── Subscribers ───────────────────────────────────────
        self.create_subscription(
            ConfidenceScore, '/confidence/score', self._on_confidence, 10)
        self.create_subscription(
            StateEstimate, '/state/estimate', self._on_state, SENSOR_QOS)
        self.create_subscription(
            SlamPose, '/slam/pose', self._on_slam, SENSOR_QOS)

        # ── Decision loop timer ────────────────────────────────
        hz = self.get_parameter('publish_rate_hz').value
        self.create_timer(1.0 / hz, self._decision_loop)

        self.get_logger().info(
            'PhantomDecision™ initialized. Initial mode: GNSS_PRIMARY')

    # ── Callbacks ─────────────────────────────────────────────

    def _on_confidence(self, msg: ConfidenceScore):
        self._confidence = msg

    def _on_state(self, msg: StateEstimate):
        self._ins = msg
        if msg.gnss_valid:
            self._last_gnss_time = time.monotonic()

    def _on_slam(self, msg: SlamPose):
        self._slam = msg

    # ── Decision logic ─────────────────────────────────────────

    def _decision_loop(self):
        now = time.monotonic()

        confidence = self._confidence.score if self._confidence else 50.0
        gnss_valid  = self._ins.gnss_valid  if self._ins else False

        # ── GNSS status determination ──────────────────────────
        gnss_age = now - self._last_gnss_time
        if gnss_age > self._gnss_timeout:
            if not self._gnss_lost:
                self._gnss_lost = True
                self._raise_alert(
                    severity=2,
                    source='PhantomDecision',
                    code='GNSS_LOST',
                    message=f'GNSS signal lost for {gnss_age:.1f}s. '
                            f'Switching to INS/SLAM fusion.',
                    confidence=confidence
                )
            self._gnss_recover_since = 0.0
        else:
            if self._gnss_lost:
                # Track recovery
                if self._gnss_recover_since == 0.0:
                    self._gnss_recover_since = now
                elif now - self._gnss_recover_since >= self.TH_GNSS_RECOVER_MIN:
                    self._gnss_lost = False
                    self._gnss_recover_since = 0.0
                    self._raise_alert(
                        severity=0,
                        source='PhantomDecision',
                        code='GNSS_RECOVERED',
                        message='GNSS signal restored. Returning to GNSS_PRIMARY.',
                        confidence=confidence
                    )

        # ── Target mode determination ──────────────────────────
        target = self._compute_target_mode(confidence, self._gnss_lost)

        # ── Debounced mode transition ──────────────────────────
        if target != self._mode:
            if self._pending_mode != target:
                self._pending_mode  = target
                self._pending_since = now

            if now - self._pending_since >= self._debounce:
                self._transition_to(target, confidence)
                self._pending_mode = None
        else:
            self._pending_mode = None

        self._publish_mode(confidence)

    def _compute_target_mode(self, confidence: float, gnss_lost: bool) -> Mode:
        """Pure deterministic rule-based target mode selection."""
        # Emergency override — always takes priority
        if confidence < self.TH_EMERGENCY_ENTER:
            return Mode.EMERGENCY_HOLD

        # Safe mode
        if confidence < self.TH_SAFE_MODE_ENTER:
            return Mode.SAFE_MODE

        # GNSS lost → must degrade
        if gnss_lost:
            slam_ok = (self._slam is not None and
                       self._slam.slam_initialized and
                       self._slam.quality > 0.3)
            if slam_ok and confidence >= self.TH_INS_SLAM_ENTER:
                return Mode.INS_SLAM_FUSION
            elif confidence >= self.TH_INS_ONLY_ENTER:
                return Mode.INS_ONLY
            else:
                return Mode.SAFE_MODE

        # GNSS available → prefer primary
        if confidence >= self.TH_RECOVER_CONF and not gnss_lost:
            return Mode.GNSS_PRIMARY

        # Intermediate: GNSS available but low confidence — fuse
        return Mode.INS_SLAM_FUSION

    def _transition_to(self, new_mode: Mode, confidence: float):
        old_name = MODE_NAMES[self._mode]
        new_name = MODE_NAMES[new_mode]

        severity_map = {
            Mode.GNSS_PRIMARY:    0,
            Mode.INS_SLAM_FUSION: 1,
            Mode.INS_ONLY:        1,
            Mode.SAFE_MODE:       2,
            Mode.EMERGENCY_HOLD:  3,
        }

        self.get_logger().info(
            f'[PhantomDecision™] Mode: {old_name} → {new_name} '
            f'(conf={confidence:.1f})')

        self._raise_alert(
            severity=severity_map[new_mode],
            source='PhantomDecision',
            code=f'MODE_{new_name}',
            message=f'Navigation mode changed: {old_name} → {new_name}',
            confidence=confidence
        )
        self._mode = new_mode

    def _publish_mode(self, confidence: float):
        msg = NavMode()
        msg.header.stamp     = self.get_clock().now().to_msg()
        msg.mode             = int(self._mode)
        msg.mode_name        = MODE_NAMES[self._mode]
        msg.confidence_at_switch = confidence
        msg.gnss_available   = not self._gnss_lost
        msg.slam_available   = (self._slam is not None and
                                self._slam.slam_initialized)
        msg.reason           = ''
        self._mode_pub.publish(msg)

    def _raise_alert(self, severity: int, source: str,
                     code: str, message: str, confidence: float):
        now = time.monotonic()
        # Suppress duplicate alerts within 10 seconds
        if code == self._last_alert_code and now - self._last_alert_time < 10.0:
            return

        msg = PhantomAlert()
        msg.header.stamp        = self.get_clock().now().to_msg()
        msg.severity            = severity
        msg.source              = source
        msg.code                = code
        msg.message             = message
        msg.confidence_at_alert = confidence
        msg.nav_mode_at_alert   = int(self._mode)
        self._alert_pub.publish(msg)

        self._last_alert_code = code
        self._last_alert_time = now

        level = ['INFO', 'WARNING', 'ERROR', 'CRITICAL'][min(severity, 3)]
        log_fn = [
            self.get_logger().info,
            self.get_logger().warn,
            self.get_logger().error,
            self.get_logger().fatal,
        ][min(severity, 3)]
        log_fn(f'[{level}][{source}] {code}: {message}')


def main(args=None):
    rclpy.init(args=args)
    node = PhantomDecisionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

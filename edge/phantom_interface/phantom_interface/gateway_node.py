#!/usr/bin/env python3
"""
PhantomInterface™ — Edge ↔ Cloud Gateway
Bridges ROS 2 topics to the MQTT broker (cloud).

MQTT Topics Published (UAV → Cloud):
  phantom/{drone_id}/telemetry    — fused pose + INS state
  phantom/{drone_id}/confidence   — confidence score
  phantom/{drone_id}/status       — nav mode + alerts

MQTT Topics Subscribed (Cloud → UAV):
  phantom/{drone_id}/command      — flight commands
  phantom/{drone_id}/mission      — mission updates

Rules:
  - Fully async, non-blocking
  - UAV does NOT depend on cloud connectivity
  - Lossy OK: use MQTT QoS 0 for high-rate telemetry, QoS 1 for alerts
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
import paho.mqtt.client as mqtt
import json
import time
import threading
from typing import Optional

from phantom_msgs.msg import (
    FusedPose,
    ConfidenceScore,
    NavMode,
    PhantomAlert,
    StateEstimate,
)

SENSOR_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    history=HistoryPolicy.KEEP_LAST,
    depth=5
)


class PhantomInterfaceNode(Node):
    """Async MQTT bridge between edge and cloud."""

    def __init__(self):
        super().__init__('phantom_interface_node')

        self.declare_parameter('drone_id',          'drone-001')
        self.declare_parameter('broker_host',       'localhost')
        self.declare_parameter('broker_port',        1883)
        self.declare_parameter('broker_tls',         False)
        self.declare_parameter('telemetry_rate_hz',  5.0)
        self.declare_parameter('confidence_rate_hz', 2.0)
        self.declare_parameter('mqtt_keepalive_s',   60)
        self.declare_parameter('reconnect_delay_s',   5.0)

        self._drone_id    = self.get_parameter('drone_id').value
        self._broker_host = self.get_parameter('broker_host').value
        self._broker_port = int(self.get_parameter('broker_port').value)
        self._tls         = self.get_parameter('broker_tls').value

        # ── MQTT client setup ──────────────────────────────────
        self._mqtt = mqtt.Client(
            client_id=f'phantomnav-edge-{self._drone_id}',
            protocol=mqtt.MQTTv311,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION1
        )
        self._mqtt.on_connect    = self._on_mqtt_connect
        self._mqtt.on_disconnect = self._on_mqtt_disconnect
        self._mqtt.on_message    = self._on_mqtt_message
        self._connected = False

        if self._tls:
            self._mqtt.tls_set()

        # ── Latest data snapshots ──────────────────────────────
        self._latest_fused:      Optional[FusedPose]       = None
        self._latest_state:      Optional[StateEstimate]    = None
        self._latest_confidence: Optional[ConfidenceScore]  = None
        self._latest_nav_mode:   Optional[NavMode]          = None

        # ── ROS 2 Subscriptions ────────────────────────────────
        self.create_subscription(FusedPose,      '/fusion/pose',       self._on_fused, SENSOR_QOS)
        self.create_subscription(StateEstimate,  '/state/estimate',    self._on_state, SENSOR_QOS)
        self.create_subscription(ConfidenceScore,'/confidence/score',  self._on_confidence, 10)
        self.create_subscription(NavMode,        '/nav/mode',          self._on_nav_mode, 10)
        self.create_subscription(PhantomAlert,   '/alerts',            self._on_alert, 10)

        # ── Publish timers ─────────────────────────────────────
        tel_hz  = self.get_parameter('telemetry_rate_hz').value
        conf_hz = self.get_parameter('confidence_rate_hz').value
        self.create_timer(1.0 / tel_hz,  self._publish_telemetry)
        self.create_timer(1.0 / conf_hz, self._publish_confidence)
        self.create_timer(5.0,           self._publish_status)

        # ── Connect MQTT in background thread ──────────────────
        self._connect_thread = threading.Thread(
            target=self._mqtt_connect_loop, daemon=True)
        self._connect_thread.start()

        self.get_logger().info(
            f'PhantomInterface™ started. Drone: {self._drone_id} '
            f'→ mqtt://{self._broker_host}:{self._broker_port}')

    # ── ROS 2 topic callbacks ──────────────────────────────────

    def _on_fused(self, msg: FusedPose):
        self._latest_fused = msg

    def _on_state(self, msg: StateEstimate):
        self._latest_state = msg

    def _on_confidence(self, msg: ConfidenceScore):
        self._latest_confidence = msg

    def _on_nav_mode(self, msg: NavMode):
        self._latest_nav_mode = msg

    def _on_alert(self, msg: PhantomAlert):
        """Alerts are published immediately on receipt (QoS 1)."""
        if not self._connected:
            return
        payload = {
            'ts':        self._ros_ts(),
            'drone_id':  self._drone_id,
            'severity':  msg.severity,
            'source':    msg.source,
            'code':      msg.code,
            'message':   msg.message,
            'confidence':msg.confidence_at_alert,
            'nav_mode':  msg.nav_mode_at_alert,
        }
        topic = f'phantom/{self._drone_id}/alerts'
        self._mqtt_publish(topic, payload, qos=1)

    # ── MQTT publish helpers ───────────────────────────────────

    def _ros_ts(self) -> float:
        return self.get_clock().now().nanoseconds / 1e9

    def _mqtt_publish(self, topic: str, payload: dict, qos: int = 0):
        if not self._connected:
            return
        try:
            self._mqtt.publish(topic, json.dumps(payload), qos=qos)
        except Exception as e:
            self.get_logger().warn(f'MQTT publish error: {e}')

    # ── Timed publish callbacks ────────────────────────────────

    def _publish_telemetry(self):
        if not self._connected or not self._latest_fused:
            return
        f = self._latest_fused
        s = self._latest_state

        payload = {
            'ts':       self._ros_ts(),
            'drone_id': self._drone_id,
            'pose': {
                'x': f.x, 'y': f.y, 'z': f.z,
                'qw': f.qw, 'qx': f.qx, 'qy': f.qy, 'qz': f.qz,
            },
            'velocity':  {'vx': f.vx, 'vy': f.vy, 'vz': f.vz},
            'fusion':    {'w_ins': f.w_ins, 'w_slam': f.w_slam,
                          'drift_m': f.drift_estimate_m},
            'gnss_valid': s.gnss_valid if s else False,
        }
        self._mqtt_publish(f'phantom/{self._drone_id}/telemetry', payload)

    def _publish_confidence(self):
        if not self._connected or not self._latest_confidence:
            return
        c = self._latest_confidence
        payload = {
            'ts':        self._ros_ts(),
            'drone_id':  self._drone_id,
            'score':     round(c.score, 2),
            'level':     c.level,
            'sub_scores': {
                'imu_stability': round(c.sensor_stability, 3),
                'slam_quality':  round(c.slam_quality, 3),
                'drift_penalty': round(c.drift_penalty, 3),
                'gnss_factor':   round(c.gnss_factor, 3),
            },
        }
        self._mqtt_publish(f'phantom/{self._drone_id}/confidence', payload, qos=0)

    def _publish_status(self):
        if not self._connected or not self._latest_nav_mode:
            return
        m = self._latest_nav_mode
        payload = {
            'ts':            self._ros_ts(),
            'drone_id':      self._drone_id,
            'nav_mode':      m.mode,
            'nav_mode_name': m.mode_name,
            'gnss_available': m.gnss_available,
            'slam_available': m.slam_available,
        }
        self._mqtt_publish(f'phantom/{self._drone_id}/status', payload, qos=1)

    # ── MQTT connection management ─────────────────────────────

    def _mqtt_connect_loop(self):
        """Runs in background thread, retries connection."""
        delay = float(self.get_parameter('reconnect_delay_s').value)
        while rclpy.ok():
            try:
                self.get_logger().info(
                    f'Connecting to MQTT broker {self._broker_host}:{self._broker_port}...')
                self._mqtt.connect(
                    self._broker_host,
                    self._broker_port,
                    keepalive=int(self.get_parameter('mqtt_keepalive_s').value))
                self._mqtt.loop_forever()
            except Exception as e:
                self.get_logger().warn(
                    f'MQTT connection failed: {e}. Retrying in {delay}s...')
                time.sleep(delay)

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected = True
            self.get_logger().info('MQTT broker connected.')
            # Subscribe to cloud → UAV topics
            client.subscribe(f'phantom/{self._drone_id}/command', qos=1)
            client.subscribe(f'phantom/{self._drone_id}/mission',  qos=1)
        else:
            self.get_logger().error(f'MQTT connect failed, rc={rc}')

    def _on_mqtt_disconnect(self, client, userdata, rc):
        self._connected = False
        self.get_logger().warn(f'MQTT disconnected (rc={rc}). Reconnecting...')

    def _on_mqtt_message(self, client, userdata, msg):
        """Handle incoming cloud commands (async, non-blocking)."""
        try:
            payload = json.loads(msg.payload.decode())
            topic   = msg.topic
            self.get_logger().info(f'Cloud message on {topic}: {payload}')
            # TODO: forward to ROS 2 command topics
        except json.JSONDecodeError as e:
            self.get_logger().warn(f'Invalid MQTT payload: {e}')


def main(args=None):
    rclpy.init(args=args)
    node = PhantomInterfaceNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

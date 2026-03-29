#!/usr/bin/env python3
"""
PhantomNav™ — AirSim GNSS-Denied Simulation
Simulates three-phase flight scenario:
  Phase 1 — GNSS nominal flight (0–30 s)
  Phase 2 — GNSS loss mid-flight (30–90 s)
  Phase 3 — Sensor degradation (90–120 s)
  Phase 4 — Recovery and return (120–150 s)

Publishes synthetic sensor data to ROS 2 topics so the full
edge stack can be tested in simulation without real hardware.
"""

import rclpy
from rclpy.node import Node
import airsim
import numpy as np
import time
import math
from dataclasses import dataclass
from enum import Enum

from sensor_msgs.msg import Imu, NavSatFix, NavSatStatus
from geometry_msgs.msg import TwistWithCovarianceStamped
from std_msgs.msg import Header


class SimPhase(Enum):
    GNSS_NOMINAL    = "GNSS_NOMINAL"
    GNSS_LOST       = "GNSS_LOST"
    SENSOR_DEGRADED = "SENSOR_DEGRADED"
    RECOVERY        = "RECOVERY"


@dataclass
class SimConfig:
    phase_durations: dict = None
    imu_noise_nominal:   float = 0.01   # m/s^2
    imu_noise_degraded:  float = 0.15
    gnss_accuracy_m:     float = 1.5
    waypoints: list = None

    def __post_init__(self):
        if self.phase_durations is None:
            self.phase_durations = {
                SimPhase.GNSS_NOMINAL:    30.0,
                SimPhase.GNSS_LOST:       60.0,
                SimPhase.SENSOR_DEGRADED: 30.0,
                SimPhase.RECOVERY:        30.0,
            }
        if self.waypoints is None:
            self.waypoints = [
                (0,    0,   -10),   # Takeoff
                (50,   0,   -20),   # Fly north
                (50,   50,  -20),   # Turn east
                (0,    50,  -15),   # Return leg
                (0,    0,   -5),    # Approach home
            ]


class PhantomSimNode(Node):
    """
    AirSim bridge node.
    Connects to AirSim, drives the UAV, and publishes sensor data
    to the PhantomNav edge stack via ROS 2 topics.
    """

    def __init__(self):
        super().__init__('phantom_sim_node')

        self.declare_parameter('sim_speed',       1.0)
        self.declare_parameter('airsim_host',     '127.0.0.1')
        self.declare_parameter('origin_lat',      14.6760)  # Cebu City
        self.declare_parameter('origin_lon',      121.0437)
        self.declare_parameter('origin_alt',      10.0)

        self._cfg = SimConfig()
        self._phase = SimPhase.GNSS_NOMINAL
        self._phase_start = time.monotonic()
        self._sim_start   = time.monotonic()

        self._origin_lat = self.get_parameter('origin_lat').value
        self._origin_lon = self.get_parameter('origin_lon').value
        self._origin_alt = self.get_parameter('origin_alt').value

        # ── Publishers (feed into PhantomNav edge modules) ─────
        self._imu_pub  = self.create_publisher(Imu, '/imu/data', 10)
        self._fix_pub  = self.create_publisher(NavSatFix, '/gnss/fix', 10)
        self._vel_pub  = self.create_publisher(
            TwistWithCovarianceStamped, '/gnss/velocity', 10)

        # ── AirSim client ──────────────────────────────────────
        host = self.get_parameter('airsim_host').value
        try:
            self._client = airsim.MultirotorClient(ip=host)
            self._client.confirmConnection()
            self._client.enableApiControl(True)
            self._client.armDisarm(True)
            self._airsim_ok = True
            self.get_logger().info(f"AirSim connected at {host}")
        except Exception as e:
            self.get_logger().warn(
                f"AirSim not available ({e}). Running in sensor-only mode.")
            self._airsim_ok = False
            self._client = None

        # ── Simulation timers ──────────────────────────────────
        self.create_timer(0.005,  self._tick_imu)     # 200 Hz IMU
        self.create_timer(0.1,    self._tick_gnss)    # 10 Hz GNSS
        self.create_timer(1.0,    self._tick_phase)   # Phase manager
        self.create_timer(5.0,    self._print_status)

        self.get_logger().info("PhantomNav™ Simulation started.")
        self._log_scenario()

    # ── Phase management ───────────────────────────────────────

    def _tick_phase(self):
        now  = time.monotonic()
        age  = now - self._phase_start
        dur  = self._cfg.phase_durations[self._phase]

        if age >= dur:
            self._advance_phase()

    def _advance_phase(self):
        phases = list(SimPhase)
        idx    = phases.index(self._phase)
        if idx + 1 < len(phases):
            self._phase       = phases[idx + 1]
            self._phase_start = time.monotonic()
            self.get_logger().warn(
                f"[SIM] ▶ Phase transition → {self._phase.value}")

            if self._phase == SimPhase.GNSS_LOST:
                self.get_logger().error(
                    "[SIM] ✈ GNSS SIGNAL LOST — edge autonomy takes over")
            elif self._phase == SimPhase.SENSOR_DEGRADED:
                self.get_logger().error(
                    "[SIM] ⚠ Sensor degradation injected")
            elif self._phase == SimPhase.RECOVERY:
                self.get_logger().info(
                    "[SIM] ✓ GNSS recovering...")

    # ── IMU publisher ──────────────────────────────────────────

    def _tick_imu(self):
        stamp = self.get_clock().now().to_msg()

        if self._airsim_ok and self._client:
            imu_data = self._client.getImuData()
            ax = imu_data.linear_acceleration.x_val
            ay = imu_data.linear_acceleration.y_val
            az = imu_data.linear_acceleration.z_val
            gx = imu_data.angular_velocity.x_val
            gy = imu_data.angular_velocity.y_val
            gz = imu_data.angular_velocity.z_val
        else:
            # Synthetic: hover + sinusoidal motion
            t   = time.monotonic() - self._sim_start
            ax  = 0.1 * math.sin(0.5 * t)
            ay  = 0.1 * math.cos(0.3 * t)
            az  = -9.80665 + 0.05 * math.sin(t)
            gx  = 0.005 * math.sin(t)
            gy  = 0.005 * math.cos(t)
            gz  = 0.001

        # Inject noise based on current phase
        noise = (self._cfg.imu_noise_degraded
                 if self._phase == SimPhase.SENSOR_DEGRADED
                 else self._cfg.imu_noise_nominal)

        rng = np.random.default_rng()
        ax += rng.normal(0, noise)
        ay += rng.normal(0, noise)
        az += rng.normal(0, noise * 0.5)

        msg = Imu()
        msg.header.stamp    = stamp
        msg.header.frame_id = "imu_link"
        msg.linear_acceleration.x = ax
        msg.linear_acceleration.y = ay
        msg.linear_acceleration.z = az
        msg.angular_velocity.x = gx
        msg.angular_velocity.y = gy
        msg.angular_velocity.z = gz
        # Covariance
        cov_a = noise * noise
        msg.linear_acceleration_covariance = [
            cov_a, 0, 0,
            0, cov_a, 0,
            0, 0, cov_a,
        ]
        self._imu_pub.publish(msg)

    # ── GNSS publisher ─────────────────────────────────────────

    def _tick_gnss(self):
        stamp = self.get_clock().now().to_msg()

        # Suppress GNSS during GNSS_LOST and SENSOR_DEGRADED phases
        gnss_active = self._phase in (
            SimPhase.GNSS_NOMINAL, SimPhase.RECOVERY)

        # Ramp accuracy during recovery
        if self._phase == SimPhase.RECOVERY:
            t_rec = time.monotonic() - self._phase_start
            recovery_ratio = min(1.0, t_rec / 15.0)
            gnss_acc = self._cfg.gnss_accuracy_m + 10.0 * (1.0 - recovery_ratio)
        else:
            gnss_acc = self._cfg.gnss_accuracy_m

        if gnss_active and self._airsim_ok and self._client:
            gps_data = self._client.getGpsData()
            lat = gps_data.gnss.geo_point.latitude
            lon = gps_data.gnss.geo_point.longitude
            alt = gps_data.gnss.geo_point.altitude
        elif gnss_active:
            # Synthetic: drift from origin
            t   = time.monotonic() - self._sim_start
            lat = self._origin_lat + t * 1e-5
            lon = self._origin_lon + t * 5e-6
            alt = self._origin_alt + 20.0 + 2.0 * math.sin(t * 0.1)
        else:
            # No GNSS — publish invalid fix
            fix = NavSatFix()
            fix.header.stamp    = stamp
            fix.header.frame_id = "gnss"
            fix.status.status   = NavSatStatus.STATUS_NO_FIX
            self._fix_pub.publish(fix)
            return

        # Add noise
        rng = np.random.default_rng()
        lat += rng.normal(0, gnss_acc / 111320)
        lon += rng.normal(0, gnss_acc / 111320)

        fix = NavSatFix()
        fix.header.stamp    = stamp
        fix.header.frame_id = "gnss"
        fix.status.status   = NavSatStatus.STATUS_FIX
        fix.latitude        = lat
        fix.longitude       = lon
        fix.altitude        = alt
        # 3x3 diagonal covariance
        cov = gnss_acc * gnss_acc
        fix.position_covariance = [
            cov, 0, 0,
            0, cov, 0,
            0, 0, cov * 4,
        ]
        fix.position_covariance_type = NavSatFix.COVARIANCE_TYPE_DIAGONAL_KNOWN
        self._fix_pub.publish(fix)

        # Velocity (synthetic)
        vel = TwistWithCovarianceStamped()
        vel.header.stamp    = stamp
        vel.header.frame_id = "gnss"
        t   = time.monotonic() - self._sim_start
        vel.twist.twist.linear.x = 2.0 * math.cos(t * 0.1)
        vel.twist.twist.linear.y = 2.0 * math.sin(t * 0.1)
        vel.twist.twist.linear.z = 0.1
        vel.twist.covariance[0]  = 0.01
        self._vel_pub.publish(vel)

    # ── Status / logging ───────────────────────────────────────

    def _log_scenario(self):
        self.get_logger().info("=" * 60)
        self.get_logger().info("PhantomNav™ GNSS-Denied Scenario")
        self.get_logger().info("  Phase 1 (0–30s):   GNSS nominal")
        self.get_logger().info("  Phase 2 (30–90s):  GNSS LOST → INS+SLAM")
        self.get_logger().info("  Phase 3 (90–120s): Sensor degradation")
        self.get_logger().info("  Phase 4 (120–150s):Recovery + return")
        self.get_logger().info("=" * 60)

    def _print_status(self):
        age = time.monotonic() - self._phase_start
        dur = self._cfg.phase_durations[self._phase]
        self.get_logger().info(
            f"[SIM] Phase: {self._phase.value:<20} "
            f"{age:.0f}/{dur:.0f}s elapsed")


def main(args=None):
    rclpy.init(args=args)
    node = PhantomSimNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()

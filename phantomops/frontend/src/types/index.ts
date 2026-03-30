// PhantomOps™ — Core Type Definitions

export type NavMode =
  | 'GNSS_PRIMARY'
  | 'INS_SLAM_FUSION'
  | 'INS_ONLY'
  | 'SAFE_MODE'
  | 'EMERGENCY_HOLD'
  | 'UNKNOWN';

export type DroneStatus = 'active' | 'warning' | 'critical' | 'offline';
export type ConfidenceLevel = 'NOMINAL' | 'DEGRADED' | 'CRITICAL' | 'UNSAFE';

export interface Position {
  x: number;
  y: number;
  z: number;
}

export interface Quaternion {
  qw: number;
  qx: number;
  qy: number;
  qz: number;
}

export interface SubScores {
  imu_stability: number;
  slam_quality: number;
  drift_penalty: number;
  gnss_factor: number;
}

export interface TelemetryData {
  ts: number;
  drone_id: string;
  pose: Position & Quaternion;
  velocity: { vx: number; vy: number; vz: number };
  fusion: { w_ins: number; w_slam: number; drift_m: number };
  gnss_valid: boolean;
}

export interface ConfidenceData {
  ts: number;
  drone_id: string;
  score: number;
  level: ConfidenceLevel;
  sub_scores: SubScores;
}

export interface DroneState {
  drone_id: string;
  name?: string;
  model?: string;
  status: DroneStatus;
  confidence?: number;
  conf_level?: ConfidenceLevel;
  nav_mode?: NavMode;
  gnss_valid?: boolean;
  last_seen?: number;
  age_s?: number;
  position?: Position;
  telemetry?: TelemetryData;
}

export interface Alert {
  ts: number;
  drone_id: string;
  severity: number; // 0=INFO 1=WARN 2=ERROR 3=CRITICAL
  source: string;
  code: string;
  message: string;
  confidence_at_alert?: number;
  nav_mode_at_alert?: number;
}

export interface Waypoint {
  seq: number;
  x: number;
  y: number;
  z: number;
  hold_time_s?: number;
  action?: string;
}

export interface Mission {
  id?: string;
  drone_id: string;
  name: string;
  description?: string;
  waypoints: Waypoint[];
  max_speed_ms?: number;
  return_home?: boolean;
  gnss_required?: boolean;
  status?: 'PLANNED' | 'ACTIVE' | 'PAUSED' | 'COMPLETED' | 'ABORTED';
  created_at?: number;
}

export interface ConfidenceTrendBucket {
  t_start: number;
  mean: number;
  min: number;
}

export interface DriftSummary {
  drone_id: string;
  window_s: number;
  sample_count: number;
  drift_m: { mean: number; std: number; max: number; p95: number };
  drift_rate_m_per_s: number;
  drift_spikes: number;
  gnss_loss_segments: number;
  slam_usage: { mean_weight: number; max_weight: number };
}

// WebSocket message types
export interface WsMessage<T = unknown> {
  type: string;
  drone_id?: string;
  ts: number;
  data: T;
}

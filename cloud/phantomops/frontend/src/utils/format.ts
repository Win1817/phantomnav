// PhantomOps™ — Confidence & nav mode utilities

import { NavMode, DroneStatus, ConfidenceLevel } from '../types';

export function confidenceColor(score: number): string {
  if (score >= 70) return '#00ff9d';   // green
  if (score >= 40) return '#f5a623';   // amber
  if (score >= 20) return '#ff4d4d';   // red
  return '#ff0055';                    // critical red
}

export function confidenceColorHex(score: number): string {
  if (score >= 70) return '#00ff9d';
  if (score >= 40) return '#f5a623';
  return '#ff4d4d';
}

export function statusColor(status: DroneStatus): string {
  switch (status) {
    case 'active':   return '#00ff9d';
    case 'warning':  return '#f5a623';
    case 'critical': return '#ff4d4d';
    case 'offline':  return '#4a5568';
    default:         return '#718096';
  }
}

export function navModeLabel(mode: NavMode | string): string {
  switch (mode) {
    case 'GNSS_PRIMARY':    return 'GNSS PRIMARY';
    case 'INS_SLAM_FUSION': return 'INS + SLAM';
    case 'INS_ONLY':        return 'INS ONLY';
    case 'SAFE_MODE':       return 'SAFE MODE';
    case 'EMERGENCY_HOLD':  return 'EMERGENCY';
    default:                return mode ?? 'UNKNOWN';
  }
}

export function navModeColor(mode: NavMode | string): string {
  switch (mode) {
    case 'GNSS_PRIMARY':    return '#00ff9d';
    case 'INS_SLAM_FUSION': return '#63b3ed';
    case 'INS_ONLY':        return '#f5a623';
    case 'SAFE_MODE':       return '#ff4d4d';
    case 'EMERGENCY_HOLD':  return '#ff0055';
    default:                return '#718096';
  }
}

export function severityLabel(severity: number): string {
  return ['INFO', 'WARNING', 'ERROR', 'CRITICAL'][Math.min(severity, 3)];
}

export function severityColor(severity: number): string {
  return ['#63b3ed', '#f5a623', '#ff4d4d', '#ff0055'][Math.min(severity, 3)];
}

export function formatTs(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString('en-US', { hour12: false });
}

export function formatAge(ts: number): string {
  const age = Date.now() / 1000 - ts;
  if (age < 5)   return 'LIVE';
  if (age < 60)  return `${Math.round(age)}s ago`;
  if (age < 3600) return `${Math.round(age / 60)}m ago`;
  return `${Math.round(age / 3600)}h ago`;
}

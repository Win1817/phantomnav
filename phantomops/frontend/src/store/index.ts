// PhantomOps™ — Global State Store (Zustand)

import { create } from 'zustand';
import { DroneState, Alert, TelemetryData, ConfidenceData, WsMessage } from '../types';

interface FleetStore {
  // Auth
  token: string | null;
  user: Record<string, unknown> | null;
  setAuth: (token: string, user: Record<string, unknown>) => void;
  clearAuth: () => void;

  // Fleet
  drones: Record<string, DroneState>;
  selectedDroneId: string | null;
  setSelectedDrone: (id: string | null) => void;
  upsertDrone: (drone: DroneState) => void;

  // Real-time telemetry history (last 300 points per drone)
  telemetryHistory: Record<string, TelemetryData[]>;
  confidenceHistory: Record<string, ConfidenceData[]>;
  pushTelemetry: (data: TelemetryData) => void;
  pushConfidence: (data: ConfidenceData) => void;

  // Alerts
  alerts: Alert[];
  unreadAlerts: number;
  pushAlert: (alert: Alert) => void;
  markAlertsRead: () => void;

  // WebSocket status
  wsConnected: boolean;
  mqttConnected: boolean;
  setWsConnected: (v: boolean) => void;
  setMqttConnected: (v: boolean) => void;

  // Ingest a raw WebSocket message
  ingestWsMessage: (msg: WsMessage) => void;
}

const MAX_HISTORY = 300;

export const useStore = create<FleetStore>((set, get) => ({
  // ── Auth ──────────────────────────────────────────────────
  token: localStorage.getItem('phantomops_token'),
  user: null,
  setAuth: (token, user) => {
    localStorage.setItem('phantomops_token', token);
    set({ token, user });
  },
  clearAuth: () => {
    localStorage.removeItem('phantomops_token');
    set({ token: null, user: null });
  },

  // ── Fleet ─────────────────────────────────────────────────
  drones: {},
  selectedDroneId: null,
  setSelectedDrone: (id) => set({ selectedDroneId: id }),
  upsertDrone: (drone) =>
    set((s) => ({ drones: { ...s.drones, [drone.drone_id]: { ...s.drones[drone.drone_id], ...drone } } })),

  // ── History ───────────────────────────────────────────────
  telemetryHistory: {},
  confidenceHistory: {},

  pushTelemetry: (data) =>
    set((s) => {
      const prev = s.telemetryHistory[data.drone_id] ?? [];
      const next = [...prev, data].slice(-MAX_HISTORY);
      return { telemetryHistory: { ...s.telemetryHistory, [data.drone_id]: next } };
    }),

  pushConfidence: (data) =>
    set((s) => {
      const prev = s.confidenceHistory[data.drone_id] ?? [];
      const next = [...prev, data].slice(-MAX_HISTORY);
      return { confidenceHistory: { ...s.confidenceHistory, [data.drone_id]: next } };
    }),

  // ── Alerts ────────────────────────────────────────────────
  alerts: [],
  unreadAlerts: 0,
  pushAlert: (alert) =>
    set((s) => ({
      alerts: [alert, ...s.alerts].slice(0, 200),
      unreadAlerts: s.unreadAlerts + 1,
    })),
  markAlertsRead: () => set({ unreadAlerts: 0 }),

  // ── WS status ─────────────────────────────────────────────
  wsConnected: false,
  mqttConnected: false,
  setWsConnected: (v) => set({ wsConnected: v }),
  setMqttConnected: (v) => set({ mqttConnected: v }),

  // ── Message ingestion ─────────────────────────────────────
  ingestWsMessage: (msg: WsMessage) => {
    const { type, drone_id, data } = msg;
    const store = get();

    if (type === 'mqtt_connected')   { store.setMqttConnected(true);  return; }
    if (type === 'mqtt_disconnected'){ store.setMqttConnected(false); return; }

    if (!drone_id) return;

    if (type === 'phantom_telemetry') {
      const tel = data as TelemetryData;
      store.pushTelemetry({ ...tel, drone_id });
      store.upsertDrone({
        drone_id,
        status: 'active',
        gnss_valid: tel.gnss_valid,
        last_seen: tel.ts,
        position: tel.pose,
        telemetry: tel,
      });
    }

    if (type === 'phantom_confidence') {
      const conf = data as ConfidenceData;
      store.pushConfidence({ ...conf, drone_id });
      const score = conf.score;
      const status = score >= 70 ? 'active' : score >= 40 ? 'warning' : score >= 20 ? 'critical' : 'offline';
      store.upsertDrone({
        drone_id,
        status,
        confidence: score,
        conf_level: conf.level,
      });
    }

    if (type === 'phantom_status') {
      const d = data as Record<string, unknown>;
      store.upsertDrone({
        drone_id,
        status: store.drones[drone_id]?.status ?? 'active',
        nav_mode: d.nav_mode_name as string,
        gnss_valid: d.gnss_available as boolean,
      });
    }

    if (type === 'phantom_alerts') {
      const alert = data as Alert;
      store.pushAlert({ ...alert, drone_id });
    }
  },
}));

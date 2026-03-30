// PhantomOps™ — WebSocket hook
// Maintains a persistent WS connection to the ops backend.
// Auto-reconnects with exponential backoff.

import { useEffect, useRef, useCallback } from 'react';
import { useStore } from '../store';
import { WsMessage } from '../types';

const WS_URL = import.meta.env.VITE_WS_URL ?? `ws://${window.location.host}/ws`;

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryDelay = useRef(1000);

  const { setWsConnected, ingestWsMessage, token } = useStore((s) => ({
    setWsConnected: s.setWsConnected,
    ingestWsMessage: s.ingestWsMessage,
    token: s.token,
  }));

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const url = token ? `${WS_URL}?token=${token}` : WS_URL;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsConnected(true);
      retryDelay.current = 1000;
      // Subscribe to all drones
      ws.send(JSON.stringify({ type: 'subscribe', drones: ['*'] }));
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as WsMessage;
        ingestWsMessage(msg);
      } catch {
        // ignore malformed
      }
    };

    ws.onclose = () => {
      setWsConnected(false);
      wsRef.current = null;
      // Exponential backoff, cap at 30s
      retryRef.current = setTimeout(() => {
        retryDelay.current = Math.min(retryDelay.current * 1.5, 30000);
        connect();
      }, retryDelay.current);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [token, setWsConnected, ingestWsMessage]);

  useEffect(() => {
    connect();
    const ping = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping' }));
      }
    }, 20000);

    return () => {
      clearInterval(ping);
      if (retryRef.current) clearTimeout(retryRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const send = useCallback((msg: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  return { send };
}

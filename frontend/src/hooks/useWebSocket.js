/**
 * useWebSocket.js — Phase 5: Real-Time WebSocket Hook
 * -----------------------------------------------------
 * Custom React hook that manages a persistent WebSocket connection
 * to the backend border surveillance API.
 *
 * Features:
 *   - Auto-connects on mount, auto-disconnects on unmount
 *   - Exponential-backoff reconnection (up to MAX_RETRIES)
 *   - Exposes: isConnected, lastMessage, sendMessage
 *   - onMessage callback fires for every parsed incoming event
 *
 * Usage:
 *   const { isConnected, lastMessage } = useWebSocket({
 *     url: 'ws://localhost:8000/api/v1/ws',
 *     onMessage: (parsedData) => { ... },
 *   });
 */

import { useEffect, useRef, useCallback, useState } from 'react';

const MAX_RETRIES     = 5;
const BASE_DELAY_MS   = 1000;  // 1 s initial reconnect delay
const MAX_DELAY_MS    = 30000; // 30 s cap

export function useWebSocket({ url, onMessage, enabled = true }) {
  const wsRef        = useRef(null);
  const retryCount   = useRef(0);
  const retryTimer   = useRef(null);
  const unmounted    = useRef(false);

  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState(null);

  const onMessageRef = useRef(onMessage);
  useEffect(() => { onMessageRef.current = onMessage; }, [onMessage]);

  const clearRetryTimer = () => {
    if (retryTimer.current) {
      clearTimeout(retryTimer.current);
      retryTimer.current = null;
    }
  };

  const connect = useCallback(() => {
    if (unmounted.current || !enabled) return;
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return;

    console.log(`[WS] Connecting to ${url} (attempt ${retryCount.current + 1})`);
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (unmounted.current) { ws.close(); return; }
      console.log('[WS] Connection established.');
      retryCount.current = 0;
      setIsConnected(true);
    };

    ws.onmessage = (event) => {
      if (unmounted.current) return;
      try {
        const parsed = JSON.parse(event.data);
        setLastMessage(parsed);
        if (onMessageRef.current) onMessageRef.current(parsed);
      } catch (err) {
        console.warn('[WS] Could not parse message:', event.data, err);
      }
    };

    ws.onclose = (event) => {
      if (unmounted.current) return;
      setIsConnected(false);

      // Attempt to reconnect unless we exceeded max retries or close was clean
      if (!event.wasClean && retryCount.current < MAX_RETRIES) {
        const delay = Math.min(BASE_DELAY_MS * 2 ** retryCount.current, MAX_DELAY_MS);
        retryCount.current += 1;
        clearRetryTimer();
        retryTimer.current = setTimeout(connect, delay);
      } else if (retryCount.current >= MAX_RETRIES) {
        console.warn('[WS] Max retries reached. Giving up.');
      }
    };

    ws.onerror = () => {
      // onclose will fire next and handle clean reconnect if needed
    };
  }, [url, enabled]);

  // Connect on mount, disconnect on unmount
  useEffect(() => {
    unmounted.current = false;
    if (enabled) connect();

    return () => {
      unmounted.current = true;
      clearRetryTimer();
      if (wsRef.current) {
        const currentWs = wsRef.current;
        if (currentWs.readyState === WebSocket.CONNECTING) {
          currentWs.onopen = () => {
            currentWs.close(1000, 'Component unmounted');
          };
        } else if (currentWs.readyState === WebSocket.OPEN) {
          currentWs.close(1000, 'Component unmounted');
        }
        wsRef.current = null;
      }
      setIsConnected(false);
    };
  }, [connect, enabled]);

  const sendMessage = useCallback((data) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(typeof data === 'string' ? data : JSON.stringify(data));
    } else {
      console.warn('[WS] Cannot send — socket not open.');
    }
  }, []);

  return { isConnected, lastMessage, sendMessage };
}

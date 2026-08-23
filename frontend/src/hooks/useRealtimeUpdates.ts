import { useEffect, useRef } from "react";
import { getRealtimeSubprotocol, getRealtimeWebSocketUrl } from "@/api/client";
import { useAuth } from "@/contexts/AuthContext";

export const REALTIME_DATA_CHANGED_EVENT = "dayflow:data-changed";

export interface RealtimeDataChangedEvent {
  type: "data_changed";
  model: string;
  action: "created" | "updated" | "deleted";
  record_id: number | null;
  timestamp: string;
}

export const useRealtimeUpdates = () => {
  const { isAuthenticated } = useAuth();
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const dispatchTimerRef = useRef<number | null>(null);
  const latestPayloadRef = useRef<RealtimeDataChangedEvent | null>(null);

  useEffect(() => {
    if (!isAuthenticated) {
      return;
    }

    let cancelled = false;
    let retryCount = 0;

    const connect = () => {
      const socketUrl = getRealtimeWebSocketUrl();
      if (!socketUrl || cancelled) {
        return;
      }

      // The credential travels as a subprotocol rather than a query parameter,
      // which kept it out of access logs and browser history (audit V-12).
      const subprotocol = getRealtimeSubprotocol();
      const socket = subprotocol
        ? new WebSocket(socketUrl, subprotocol)
        : new WebSocket(socketUrl);
      socketRef.current = socket;

      socket.onopen = () => {
        retryCount = 0;
      };

      socket.onmessage = (message) => {
        try {
          const payload = JSON.parse(message.data) as RealtimeDataChangedEvent | { type?: string };
          if (payload.type !== "data_changed") {
            return;
          }

          latestPayloadRef.current = payload as RealtimeDataChangedEvent;
          if (dispatchTimerRef.current !== null) {
            window.clearTimeout(dispatchTimerRef.current);
          }

          dispatchTimerRef.current = window.setTimeout(() => {
            if (!latestPayloadRef.current) {
              return;
            }

            window.dispatchEvent(
              new CustomEvent<RealtimeDataChangedEvent>(REALTIME_DATA_CHANGED_EVENT, {
                detail: latestPayloadRef.current,
              }),
            );
          }, 100);
        } catch {
          // Ignore malformed realtime messages.
        }
      };

      socket.onclose = () => {
        socketRef.current = null;
        if (cancelled) {
          return;
        }

        const delay = Math.min(30000, 1000 * 2 ** Math.min(retryCount, 5));
        retryCount += 1;
        reconnectTimerRef.current = window.setTimeout(connect, delay);
      };

      socket.onerror = () => {
        socket.close();
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
      }
      if (dispatchTimerRef.current !== null) {
        window.clearTimeout(dispatchTimerRef.current);
      }
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [isAuthenticated]);
};

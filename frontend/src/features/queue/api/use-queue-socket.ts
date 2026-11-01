import { useEffect, useRef, useState } from "react";
import { client } from "@/api/client";

export interface IncomingCallEvent {
  event: "CALLED";
  atendimento_id: string;
  medico_id: string;
  status: string;
  ttl_segundos: number;
  chamada_iniciada_em: string;
}

export interface QueueSocketEvent {
  event: string;
  atendimento_id?: string;
  [key: string]: unknown;
}

export interface UseQueueSocketOptions {
  atendimentoId?: string;
  token?: string;
  enabled?: boolean;
  onCallReceived?: (event: IncomingCallEvent) => void;
  onEvent?: (event: QueueSocketEvent) => void;
}

/**
 * Hook headless para conexão e streaming contínuo via WebSocket com a fila virtual.
 * Rota canônica: /ws/queue/{atendimento_id}?token={token} (Issue #42 / ADR-002 / ADR-011).
 */
export function useQueueSocket({
  atendimentoId,
  token,
  enabled = true,
  onCallReceived,
  onEvent,
}: UseQueueSocketOptions) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<QueueSocketEvent | null>(null);
  const [calledEvent, setCalledEvent] = useState<IncomingCallEvent | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const attemptRef = useRef(0);

  useEffect(() => {
    if (!enabled || !atendimentoId || !token) {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setIsConnected(false);
      return;
    }

    let isMounted = true;

    const authToken = token;

    function getWsUrl(): string {
      const config = client.getConfig();
      const rawBase =
        config.baseUrl ||
        (typeof window !== "undefined" ? window.location.origin : "http://localhost:8000");
      const base = rawBase.replace(/^http/, "ws");
      return `${base}/ws/queue/${atendimentoId}?token=${encodeURIComponent(authToken)}`;
    }

    function connect() {
      if (!isMounted) return;

      try {
        const wsUrl = getWsUrl();
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          if (!isMounted) return;
          setIsConnected(true);
          attemptRef.current = 0;
        };

        ws.onmessage = (messageEvent) => {
          if (!isMounted) return;
          try {
            const data = JSON.parse(messageEvent.data) as QueueSocketEvent;
            setLastEvent(data);
            onEvent?.(data);

            if (data.event === "CALLED") {
              const callEvent = data as unknown as IncomingCallEvent;
              setCalledEvent(callEvent);
              onCallReceived?.(callEvent);
            }
          } catch {
            // Silencioso em mensagens não-JSON ou pings textuais
          }
        };

        ws.onclose = () => {
          if (!isMounted) return;
          setIsConnected(false);
          wsRef.current = null;

          // Reconexão com backoff exponencial (1s, 2s, máx 5s)
          const delay = Math.min(1000 * 2 ** attemptRef.current, 5000);
          attemptRef.current += 1;
          reconnectTimeoutRef.current = setTimeout(connect, delay);
        };

        ws.onerror = () => {
          ws.close();
        };
      } catch {
        // Fallback gracioso; a aplicação continuará atualizada via polling TanStack Query
      }
    }

    connect();

    return () => {
      isMounted = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [atendimentoId, token, enabled, onCallReceived, onEvent]);

  return {
    isConnected,
    lastEvent,
    calledEvent,
  };
}

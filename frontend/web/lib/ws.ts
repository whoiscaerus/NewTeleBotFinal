/**
 * WebSocket Client for Real-Time Dashboard
 *
 * Provides WebSocket connection with:
 * - JWT authentication via query parameter
 * - Auto-reconnect with exponential backoff
 * - Message queue for offline buffering
 * - Typed message events
 * - React hook for easy integration
 */

import { useEffect, useState, useCallback, useRef } from 'react';

// Message types from backend
export interface ApprovalsMessage {
  type: 'approvals';
  data: Array<{
    signal_id: string;
    instrument: string;
    side: number; // 0=buy, 1=sell
    price: number;
    volume: number;
    approval_status: number; // 0=pending, 1=approved, 2=rejected
    signal_age_minutes: number;
  }>;
  timestamp: string;
}

export interface PositionsMessage {
  type: 'positions';
  data: Array<{
    position_id: string;
    instrument: string;
    side: number;
    entry_price: number;
    current_price: number;
    unrealized_pnl: number;
    broker_ticket: string;
  }>;
  timestamp: string;
}

export interface EquityMessage {
  type: 'equity';
  data: {
    final_equity: number;
    total_return_percent: number;
    max_drawdown_percent: number;
    equity_curve: Array<{
      date: string;
      equity: number;
    }>;
    days_in_period: number;
  };
  timestamp: string;
}

export interface SignalCreatedMessage {
  type: 'signal_created';
  data: {
    id: string;
    instrument: string;
    side: number;
    price: number;
    status: string;
    created_at: string;
    [key: string]: any;
  };
  timestamp?: string;
}

export type DashboardMessage = ApprovalsMessage | PositionsMessage | EquityMessage | SignalCreatedMessage;

export interface DashboardWebSocketConfig {
  token: string;
  url?: string; // Optional custom WebSocket URL
  onMessage?: (message: DashboardMessage) => void;
  onError?: (error: Error) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
}

export interface DashboardWebSocketState {
  connected: boolean;
  reconnecting: boolean;
  error: Error | null;
  lastMessage: DashboardMessage | null;
  approvals: ApprovalsMessage['data'];
  positions: PositionsMessage['data'];
  equity: EquityMessage['data'] | null;
  latestSignal: SignalCreatedMessage['data'] | null;
}

/**
 * WebSocket client with auto-reconnect
 */
class DashboardWebSocketClient {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private reconnectDelay = 1000; // Start at 1 second
  private maxReconnectDelay = 30000; // Cap at 30 seconds
  private reconnectTimer: NodeJS.Timeout | null = null;
  private messageQueue: DashboardMessage[] = [];
  private config: DashboardWebSocketConfig;
  private isManualClose = false;

  constructor(config: DashboardWebSocketConfig) {
    this.config = config;
  }

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return; // Already connected
    }

    this.isManualClose = false;

    const wsUrl = this.config.url ||
      (typeof window !== 'undefined'
        ? `ws://${window.location.host}/ws`
        : 'ws://localhost:8000/ws');

    const urlWithToken = `${wsUrl}?token=${encodeURIComponent(this.config.token)}`;

    try {
      this.ws = new WebSocket(urlWithToken);

      this.ws.onopen = () => {
        console.log('[Dashboard WS] Connected');
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
        this.config.onConnect?.();

        // Process queued messages
        while (this.messageQueue.length > 0) {
          const msg = this.messageQueue.shift();
          if (msg) {
            this.config.onMessage?.(msg);
          }
        }
      };

      this.ws.onmessage = (event) => {
        try {
          const message: DashboardMessage = JSON.parse(event.data);

          if (this.ws?.readyState === WebSocket.OPEN) {
            this.config.onMessage?.(message);
          } else {
            // Queue messages if not fully connected
            this.messageQueue.push(message);
          }
        } catch (error) {
          console.error('[Dashboard WS] Failed to parse message:', error);
          this.config.onError?.(new Error('Failed to parse WebSocket message'));
        }
      };

      this.ws.onerror = (error) => {
        console.error('[Dashboard WS] Error:', error);
        this.config.onError?.(new Error('WebSocket connection error'));
      };

      this.ws.onclose = (event) => {
        console.log('[Dashboard WS] Disconnected:', event.code, event.reason);
        this.config.onDisconnect?.();

        // Reconnect if not manually closed
        if (!this.isManualClose && this.reconnectAttempts < this.maxReconnectAttempts) {
          this.scheduleReconnect();
        } else if (this.reconnectAttempts >= this.maxReconnectAttempts) {
          const error = new Error('Max reconnect attempts reached');
          this.config.onError?.(error);
        }
      };
    } catch (error) {
      console.error('[Dashboard WS] Connection failed:', error);
      this.config.onError?.(error as Error);
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }

    this.reconnectAttempts++;
    const delay = Math.min(
      this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
      this.maxReconnectDelay
    );

    console.log(`[Dashboard WS] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, delay);
  }

  disconnect() {
    this.isManualClose = true;

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    this.messageQueue = [];
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

/**
 * React hook for dashboard WebSocket
 *
 * @example
 * const { connected, approvals, positions, equity, error } = useDashboardWebSocket(token);
 */
export function useDashboardWebSocket(
  token: string | null,
  options?: Partial<DashboardWebSocketConfig>
): DashboardWebSocketState {
  const [state, setState] = useState<DashboardWebSocketState>({
    connected: false,
    reconnecting: false,
    error: null,
    lastMessage: null,
    approvals: [],
    positions: [],
    equity: null,
    latestSignal: null,
  });

  const clientRef = useRef<DashboardWebSocketClient | null>(null);

  const handleMessage = useCallback((message: DashboardMessage) => {
    setState((prev: DashboardWebSocketState) => {
      const updates: Partial<DashboardWebSocketState> = {
        lastMessage: message,
      };

      switch (message.type) {
        case 'approvals':
          updates.approvals = message.data;
          break;
        case 'positions':
          updates.positions = message.data;
          break;
        case 'equity':
          updates.equity = message.data;
          break;
        case 'signal_created':
          updates.latestSignal = message.data;
          // Optionally append to approvals if it matches the structure,
          // but signal_created structure might differ from approvals list item.
          // For now, we just expose latestSignal.
          break;
      }

      return { ...prev, ...updates };
    });

    options?.onMessage?.(message);
  }, [options]);

  const handleError = useCallback((error: Error) => {
    setState((prev: DashboardWebSocketState) => ({ ...prev, error, reconnecting: false }));
    options?.onError?.(error);
  }, [options]);

  const handleConnect = useCallback(() => {
    setState((prev: DashboardWebSocketState) => ({ ...prev, connected: true, reconnecting: false, error: null }));
    options?.onConnect?.();
  }, [options]);

  const handleDisconnect = useCallback(() => {
    setState((prev: DashboardWebSocketState) => ({ ...prev, connected: false, reconnecting: true }));
    options?.onDisconnect?.();
  }, [options]);

  useEffect(() => {
    if (!token) {
      return;
    }

    const client = new DashboardWebSocketClient({
      token,
      url: options?.url,
      onMessage: handleMessage,
      onError: handleError,
      onConnect: handleConnect,
      onDisconnect: handleDisconnect,
    });

    clientRef.current = client;
    client.connect();

    return () => {
      client.disconnect();
      clientRef.current = null;
    };
  }, [token, options?.url, handleMessage, handleError, handleConnect, handleDisconnect]);

  return state;
}

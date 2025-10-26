"use client";

import React, { useState, useEffect } from "react";
import { useTelegram } from "@/app/_providers/TelegramProvider";
import { apiGet } from "@/lib/api";
import { logger } from "@/lib/logger";

interface PositionData {
  id: string;
  ticket: string;
  instrument: string;
  side: number; // 0=buy, 1=sell
  volume: number;
  entry_price: number;
  current_price: number;
  stop_loss?: number;
  take_profit?: number;
  pnl_points: number;
  pnl_usd: number;
  pnl_percent: number;
  opened_at: string;
}

interface Portfolio {
  account_id: string;
  balance: number;
  equity: number;
  free_margin: number;
  margin_level?: number;
  drawdown_percent: number;
  open_positions_count: number;
  total_pnl_usd: number;
  total_pnl_percent: number;
  positions: PositionData[];
  last_updated: string;
}

/**
 * Mini App Positions Page
 *
 * Displays live trading positions with P&L, equity, and drawdown.
 * Auto-refreshes every 30 seconds.
 *
 * @example
 * Navigate to /positions → see equity chart + positions list
 */
export default function PositionsPage() {
  const { jwt, isLoading: authLoading, error: authError } = useTelegram();
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  // Fetch positions
  const fetchPositions = async (forceRefresh: boolean = false) => {
    if (!jwt) return;

    try {
      setRefreshing(true);
      const params = forceRefresh ? "?force_refresh=true" : "";
      const data = await apiGet<Portfolio>(`/api/v1/positions${params}`, {
        headers: { Authorization: `Bearer ${jwt}` },
      });

      if (data) {
        setPortfolio(data);
        setError(null);
        logger.info("Positions fetched", {
          positions_count: data.open_positions_count,
          equity: data.equity,
        });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to fetch positions";
      setError(message);
      logger.error("Failed to fetch positions", { error: err });
    } finally {
      setRefreshing(false);
      setLoading(false);
    }
  };

  // Set up polling on mount
  useEffect(() => {
    if (!authLoading && jwt) {
      fetchPositions();
      const interval = setInterval(() => fetchPositions(), 30000); // Poll every 30s
      return () => clearInterval(interval);
    }
  }, [authLoading, jwt]);

  // Auth loading
  if (authLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-blue-900 to-blue-800 flex items-center justify-center">
        <div className="text-center text-white">
          <div className="animate-spin rounded-full h-12 w-12 border-4 border-blue-300 border-t-white mx-auto mb-4" />
          <p>Loading positions...</p>
        </div>
      </div>
    );
  }

  // Loading state
  if (loading && !portfolio) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-blue-900 to-blue-800 flex items-center justify-center">
        <div className="text-center text-white">
          <div className="animate-spin rounded-full h-12 w-12 border-4 border-blue-300 border-t-white mx-auto mb-4" />
          <p>Fetching portfolio...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error && !portfolio) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-blue-900 to-blue-800 p-4">
        <div className="max-w-md mx-auto mt-8">
          <div className="bg-red-500 bg-opacity-20 border border-red-400 rounded-lg p-4 text-red-200 mb-4">
            <p className="font-semibold mb-2">Error</p>
            <p className="text-sm">{error}</p>
          </div>
          <button
            onClick={() => fetchPositions(true)}
            className="w-full px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  // Main content
  if (!portfolio) return null;

  const equityTrendColor =
    portfolio.total_pnl_usd >= 0
      ? "text-green-400"
      : "text-red-400";
  const drawdownColor =
    (portfolio.drawdown_percent || 0) > 30
      ? "text-red-400"
      : (portfolio.drawdown_percent || 0) > 15
        ? "text-yellow-400"
        : "text-green-400";

  return (
    <div className="min-h-screen bg-gradient-to-b from-blue-900 to-blue-800 p-4 pb-20">
      <div className="max-w-md mx-auto">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-2xl font-bold text-white">Live Positions</h1>
          <button
            onClick={() => fetchPositions(true)}
            disabled={refreshing}
            className="px-3 py-1 bg-blue-500 text-white text-sm rounded hover:bg-blue-600 disabled:opacity-50 transition-colors"
          >
            {refreshing ? "⟳" : "↻"}
          </button>
        </div>

        {/* Equity Card */}
        <div className="bg-gradient-to-br from-purple-500 to-purple-600 rounded-lg p-4 mb-6 text-white shadow-lg">
          <p className="text-sm text-purple-100 mb-1">Account Equity</p>
          <p className="text-3xl font-bold mb-4">${portfolio.equity.toFixed(2)}</p>

          {/* Stats grid */}
          <div className="grid grid-cols-3 gap-3 mb-4">
            <div className="bg-purple-900 bg-opacity-40 rounded p-2">
              <p className="text-xs text-purple-200">Balance</p>
              <p className="font-semibold text-sm">${portfolio.balance.toFixed(0)}</p>
            </div>
            <div className="bg-purple-900 bg-opacity-40 rounded p-2">
              <p className="text-xs text-purple-200">Free Margin</p>
              <p className="font-semibold text-sm">${portfolio.free_margin.toFixed(0)}</p>
            </div>
            <div className="bg-purple-900 bg-opacity-40 rounded p-2">
              <p className="text-xs text-purple-200">Positions</p>
              <p className="font-semibold text-sm">{portfolio.open_positions_count}</p>
            </div>
          </div>

          {/* P&L */}
          <div className="flex justify-between">
            <div>
              <p className={`text-lg font-bold ${equityTrendColor}`}>
                {portfolio.total_pnl_usd >= 0 ? "+" : ""}${portfolio.total_pnl_usd.toFixed(2)}
              </p>
              <p className="text-xs text-purple-200">Total P&L</p>
            </div>
            <div>
              <p className={`text-lg font-bold ${drawdownColor}`}>
                {portfolio.drawdown_percent.toFixed(2)}%
              </p>
              <p className="text-xs text-purple-200">Drawdown</p>
            </div>
          </div>
        </div>

        {/* Positions List */}
        <div>
          <h2 className="text-lg font-semibold text-white mb-3">Open Positions</h2>

          {portfolio.open_positions_count === 0 ? (
            <div className="bg-blue-900 bg-opacity-30 border border-blue-400 border-opacity-20 rounded-lg p-4 text-center text-gray-300 text-sm">
              No open positions
            </div>
          ) : (
            <div className="space-y-3">
              {portfolio.positions.map((position) => (
                <div
                  key={position.id}
                  data-testid="position-card"
                  className="bg-blue-900 bg-opacity-40 border border-blue-400 border-opacity-30 rounded-lg p-4"
                >
                  {/* Header */}
                  <div className="flex justify-between items-start mb-2">
                    <div>
                      <p className="text-white font-bold">{position.instrument}</p>
                      <p className={`text-xs font-semibold ${
                        position.side === 0 ? "text-green-400" : "text-red-400"
                      }`}>
                        {position.side === 0 ? "📈 BUY" : "📉 SELL"}
                      </p>
                    </div>
                    <p className={`text-lg font-bold ${
                      position.pnl_usd >= 0 ? "text-green-400" : "text-red-400"
                    }`}>
                      {position.pnl_usd >= 0 ? "+" : ""}${position.pnl_usd.toFixed(2)}
                    </p>
                  </div>

                  {/* Price levels */}
                  <div className="bg-blue-800 bg-opacity-40 rounded p-2 mb-3 text-xs text-blue-100 space-y-1">
                    <div className="flex justify-between">
                      <span>Entry:</span>
                      <span className="font-mono">{position.entry_price.toFixed(4)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span>Current:</span>
                      <span className="font-mono font-semibold">{position.current_price.toFixed(4)}</span>
                    </div>
                    {position.stop_loss && (
                      <div className="flex justify-between">
                        <span>SL:</span>
                        <span className="font-mono text-red-300">{position.stop_loss.toFixed(4)}</span>
                      </div>
                    )}
                    {position.take_profit && (
                      <div className="flex justify-between">
                        <span>TP:</span>
                        <span className="font-mono text-green-300">{position.take_profit.toFixed(4)}</span>
                      </div>
                    )}
                  </div>

                  {/* Stats */}
                  <div className="flex justify-between text-xs text-gray-300">
                    <span>
                      {position.volume.toFixed(2)}
                      <span className="text-gray-400 ml-1">lots</span>
                    </span>
                    <span className={position.pnl_percent >= 0 ? "text-green-400" : "text-red-400"}>
                      {position.pnl_percent >= 0 ? "+" : ""}
                      {position.pnl_percent.toFixed(2)}%
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Last updated */}
        <p className="text-center text-xs text-gray-400 mt-8">
          Last updated: {new Date(portfolio.last_updated).toLocaleTimeString()}
        </p>
      </div>
    </div>
  );
}

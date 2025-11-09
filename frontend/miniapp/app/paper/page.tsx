"use client";

import React, { useState, useEffect } from "react";

/**
 * Paper Trading (Sandbox) Mode Page
 *
 * Allows users to test trading strategies without risking real capital.
 * Features: enable/disable toggle, account summary, positions, trade history.
 */

interface PaperAccount {
  id: string;
  balance: number;
  equity: number;
  enabled: boolean;
}

interface PaperPosition {
  id: string;
  symbol: string;
  side: string;
  volume: number;
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
}

interface PaperTrade {
  id: string;
  symbol: string;
  side: string;
  volume: number;
  entry_price: number;
  exit_price: number | null;
  realized_pnl: number | null;
  slippage: number;
  filled_at: string;
  closed_at: string | null;
}

export default function PaperTradingPage() {
  const [account, setAccount] = useState<PaperAccount | null>(null);
  const [positions, setPositions] = useState<PaperPosition[]>([]);
  const [trades, setTrades] = useState<PaperTrade[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [enabling, setEnabling] = useState(false);

  useEffect(() => {
    loadAccount();
  }, []);

  useEffect(() => {
    if (account?.enabled) {
      loadPositions();
      loadTrades();
    }
  }, [account]);

  const loadAccount = async () => {
    try {
      setLoading(true);
      const response = await fetch("/api/v1/paper/account");
      if (response.ok) {
        const data = await response.json();
        setAccount(data);
      } else if (response.status === 404) {
        setAccount(null);
      } else {
        setError("Failed to load account");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load account");
    } finally {
      setLoading(false);
    }
  };

  const loadPositions = async () => {
    try {
      const response = await fetch("/api/v1/paper/positions");
      if (response.ok) {
        const data = await response.json();
        setPositions(data);
      }
    } catch (err) {
      console.error("Failed to load positions:", err);
    }
  };

  const loadTrades = async () => {
    try {
      const response = await fetch("/api/v1/paper/trades");
      if (response.ok) {
        const data = await response.json();
        setTrades(data);
      }
    } catch (err) {
      console.error("Failed to load trades:", err);
    }
  };

  const handleEnable = async () => {
    try {
      setEnabling(true);
      setError(null);
      const response = await fetch("/api/v1/paper/enable", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ initial_balance: 10000 }),
      });

      if (response.ok) {
        const data = await response.json();
        setAccount(data);
      } else {
        const errorData = await response.json();
        setError(errorData.detail || "Failed to enable paper trading");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to enable paper trading");
    } finally {
      setEnabling(false);
    }
  };

  const handleDisable = async () => {
    if (!confirm("Are you sure you want to disable paper trading? Your account will be preserved.")) {
      return;
    }

    try {
      setEnabling(true);
      setError(null);
      const response = await fetch("/api/v1/paper/disable", {
        method: "POST",
      });

      if (response.ok) {
        const data = await response.json();
        setAccount(data);
      } else {
        const errorData = await response.json();
        setError(errorData.detail || "Failed to disable paper trading");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to disable paper trading");
    } finally {
      setEnabling(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 p-6">
        <div className="max-w-6xl mx-auto">
          <h1 className="text-3xl font-bold mb-6">Paper Trading (Sandbox)</h1>
          <div className="text-gray-500">Loading...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-6xl mx-auto">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-3xl font-bold">Paper Trading (Sandbox)</h1>
          {account?.enabled && (
            <div className="flex items-center gap-2">
              <span className="inline-block px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm font-medium">
                📊 Paper Mode Active
              </span>
            </div>
          )}
        </div>

        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-800">
            {error}
          </div>
        )}

        {!account && (
          <div className="bg-white rounded-lg shadow p-8 text-center">
            <h2 className="text-2xl font-semibold mb-4">Welcome to Paper Trading</h2>
            <p className="text-gray-600 mb-6 max-w-2xl mx-auto">
              Test trading strategies without risking real capital. Paper trading simulates
              order execution with realistic fills and slippage.
            </p>
            <button
              onClick={handleEnable}
              disabled={enabling}
              className="px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50"
            >
              {enabling ? "Enabling..." : "Enable Paper Trading"}
            </button>
          </div>
        )}

        {account && !account.enabled && (
          <div className="bg-white rounded-lg shadow p-8 text-center">
            <h2 className="text-2xl font-semibold mb-4">Paper Trading Disabled</h2>
            <p className="text-gray-600 mb-6">
              Your paper account is preserved. Re-enable to continue testing.
            </p>
            <button
              onClick={handleEnable}
              disabled={enabling}
              className="px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50"
            >
              {enabling ? "Enabling..." : "Re-enable Paper Trading"}
            </button>
          </div>
        )}

        {account && account.enabled && (
          <>
            {/* Account Summary */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
              <div className="bg-white rounded-lg shadow p-6">
                <h3 className="text-sm font-medium text-gray-500 mb-2">Balance</h3>
                <p className="text-2xl font-bold">${account.balance.toFixed(2)}</p>
              </div>
              <div className="bg-white rounded-lg shadow p-6">
                <h3 className="text-sm font-medium text-gray-500 mb-2">Equity</h3>
                <p className="text-2xl font-bold">${account.equity.toFixed(2)}</p>
              </div>
              <div className="bg-white rounded-lg shadow p-6">
                <h3 className="text-sm font-medium text-gray-500 mb-2">Unrealized PnL</h3>
                <p className={`text-2xl font-bold ${
                  account.equity - account.balance >= 0 ? "text-green-600" : "text-red-600"
                }`}>
                  ${(account.equity - account.balance).toFixed(2)}
                </p>
              </div>
            </div>

            {/* Open Positions */}
            <div className="bg-white rounded-lg shadow mb-6">
              <div className="p-6 border-b">
                <h2 className="text-xl font-semibold">Open Positions</h2>
              </div>
              <div className="overflow-x-auto">
                {positions.length === 0 ? (
                  <p className="p-6 text-gray-500 text-center">No open positions</p>
                ) : (
                  <table className="w-full">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Symbol</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Side</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Volume</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Entry</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Current</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">PnL</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200">
                      {positions.map((pos) => (
                        <tr key={pos.id}>
                          <td className="px-6 py-4 font-medium">{pos.symbol}</td>
                          <td className="px-6 py-4">
                            <span className={`inline-block px-2 py-1 rounded text-xs font-medium ${
                              pos.side === "buy" ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"
                            }`}>
                              {pos.side.toUpperCase()}
                            </span>
                          </td>
                          <td className="px-6 py-4">{pos.volume}</td>
                          <td className="px-6 py-4">${pos.entry_price.toFixed(2)}</td>
                          <td className="px-6 py-4">${pos.current_price.toFixed(2)}</td>
                          <td className={`px-6 py-4 font-medium ${
                            pos.unrealized_pnl >= 0 ? "text-green-600" : "text-red-600"
                          }`}>
                            ${pos.unrealized_pnl.toFixed(2)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>

            {/* Trade History */}
            <div className="bg-white rounded-lg shadow mb-6">
              <div className="p-6 border-b">
                <h2 className="text-xl font-semibold">Trade History</h2>
              </div>
              <div className="overflow-x-auto">
                {trades.length === 0 ? (
                  <p className="p-6 text-gray-500 text-center">No trade history</p>
                ) : (
                  <table className="w-full">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Symbol</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Side</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Volume</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Entry</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Exit</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">PnL</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Filled</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200">
                      {trades.map((trade) => (
                        <tr key={trade.id}>
                          <td className="px-6 py-4 font-medium">{trade.symbol}</td>
                          <td className="px-6 py-4">
                            <span className={`inline-block px-2 py-1 rounded text-xs font-medium ${
                              trade.side === "buy" ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"
                            }`}>
                              {trade.side.toUpperCase()}
                            </span>
                          </td>
                          <td className="px-6 py-4">{trade.volume}</td>
                          <td className="px-6 py-4">${trade.entry_price.toFixed(2)}</td>
                          <td className="px-6 py-4">
                            {trade.exit_price ? `$${trade.exit_price.toFixed(2)}` : "-"}
                          </td>
                          <td className={`px-6 py-4 font-medium ${
                            trade.realized_pnl !== null && trade.realized_pnl >= 0
                              ? "text-green-600"
                              : "text-red-600"
                          }`}>
                            {trade.realized_pnl !== null ? `$${trade.realized_pnl.toFixed(2)}` : "-"}
                          </td>
                          <td className="px-6 py-4 text-sm text-gray-500">
                            {new Date(trade.filled_at).toLocaleDateString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>

            {/* Controls */}
            <div className="flex justify-end">
              <button
                onClick={handleDisable}
                disabled={enabling}
                className="px-6 py-3 bg-gray-200 text-gray-800 rounded-lg font-medium hover:bg-gray-300 disabled:opacity-50"
              >
                {enabling ? "Processing..." : "Disable Paper Trading"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

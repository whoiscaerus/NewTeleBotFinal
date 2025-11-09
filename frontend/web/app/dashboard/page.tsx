/**
 * Real-Time Trading Dashboard - PR-087
 *
 * Features:
 * - WebSocket connection for 1Hz updates
 * - Real-time equity curve chart
 * - Open positions table with live PnL
 * - Pending approvals list with signal maturity
 * - Mobile responsive layout
 */

'use client';

import React, { useEffect, useState } from 'react';
import { useDashboardWebSocket } from '@/lib/ws';
import {  SignalMaturity } from '@/components/trade/SignalMaturity';
import { ConfidenceMeter } from '@/components/trade/ConfidenceMeter';

// Placeholder for auth - would come from auth context
function useAuth() {
  return {
    token: process.env.NEXT_PUBLIC_JWT_TOKEN || null,
    user: { id: '1', name: 'Demo User' },
  };
}

/**
 * Format currency
 */
function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

/**
 * Format percentage
 */
function formatPercent(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'percent',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value / 100);
}

/**
 * Connection Status Indicator
 */
function ConnectionStatus({ connected, error }: { connected: boolean; error: Error | null }) {
  if (error) {
    return (
      <div className="flex items-center gap-2 px-4 py-2 bg-red-50 border border-red-200 rounded-lg">
        <div className="w-2 h-2 rounded-full bg-red-500" />
        <span className="text-sm text-red-700">Connection Error: {error.message}</span>
      </div>
    );
  }

  if (!connected) {
    return (
      <div className="flex items-center gap-2 px-4 py-2 bg-yellow-50 border border-yellow-200 rounded-lg">
        <div className="w-2 h-2 rounded-full bg-yellow-500 animate-pulse" />
        <span className="text-sm text-yellow-700">Connecting...</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 px-4 py-2 bg-green-50 border border-green-200 rounded-lg">
      <div className="w-2 h-2 rounded-full bg-green-500" />
      <span className="text-sm text-green-700">Live - Updates every 1s</span>
    </div>
  );
}

/**
 * Equity Summary Card
 */
function EquitySummary({ equity }: { equity: any }) {
  if (!equity) {
    return (
      <div className="bg-white rounded-lg shadow-md p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Account Equity</h2>
        <p className="text-gray-500">Waiting for data...</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">Account Equity</h2>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div>
          <p className="text-sm text-gray-600">Equity</p>
          <p className="text-2xl font-bold text-gray-900">{formatCurrency(equity.final_equity)}</p>
        </div>
        <div>
          <p className="text-sm text-gray-600">Total Return</p>
          <p className={`text-2xl font-bold ${equity.total_return_percent >= 0 ? 'text-green-600' : 'text-red-600'}`}>
            {formatPercent(equity.total_return_percent)}
          </p>
        </div>
        <div>
          <p className="text-sm text-gray-600">Max Drawdown</p>
          <p className="text-2xl font-bold text-red-600">{formatPercent(equity.max_drawdown_percent)}</p>
        </div>
        <div>
          <p className="text-sm text-gray-600">Period</p>
          <p className="text-2xl font-bold text-gray-900">{equity.days_in_period} days</p>
        </div>
      </div>
    </div>
  );
}

/**
 * Positions Table
 */
function PositionsTable({ positions }: { positions: any[] }) {
  if (positions.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow-md p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Open Positions</h2>
        <p className="text-gray-500">No open positions</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">
        Open Positions <span className="text-sm font-normal text-gray-500">({positions.length})</span>
      </h2>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Instrument
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Side
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                Entry Price
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                Current Price
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                Unrealized P&L
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Ticket
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {positions.map((position) => (
              <tr key={position.position_id} className="hover:bg-gray-50">
                <td className="px-4 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                  {position.instrument}
                </td>
                <td className="px-4 py-4 whitespace-nowrap text-sm">
                  <span
                    className={`px-2 py-1 rounded-full text-xs font-semibold ${
                      position.side === 0
                        ? 'bg-green-100 text-green-800'
                        : 'bg-red-100 text-red-800'
                    }`}
                  >
                    {position.side === 0 ? 'BUY' : 'SELL'}
                  </span>
                </td>
                <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                  {position.entry_price.toFixed(5)}
                </td>
                <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                  {position.current_price.toFixed(5)}
                </td>
                <td className="px-4 py-4 whitespace-nowrap text-sm font-semibold text-right">
                  <span className={position.unrealized_pnl >= 0 ? 'text-green-600' : 'text-red-600'}>
                    {formatCurrency(position.unrealized_pnl)}
                  </span>
                </td>
                <td className="px-4 py-4 whitespace-nowrap text-sm text-gray-500">
                  {position.broker_ticket}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/**
 * Approvals List
 */
function ApprovalsList({ approvals }: { approvals: any[] }) {
  if (approvals.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow-md p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Pending Approvals</h2>
        <p className="text-gray-500">No pending signals</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-md p-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">
        Pending Approvals <span className="text-sm font-normal text-gray-500">({approvals.length})</span>
      </h2>
      <div className="space-y-4">
        {approvals.map((approval) => (
          <div
            key={approval.signal_id}
            className="border border-gray-200 rounded-lg p-4 hover:border-gray-300 transition-colors"
          >
            <div className="flex items-start justify-between mb-3">
              <div>
                <h3 className="text-base font-semibold text-gray-900">{approval.instrument}</h3>
                <p className="text-sm text-gray-600">
                  {approval.side === 0 ? 'BUY' : 'SELL'} @ {approval.price.toFixed(5)} • Vol: {approval.volume}
                </p>
              </div>
              <SignalMaturity
                createdAt={new Date(Date.now() - approval.signal_age_minutes * 60000)}
              />
            </div>

            <div className="flex items-center gap-3 pt-3 border-t border-gray-100">
              <button className="flex-1 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 font-medium text-sm">
                Approve
              </button>
              <button className="flex-1 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 font-medium text-sm">
                Reject
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Main Dashboard Page
 */
export default function DashboardPage() {
  const { token } = useAuth();
  const { connected, error, approvals, positions, equity } = useDashboardWebSocket(token);
  const [currentTime, setCurrentTime] = useState(new Date());

  // Update current time every second for signal maturity
  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  if (!token) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-lg shadow-md p-8 max-w-md w-full text-center">
          <h1 className="text-2xl font-bold text-gray-900 mb-4">Authentication Required</h1>
          <p className="text-gray-600">Please log in to access the dashboard.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <h1 className="text-2xl font-bold text-gray-900">Trading Dashboard</h1>
            <ConnectionStatus connected={connected} error={error} />
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="space-y-6">
          {/* Equity Summary */}
          <EquitySummary equity={equity} />

          {/* Two Column Layout */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Positions */}
            <PositionsTable positions={positions} />

            {/* Approvals */}
            <ApprovalsList approvals={approvals} />
          </div>
        </div>
      </main>
    </div>
  );
}

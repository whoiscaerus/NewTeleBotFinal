'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { AlertCircle, Plus, Trash2, Eye, EyeOff } from 'lucide-react';
import { useRouter } from 'next/navigation';

interface Alert {
  alert_id: string;
  symbol: string;
  operator: 'above' | 'below';
  price_level: number;
  is_active: boolean;
  last_triggered?: string | null;
  created_at?: string;
}

interface AlertCreateForm {
  symbol: string;
  operator: 'above' | 'below';
  price_level: string;
}

const VALID_SYMBOLS = [
  'XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD',
  'NZDUSD', 'USDCAD', 'USDCHF', 'GOLD', 'SILVER',
  'CRUDE', 'NATGAS', 'DXUSD', 'SP500', 'NASDQ100'
];

/**
 * Price Alerts Management Page
 *
 * Allows users to:
 * - Create price alerts for specific instruments
 * - View all their active and inactive alerts
 * - Delete alerts they no longer want
 * - See when alerts were last triggered
 *
 * Features:
 * - Form validation (symbol, operator, price)
 * - Real-time alert list updates
 * - Error handling with toast notifications
 * - Responsive design for mobile/desktop
 */
export default function AlertsPage() {
  const router = useRouter();
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  const [formData, setFormData] = useState<AlertCreateForm>({
    symbol: 'XAUUSD',
    operator: 'above',
    price_level: '',
  });

  // Fetch alerts on component mount
  useEffect(() => {
    loadAlerts();
  }, []);

  // Auto-dismiss success message
  useEffect(() => {
    if (success) {
      const timer = setTimeout(() => setSuccess(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [success]);

  const loadAlerts = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await fetch('/api/v1/alerts', {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        if (response.status === 401) {
          router.push('/login');
          return;
        }
        throw new Error(`Failed to load alerts: ${response.statusText}`);
      }

      const data: Alert[] = await response.json();
      setAlerts(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load alerts';
      setError(message);
      console.error('Error loading alerts:', err);
    } finally {
      setLoading(false);
    }
  }, [router]);

  const handleCreateAlert = async (e: React.FormEvent) => {
    e.preventDefault();

    // Validate form
    if (!formData.symbol || !formData.price_level) {
      setError('Please fill in all fields');
      return;
    }

    const priceLevel = parseFloat(formData.price_level);
    if (isNaN(priceLevel) || priceLevel <= 0 || priceLevel >= 1000000) {
      setError('Price must be between 0 and 1,000,000');
      return;
    }

    try {
      setError(null);

      const response = await fetch('/api/v1/alerts', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          symbol: formData.symbol,
          operator: formData.operator,
          price_level: priceLevel,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
        const errorMessage = errorData.detail || `Error creating alert: ${response.statusText}`;
        setError(errorMessage);
        return;
      }

      const newAlert: Alert = await response.json();
      setAlerts((prev) => [...prev, newAlert]);
      setSuccess(`Alert created: ${formData.symbol} ${formData.operator} $${priceLevel.toFixed(2)}`);

      // Reset form
      setFormData({
        symbol: 'XAUUSD',
        operator: 'above',
        price_level: '',
      });
      setShowForm(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create alert';
      setError(message);
      console.error('Error creating alert:', err);
    }
  };

  const handleDeleteAlert = async (alertId: string) => {
    if (!window.confirm('Are you sure you want to delete this alert?')) {
      return;
    }

    try {
      setDeleting(alertId);
      setError(null);

      const response = await fetch(`/api/v1/alerts/${alertId}`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to delete alert: ${response.statusText}`);
      }

      setAlerts((prev) => prev.filter((a) => a.alert_id !== alertId));
      setSuccess('Alert deleted successfully');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete alert';
      setError(message);
      console.error('Error deleting alert:', err);
    } finally {
      setDeleting(null);
    }
  };

  const formatPrice = (price: number): string => {
    return price.toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  };

  const formatDate = (dateString: string | null | undefined): string => {
    if (!dateString) return 'Never';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 to-slate-800 py-8 px-4">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-4xl font-bold text-white mb-2">Price Alerts</h1>
            <p className="text-slate-400">Get notified when prices reach your target levels</p>
          </div>
          <button
            onClick={() => setShowForm(!showForm)}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg font-medium transition"
          >
            <Plus size={20} />
            Create Alert
          </button>
        </div>

        {/* Toast Messages */}
        {error && (
          <div className="mb-6 p-4 bg-red-900/30 border border-red-700 rounded-lg flex items-start gap-3">
            <AlertCircle className="text-red-500 mt-0.5" size={20} />
            <div className="flex-1">
              <p className="text-red-200 font-medium">Error</p>
              <p className="text-red-100 text-sm">{error}</p>
            </div>
          </div>
        )}

        {success && (
          <div className="mb-6 p-4 bg-green-900/30 border border-green-700 rounded-lg">
            <p className="text-green-200">✓ {success}</p>
          </div>
        )}

        {/* Create Alert Form */}
        {showForm && (
          <div className="mb-8 bg-slate-800 border border-slate-700 rounded-lg p-6">
            <h2 className="text-2xl font-bold text-white mb-6">New Price Alert</h2>

            <form onSubmit={handleCreateAlert} className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Symbol Select */}
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">
                    Symbol
                  </label>
                  <select
                    value={formData.symbol}
                    onChange={(e) =>
                      setFormData((prev) => ({ ...prev, symbol: e.target.value }))
                    }
                    className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  >
                    {VALID_SYMBOLS.map((symbol) => (
                      <option key={symbol} value={symbol}>
                        {symbol}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Operator Select */}
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">
                    Condition
                  </label>
                  <select
                    value={formData.operator}
                    onChange={(e) =>
                      setFormData((prev) => ({
                        ...prev,
                        operator: e.target.value as 'above' | 'below',
                      }))
                    }
                    className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  >
                    <option value="above">Above</option>
                    <option value="below">Below</option>
                  </select>
                </div>

                {/* Price Input */}
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">
                    Price Level
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    min="0.01"
                    max="999999.99"
                    value={formData.price_level}
                    onChange={(e) =>
                      setFormData((prev) => ({
                        ...prev,
                        price_level: e.target.value,
                      }))
                    }
                    placeholder="Enter price level"
                    className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                </div>
              </div>

              {/* Form Actions */}
              <div className="flex gap-3">
                <button
                  type="submit"
                  className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition"
                >
                  Create Alert
                </button>
                <button
                  type="button"
                  onClick={() => setShowForm(false)}
                  className="px-6 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg font-medium transition"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Alerts List */}
        {loading ? (
          <div className="text-center py-12">
            <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
            <p className="text-slate-400 mt-4">Loading alerts...</p>
          </div>
        ) : alerts.length === 0 ? (
          <div className="text-center py-12 bg-slate-800 border border-slate-700 rounded-lg">
            <AlertCircle size={48} className="mx-auto text-slate-500 mb-4" />
            <p className="text-slate-300 text-lg">No alerts yet</p>
            <p className="text-slate-400 text-sm">Create your first price alert to get started</p>
          </div>
        ) : (
          <div className="grid gap-4">
            {alerts.map((alert) => (
              <div
                key={alert.alert_id}
                className={`p-4 border rounded-lg transition ${
                  alert.is_active
                    ? 'bg-slate-800 border-slate-700 hover:border-slate-600'
                    : 'bg-slate-900 border-slate-700 opacity-60'
                }`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    {/* Alert Summary */}
                    <div className="flex items-center gap-4 mb-2">
                      <div className="flex items-baseline gap-2">
                        <span className="text-xl font-bold text-white">
                          {alert.symbol}
                        </span>
                        <span className="text-sm font-medium text-blue-400">
                          {alert.operator === 'above' ? '↑' : '↓'}
                        </span>
                        <span className="text-lg text-slate-300">
                          ${formatPrice(alert.price_level)}
                        </span>
                      </div>

                      {/* Status Badge */}
                      {alert.is_active ? (
                        <span className="inline-flex items-center gap-1 px-2 py-1 bg-green-900/30 border border-green-700 rounded text-green-200 text-xs font-medium">
                          <span className="w-2 h-2 bg-green-500 rounded-full" />
                          Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-1 bg-slate-700 border border-slate-600 rounded text-slate-300 text-xs font-medium">
                          <span className="w-2 h-2 bg-slate-500 rounded-full" />
                          Inactive
                        </span>
                      )}
                    </div>

                    {/* Alert Details */}
                    <div className="flex gap-6 text-sm text-slate-400">
                      <div>
                        <p className="text-xs text-slate-500 uppercase">Created</p>
                        <p className="text-slate-300">{formatDate(alert.created_at)}</p>
                      </div>
                      {alert.last_triggered && (
                        <div>
                          <p className="text-xs text-slate-500 uppercase">Last Triggered</p>
                          <p className="text-yellow-300">{formatDate(alert.last_triggered)}</p>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex gap-2 ml-4">
                    <button
                      onClick={() => handleDeleteAlert(alert.alert_id)}
                      disabled={deleting === alert.alert_id}
                      className="p-2 hover:bg-red-900/30 text-red-400 hover:text-red-300 rounded transition disabled:opacity-50"
                      title="Delete alert"
                    >
                      {deleting === alert.alert_id ? (
                        <div className="w-5 h-5 animate-spin rounded-full border-2 border-red-400 border-t-transparent" />
                      ) : (
                        <Trash2 size={20} />
                      )}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Stats Footer */}
        {alerts.length > 0 && (
          <div className="mt-8 grid grid-cols-3 gap-4 text-center">
            <div className="p-4 bg-slate-800 border border-slate-700 rounded-lg">
              <p className="text-slate-400 text-sm">Total Alerts</p>
              <p className="text-2xl font-bold text-white">{alerts.length}</p>
            </div>
            <div className="p-4 bg-slate-800 border border-slate-700 rounded-lg">
              <p className="text-slate-400 text-sm">Active</p>
              <p className="text-2xl font-bold text-green-400">
                {alerts.filter((a) => a.is_active).length}
              </p>
            </div>
            <div className="p-4 bg-slate-800 border border-slate-700 rounded-lg">
              <p className="text-slate-400 text-sm">Triggered</p>
              <p className="text-2xl font-bold text-yellow-400">
                {alerts.filter((a) => a.last_triggered).length}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

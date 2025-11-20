"use client";

import React, { useState } from 'react';
import { Check, X, AlertCircle, Loader2 } from 'lucide-react'; // Assuming lucide-react is available or use generic icons

interface Signal {
  id: string;
  instrument: string;
  side: number; // 0=buy, 1=sell
  price: number;
  timestamp: string;
}

interface ApprovalCardProps {
  signal: Signal;
  onApprove: (id: string) => Promise<void>;
  onReject: (id: string) => Promise<void>;
}

export const ApprovalCard: React.FC<ApprovalCardProps> = ({ signal, onApprove, onReject }) => {
  const [status, setStatus] = useState<'idle' | 'approving' | 'rejecting' | 'approved' | 'rejected' | 'error'>('idle');

  const handleApprove = async () => {
    // Optimistic Update
    setStatus('approved');

    try {
      await onApprove(signal.id);
      // Keep 'approved' state
    } catch (error) {
      // Revert on failure
      setStatus('error');
      setTimeout(() => setStatus('idle'), 3000);
    }
  };

  const handleReject = async () => {
    setStatus('rejected');
    try {
      await onReject(signal.id);
    } catch (error) {
      setStatus('error');
      setTimeout(() => setStatus('idle'), 3000);
    }
  };

  if (status === 'approved') {
    return (
      <div className="bg-green-900/20 border border-green-500/50 rounded-lg p-4 flex items-center justify-between animate-in fade-in zoom-in duration-300">
        <div className="flex items-center gap-2 text-green-400">
          <Check className="w-5 h-5" />
          <span className="font-medium">Signal Approved</span>
        </div>
      </div>
    );
  }

  if (status === 'rejected') {
    return (
      <div className="bg-red-900/20 border border-red-500/50 rounded-lg p-4 flex items-center justify-between animate-in fade-in zoom-in duration-300">
        <div className="flex items-center gap-2 text-red-400">
          <X className="w-5 h-5" />
          <span className="font-medium">Signal Rejected</span>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-[#111] border border-gray-800 rounded-lg p-4 hover:border-gray-700 transition-colors">
      <div className="flex justify-between items-start mb-4">
        <div>
          <h3 className="text-lg font-bold text-white">{signal.instrument}</h3>
          <span className={`text-sm font-mono px-2 py-0.5 rounded ${signal.side === 0 ? 'bg-green-900 text-green-400' : 'bg-red-900 text-red-400'}`}>
            {signal.side === 0 ? 'BUY' : 'SELL'} @ {signal.price}
          </span>
        </div>
        <div className="text-xs text-gray-500">
          {new Date(signal.timestamp).toLocaleTimeString()}
        </div>
      </div>

      {status === 'error' && (
        <div className="mb-3 text-sm text-red-400 flex items-center gap-1">
          <AlertCircle className="w-4 h-4" />
          Action failed. Retrying...
        </div>
      )}

      <div className="flex gap-3">
        <button
          onClick={handleApprove}
          disabled={status !== 'idle'}
          className="flex-1 bg-green-600 hover:bg-green-500 disabled:opacity-50 text-white py-2 rounded-md font-medium transition-all active:scale-95 flex justify-center items-center gap-2"
        >
          {status === 'approving' ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Approve'}
        </button>
        <button
          onClick={handleReject}
          disabled={status !== 'idle'}
          className="flex-1 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 text-gray-300 py-2 rounded-md font-medium transition-all active:scale-95 flex justify-center items-center gap-2"
        >
          {status === 'rejecting' ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Reject'}
        </button>
      </div>
    </div>
  );
};

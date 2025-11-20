"use client";

import React from 'react';
import { Activity, CheckCircle, AlertTriangle, Send, Server } from 'lucide-react';

interface AuditLogEntry {
  id: string;
  action: string;
  status: 'success' | 'failure' | 'pending';
  timestamp: string;
  details: string;
}

interface AuditLogFeedProps {
  logs: AuditLogEntry[];
}

export const AuditLogFeed: React.FC<AuditLogFeedProps> = ({ logs }) => {
  return (
    <div className="bg-[#0d0d0d] border border-gray-800 rounded-lg p-4">
      <h3 className="text-sm font-semibold text-gray-400 mb-4 flex items-center gap-2">
        <Activity className="w-4 h-4" />
        Activity Feed
      </h3>

      <div className="space-y-6 relative before:absolute before:inset-0 before:ml-5 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-gray-800 before:to-transparent">
        {logs.map((log, index) => (
          <div key={log.id} className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active">

            {/* Icon */}
            <div className="flex items-center justify-center w-10 h-10 rounded-full border border-gray-800 bg-[#111] shadow shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 z-10">
              {log.status === 'success' && <CheckCircle className="w-5 h-5 text-green-500" />}
              {log.status === 'failure' && <AlertTriangle className="w-5 h-5 text-red-500" />}
              {log.status === 'pending' && <Server className="w-5 h-5 text-blue-500" />}
            </div>

            {/* Content */}
            <div className="w-[calc(100%-4rem)] md:w-[calc(50%-2.5rem)] bg-[#161616] p-4 rounded-lg border border-gray-800 shadow-sm">
              <div className="flex items-center justify-between space-x-2 mb-1">
                <div className="font-bold text-gray-200">{log.action}</div>
                <time className="font-mono text-xs text-gray-500">{new Date(log.timestamp).toLocaleTimeString()}</time>
              </div>
              <div className="text-gray-400 text-sm">
                {log.details}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

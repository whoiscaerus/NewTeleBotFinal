"use client";

import React, { useState, useEffect } from "react";
import { apiGet } from "@/lib/api";
import { logger } from "@/lib/logger";

interface Invoice {
  id: string;
  amount_paid: number; // Amount in cents
  amount_due: number; // Amount due in cents
  status: "paid" | "past_due" | "draft" | "canceled";
  created: number; // Unix timestamp
  pdf_url: string; // PDF download URL
  description: string; // Invoice description (e.g., "Premium Plan - Monthly")
}

interface InvoiceListProps {
  jwt: string;
}

/**
 * InvoiceList Component
 *
 * Displays user's invoice history with status badges and download links.
 * Shows paid, pending, and past due invoices with amounts and dates.
 *
 * Features:
 * - Status badges (paid/past_due/canceled/draft)
 * - Amount formatting in GBP
 * - PDF download links
 * - Date formatting
 * - Loading and error states
 *
 * @example
 * <InvoiceList jwt={token} />
 */
export const InvoiceList: React.FC<InvoiceListProps> = ({ jwt }) => {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadInvoices();
  }, [jwt]);

  const loadInvoices = async () => {
    if (!jwt) return;

    try {
      setLoading(true);
      const data = await apiGet<Invoice[]>("/api/v1/billing/invoices");

      setInvoices(data || []);
      setError(null);

      logger.info("Invoices loaded", {
        invoice_count: data?.length || 0,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load invoices";
      setError(message);
      logger.error("Failed to load invoices", { error: err });
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-3">
        <div className="h-16 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
        <div className="h-16 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
        <div className="h-16 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
        <p className="text-red-700 dark:text-red-200 text-sm">{error}</p>
        <button
          onClick={loadInvoices}
          className="mt-2 text-sm text-red-600 dark:text-red-400 hover:underline"
        >
          Try again
        </button>
      </div>
    );
  }

  if (invoices.length === 0) {
    return (
      <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4 text-center">
        <p className="text-gray-600 dark:text-gray-400 text-sm">No invoices yet</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {invoices.map((invoice) => (
        <InvoiceCard key={invoice.id} invoice={invoice} />
      ))}
    </div>
  );
};

interface InvoiceCardProps {
  invoice: Invoice;
}

/**
 * Individual invoice card component
 * Displays invoice details with status badge and download link
 */
const InvoiceCard: React.FC<InvoiceCardProps> = ({ invoice }) => {
  const formatDate = (timestamp: number): string => {
    const date = new Date(timestamp * 1000);
    return date.toLocaleDateString("en-GB", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  };

  const formatAmount = (cents: number): string => {
    // Convert cents to GBP
    const gbp = (cents / 100).toFixed(2);
    return `£${gbp}`;
  };

  const getStatusBadge = (status: string) => {
    const statusStyles: Record<string, { bg: string; text: string; label: string }> = {
      paid: {
        bg: "bg-green-100 dark:bg-green-900/30",
        text: "text-green-800 dark:text-green-300",
        label: "Paid",
      },
      past_due: {
        bg: "bg-yellow-100 dark:bg-yellow-900/30",
        text: "text-yellow-800 dark:text-yellow-300",
        label: "Past Due",
      },
      draft: {
        bg: "bg-gray-100 dark:bg-gray-700",
        text: "text-gray-800 dark:text-gray-300",
        label: "Draft",
      },
      canceled: {
        bg: "bg-red-100 dark:bg-red-900/30",
        text: "text-red-800 dark:text-red-300",
        label: "Canceled",
      },
    };

    const style = statusStyles[status] || statusStyles.draft;

    return (
      <span className={`px-2 py-1 rounded text-xs font-medium ${style.bg} ${style.text}`}>
        {style.label}
      </span>
    );
  };

  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:bg-gray-50 dark:hover:bg-gray-800 transition">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
              {invoice.description}
            </h3>
            {getStatusBadge(invoice.status)}
          </div>
          <p className="text-xs text-gray-600 dark:text-gray-400">
            {formatDate(invoice.created)}
          </p>
        </div>

        <div className="text-right">
          <p className="text-sm font-semibold text-gray-900 dark:text-white">
            {formatAmount(invoice.amount_paid || invoice.amount_due)}
          </p>
          {invoice.pdf_url && (
            <a
              href={invoice.pdf_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-blue-600 dark:text-blue-400 hover:underline mt-1 block"
            >
              Download PDF
            </a>
          )}
        </div>
      </div>
    </div>
  );
};

export default InvoiceList;

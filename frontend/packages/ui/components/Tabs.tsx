"use client";

import React, { useState } from "react";
import clsx from "clsx";

export interface Tab {
  id: string;
  label: string;
  content: React.ReactNode;
  disabled?: boolean;
}

export interface TabsProps {
  tabs: Tab[];
  defaultActiveId?: string;
  onChange?: (tabId: string) => void;
  variant?: "default" | "pills" | "underline";
  className?: string;
}

/**
 * Tabs component - Tabbed navigation interface
 * Used for trading dashboard sections, settings panels
 */
export const Tabs: React.FC<TabsProps> = ({
  tabs,
  defaultActiveId,
  onChange,
  variant = "default",
  className,
}) => {
  const [activeId, setActiveId] = useState(defaultActiveId || tabs[0]?.id || "");

  const handleTabClick = (tabId: string, disabled?: boolean) => {
    if (disabled) return;
    setActiveId(tabId);
    onChange?.(tabId);
  };

  const baseTabStyles = "px-4 py-2 font-medium transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500";

  const variantStyles = {
    default: {
      container: "border-b border-gray-200 dark:border-gray-700",
      tab: "border-b-2 -mb-px",
      active: "border-blue-600 text-blue-600 dark:text-blue-400",
      inactive: "border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 hover:border-gray-300",
    },
    pills: {
      container: "bg-gray-100 dark:bg-gray-800 rounded-lg p-1 gap-1",
      tab: "rounded-md",
      active: "bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm",
      inactive: "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200",
    },
    underline: {
      container: "gap-4",
      tab: "border-b-2",
      active: "border-blue-600 text-blue-600 dark:text-blue-400",
      inactive: "border-transparent text-gray-600 dark:text-gray-400 hover:border-gray-300",
    },
  };

  const currentVariant = variantStyles[variant];

  return (
    <div className={className}>
      {/* Tab Headers */}
      <div className={clsx("flex", currentVariant.container)}>
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => handleTabClick(tab.id, tab.disabled)}
            className={clsx(
              baseTabStyles,
              currentVariant.tab,
              activeId === tab.id ? currentVariant.active : currentVariant.inactive,
              tab.disabled && "opacity-50 cursor-not-allowed"
            )}
            disabled={tab.disabled}
            role="tab"
            aria-selected={activeId === tab.id}
            aria-controls={`panel-${tab.id}`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="mt-4">
        {tabs.map((tab) => (
          <div
            key={tab.id}
            id={`panel-${tab.id}`}
            role="tabpanel"
            hidden={activeId !== tab.id}
            className={clsx(
              "transition-opacity duration-200",
              activeId === tab.id ? "opacity-100" : "opacity-0 h-0 overflow-hidden"
            )}
          >
            {tab.content}
          </div>
        ))}
      </div>
    </div>
  );
};

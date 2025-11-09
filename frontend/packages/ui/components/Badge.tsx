import React from "react";
import clsx from "clsx";

export interface BadgeProps {
  children: React.ReactNode;
  variant?: "default" | "success" | "warning" | "error" | "info";
  size?: "sm" | "md" | "lg";
  className?: string;
}

/**
 * Badge component - Status indicators and labels
 * Used for premium tiers, trade statuses, notification counts
 */
export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = "default",
  size = "md",
  className,
}) => {
  const baseStyles = "inline-flex items-center justify-center font-semibold rounded-full";

  const variantStyles = {
    default: "bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200",
    success: "bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300",
    warning: "bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-300",
    error: "bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300",
    info: "bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300",
  };

  const sizeStyles = {
    sm: "text-xs px-2 py-0.5",
    md: "text-sm px-3 py-1",
    lg: "text-base px-4 py-1.5",
  };

  return (
    <span className={clsx(baseStyles, variantStyles[variant], sizeStyles[size], className)}>
      {children}
    </span>
  );
};

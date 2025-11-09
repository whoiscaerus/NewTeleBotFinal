import React from "react";
import clsx from "clsx";

export interface CardProps {
  children: React.ReactNode;
  className?: string;
  variant?: "default" | "elevated" | "outlined";
  padding?: "none" | "sm" | "md" | "lg";
  onClick?: () => void;
}

/**
 * Card component - Reusable container with elevation and variants
 * Used across marketing site and Mini App for consistent UI
 */
export const Card: React.FC<CardProps> = ({
  children,
  className,
  variant = "default",
  padding = "md",
  onClick,
}) => {
  const baseStyles = "rounded-lg transition-all duration-200";

  const variantStyles = {
    default: "bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700",
    elevated: "bg-white dark:bg-gray-800 shadow-lg hover:shadow-xl",
    outlined: "bg-transparent border-2 border-gray-300 dark:border-gray-600",
  };

  const paddingStyles = {
    none: "",
    sm: "p-2",
    md: "p-4",
    lg: "p-6",
  };

  const interactiveStyles = onClick
    ? "cursor-pointer hover:scale-[1.02] active:scale-[0.98]"
    : "";

  return (
    <div
      className={clsx(
        baseStyles,
        variantStyles[variant],
        paddingStyles[padding],
        interactiveStyles,
        className
      )}
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
    >
      {children}
    </div>
  );
};

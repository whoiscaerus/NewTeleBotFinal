/**
 * SignalMaturity Component
 *
 * Visual indicator for trading signal age with color-coded warnings.
 * Business logic:
 * - Green: < 5 minutes (fresh signal)
 * - Yellow: 5-15 minutes (aging signal)
 * - Red: > 15 minutes (stale signal)
 */

import React from 'react';

export interface SignalMaturityProps {
  /** Signal creation timestamp */
  createdAt: Date | string;
  /** Current time (defaults to now) */
  currentTime?: Date;
  /** Optional custom class name */
  className?: string;
}

/**
 * Calculate signal age in minutes
 */
function getSignalAgeMinutes(createdAt: Date | string, currentTime: Date): number {
  const created = typeof createdAt === 'string' ? new Date(createdAt) : createdAt;
  const diffMs = currentTime.getTime() - created.getTime();
  return Math.floor(diffMs / 60000); // Convert to minutes
}

/**
 * Get color class based on age
 */
function getMaturityColor(ageMinutes: number): {
  bg: string;
  text: string;
  border: string;
  label: string;
} {
  if (ageMinutes < 5) {
    return {
      bg: 'bg-green-50',
      text: 'text-green-700',
      border: 'border-green-300',
      label: 'Fresh',
    };
  } else if (ageMinutes < 15) {
    return {
      bg: 'bg-yellow-50',
      text: 'text-yellow-700',
      border: 'border-yellow-300',
      label: 'Aging',
    };
  } else {
    return {
      bg: 'bg-red-50',
      text: 'text-red-700',
      border: 'border-red-300',
      label: 'Stale',
    };
  }
}

/**
 * Format age as human-readable text
 */
function formatAge(ageMinutes: number): string {
  if (ageMinutes < 1) {
    return 'Just now';
  } else if (ageMinutes === 1) {
    return '1 minute ago';
  } else if (ageMinutes < 60) {
    return `${ageMinutes} minutes ago`;
  } else {
    const hours = Math.floor(ageMinutes / 60);
    const remainingMinutes = ageMinutes % 60;
    if (remainingMinutes === 0) {
      return `${hours} hour${hours > 1 ? 's' : ''} ago`;
    }
    return `${hours}h ${remainingMinutes}m ago`;
  }
}

/**
 * SignalMaturity Component
 *
 * @example
 * <SignalMaturity createdAt={new Date('2024-11-09T10:00:00Z')} />
 * <SignalMaturity createdAt="2024-11-09T10:00:00Z" currentTime={new Date()} />
 */
export const SignalMaturity: React.FC<SignalMaturityProps> = ({
  createdAt,
  currentTime = new Date(),
  className = '',
}) => {
  const ageMinutes = getSignalAgeMinutes(createdAt, currentTime);
  const color = getMaturityColor(ageMinutes);
  const ageText = formatAge(ageMinutes);

  return (
    <div
      className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full border ${color.bg} ${color.border} ${className}`}
      title={`Signal age: ${ageMinutes} minutes`}
    >
      {/* Visual indicator dot */}
      <span
        className={`w-2 h-2 rounded-full ${color.text.replace('text-', 'bg-')}`}
        aria-hidden="true"
      />

      {/* Age text */}
      <span className={`text-sm font-medium ${color.text}`}>
        {ageText}
      </span>

      {/* Status label */}
      <span className={`text-xs font-semibold uppercase ${color.text} opacity-75`}>
        {color.label}
      </span>
    </div>
  );
};

/**
 * Compact variant for tables/small spaces
 */
export const SignalMaturityCompact: React.FC<SignalMaturityProps> = ({
  createdAt,
  currentTime = new Date(),
  className = '',
}) => {
  const ageMinutes = getSignalAgeMinutes(createdAt, currentTime);
  const color = getMaturityColor(ageMinutes);

  return (
    <div
      className={`inline-flex items-center gap-1.5 ${className}`}
      title={formatAge(ageMinutes)}
    >
      <span
        className={`w-2 h-2 rounded-full ${color.text.replace('text-', 'bg-')}`}
        aria-hidden="true"
      />
      <span className={`text-xs ${color.text}`}>
        {ageMinutes}m
      </span>
    </div>
  );
};

export default SignalMaturity;

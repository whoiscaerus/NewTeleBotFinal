/**
 * ConfidenceMeter Component
 *
 * Visual gauge for signal confidence level (0-100%).
 * Business logic:
 * - Red zone: 0-40% (low confidence)
 * - Yellow zone: 40-70% (medium confidence)
 * - Green zone: 70-100% (high confidence)
 */

import React from 'react';

export interface ConfidenceMeterProps {
  /** Confidence value (0-100) */
  confidence: number;
  /** Optional size variant */
  size?: 'sm' | 'md' | 'lg';
  /** Optional custom class name */
  className?: string;
  /** Show numeric value */
  showValue?: boolean;
  /** Show confidence label */
  showLabel?: boolean;
}

/**
 * Get color class and label based on confidence level
 */
function getConfidenceLevel(confidence: number): {
  color: string;
  textColor: string;
  label: string;
} {
  if (confidence < 40) {
    return {
      color: 'bg-red-500',
      textColor: 'text-red-700',
      label: 'Low Confidence',
    };
  } else if (confidence < 70) {
    return {
      color: 'bg-yellow-500',
      textColor: 'text-yellow-700',
      label: 'Medium Confidence',
    };
  } else {
    return {
      color: 'bg-green-500',
      textColor: 'text-green-700',
      label: 'High Confidence',
    };
  }
}

/**
 * Get size-specific height classes
 */
function getSizeClasses(size: 'sm' | 'md' | 'lg'): string {
  switch (size) {
    case 'sm':
      return 'h-2';
    case 'md':
      return 'h-4';
    case 'lg':
      return 'h-6';
  }
}

/**
 * ConfidenceMeter Component - Progress Bar Style
 *
 * @example
 * <ConfidenceMeter confidence={85} />
 * <ConfidenceMeter confidence={45} showValue showLabel />
 * <ConfidenceMeter confidence={25} size="lg" />
 */
export const ConfidenceMeter: React.FC<ConfidenceMeterProps> = ({
  confidence,
  size = 'md',
  className = '',
  showValue = false,
  showLabel = false,
}) => {
  // Clamp confidence to 0-100 range
  const clampedConfidence = Math.max(0, Math.min(100, confidence));
  const level = getConfidenceLevel(clampedConfidence);
  const heightClass = getSizeClasses(size);

  return (
    <div className={`w-full ${className}`}>
      {/* Progress bar */}
      <div className={`relative w-full ${heightClass} bg-gray-200 rounded-full overflow-hidden`}>
        <div
          className={`h-full ${level.color} transition-all duration-300 ease-out`}
          style={{ width: `${clampedConfidence}%` }}
          role="progressbar"
          aria-valuenow={clampedConfidence}
          aria-valuemin={0}
          aria-valuemax={100}
        />
      </div>

      {/* Value and label */}
      {(showValue || showLabel) && (
        <div className="flex items-center justify-between mt-1.5">
          {showValue && (
            <span className={`text-sm font-semibold ${level.textColor}`}>
              {clampedConfidence}%
            </span>
          )}
          {showLabel && (
            <span className={`text-xs ${level.textColor}`}>
              {level.label}
            </span>
          )}
        </div>
      )}
    </div>
  );
};

/**
 * ConfidenceMeter Circular Gauge Variant
 */
export const ConfidenceMeterCircular: React.FC<ConfidenceMeterProps> = ({
  confidence,
  size = 'md',
  className = '',
}) => {
  const clampedConfidence = Math.max(0, Math.min(100, confidence));
  const level = getConfidenceLevel(clampedConfidence);

  const radius = size === 'sm' ? 20 : size === 'md' ? 30 : 40;
  const strokeWidth = size === 'sm' ? 4 : size === 'md' ? 6 : 8;
  const normalizedRadius = radius - strokeWidth / 2;
  const circumference = normalizedRadius * 2 * Math.PI;
  const strokeDashoffset = circumference - (clampedConfidence / 100) * circumference;

  const svgSize = radius * 2;

  return (
    <div className={`inline-flex items-center justify-center ${className}`}>
      <svg
        height={svgSize}
        width={svgSize}
        className="transform -rotate-90"
      >
        {/* Background circle */}
        <circle
          stroke="#e5e7eb"
          fill="transparent"
          strokeWidth={strokeWidth}
          r={normalizedRadius}
          cx={radius}
          cy={radius}
        />
        {/* Progress circle */}
        <circle
          stroke={level.color.replace('bg-', '')}
          fill="transparent"
          strokeWidth={strokeWidth}
          strokeDasharray={circumference + ' ' + circumference}
          style={{ strokeDashoffset, transition: 'stroke-dashoffset 0.3s ease' }}
          strokeLinecap="round"
          r={normalizedRadius}
          cx={radius}
          cy={radius}
        />
      </svg>

      {/* Center text */}
      <div
        className="absolute flex flex-col items-center justify-center"
        style={{ width: svgSize, height: svgSize }}
      >
        <span className={`font-bold ${size === 'sm' ? 'text-xs' : size === 'md' ? 'text-sm' : 'text-lg'} ${level.textColor}`}>
          {clampedConfidence}%
        </span>
      </div>
    </div>
  );
};

/**
 * Compact variant for tables
 */
export const ConfidenceMeterCompact: React.FC<Omit<ConfidenceMeterProps, 'size' | 'showValue' | 'showLabel'>> = ({
  confidence,
  className = '',
}) => {
  const clampedConfidence = Math.max(0, Math.min(100, confidence));
  const level = getConfidenceLevel(clampedConfidence);

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <div className="w-16 h-2 bg-gray-200 rounded-full overflow-hidden">
        <div
          className={`h-full ${level.color} transition-all duration-300`}
          style={{ width: `${clampedConfidence}%` }}
        />
      </div>
      <span className={`text-xs font-medium ${level.textColor} min-w-[3ch]`}>
        {clampedConfidence}%
      </span>
    </div>
  );
};

export default ConfidenceMeter;

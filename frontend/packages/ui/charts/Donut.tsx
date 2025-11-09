import React from "react";
import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from "recharts";

export interface DonutDataPoint {
  name: string;
  value: number;
  color: string;
}

export interface DonutProps {
  data: DonutDataPoint[];
  centerText?: string;
  centerSubtext?: string;
  height?: number;
  innerRadius?: number;
  outerRadius?: number;
  showLegend?: boolean;
  className?: string;
}

/**
 * Donut (Pie) Chart component - Percentage/distribution visualization
 * Used for win rate, position allocation, instrument breakdown
 * Wrapper around Recharts for consistent styling
 */
export const Donut: React.FC<DonutProps> = ({
  data,
  centerText,
  centerSubtext,
  height = 300,
  innerRadius = 60,
  outerRadius = 100,
  showLegend = true,
  className,
}) => {
  const renderCustomLabel = ({
    cx,
    cy,
    midAngle,
    innerRadius,
    outerRadius,
    percent,
  }: any) => {
    const RADIAN = Math.PI / 180;
    const radius = innerRadius + (outerRadius - innerRadius) * 0.5;
    const x = cx + radius * Math.cos(-midAngle * RADIAN);
    const y = cy + radius * Math.sin(-midAngle * RADIAN);

    return (
      <text
        x={x}
        y={y}
        fill="white"
        textAnchor={x > cx ? "start" : "end"}
        dominantBaseline="central"
        fontSize={12}
        fontWeight="600"
      >
        {`${(percent * 100).toFixed(0)}%`}
      </text>
    );
  };

  return (
    <div className={className} style={{ width: "100%", height, position: "relative" }}>
      <ResponsiveContainer>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            labelLine={false}
            label={renderCustomLabel}
            outerRadius={outerRadius}
            innerRadius={innerRadius}
            fill="#8884d8"
            dataKey="value"
          >
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              backgroundColor: "rgba(0, 0, 0, 0.8)",
              border: "none",
              borderRadius: "8px",
              color: "#fff",
            }}
          />
          {showLegend && <Legend />}
        </PieChart>
      </ResponsiveContainer>

      {/* Center Text */}
      {(centerText || centerSubtext) && (
        <div
          style={{
            position: "absolute",
            top: "50%",
            left: "50%",
            transform: "translate(-50%, -50%)",
            textAlign: "center",
            pointerEvents: "none",
          }}
        >
          {centerText && (
            <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
              {centerText}
            </div>
          )}
          {centerSubtext && (
            <div className="text-sm text-gray-600 dark:text-gray-400">{centerSubtext}</div>
          )}
        </div>
      )}
    </div>
  );
};

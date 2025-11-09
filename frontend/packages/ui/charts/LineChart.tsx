import React from "react";
import {
  LineChart as RechartsLineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

export interface LineChartDataPoint {
  [key: string]: string | number;
}

export interface LineChartLine {
  dataKey: string;
  color: string;
  name?: string;
}

export interface LineChartProps {
  data: LineChartDataPoint[];
  lines: LineChartLine[];
  xAxisKey: string;
  height?: number;
  showGrid?: boolean;
  showLegend?: boolean;
  className?: string;
}

/**
 * LineChart component - Time-series data visualization
 * Used for equity curves, performance trends, price charts
 * Wrapper around Recharts for consistent styling
 */
export const LineChart: React.FC<LineChartProps> = ({
  data,
  lines,
  xAxisKey,
  height = 300,
  showGrid = true,
  showLegend = true,
  className,
}) => {
  return (
    <div className={className} style={{ width: "100%", height }}>
      <ResponsiveContainer>
        <RechartsLineChart data={data} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
          {showGrid && <CartesianGrid strokeDasharray="3 3" opacity={0.2} />}
          <XAxis
            dataKey={xAxisKey}
            tick={{ fill: "currentColor", fontSize: 12 }}
            stroke="currentColor"
            opacity={0.5}
          />
          <YAxis
            tick={{ fill: "currentColor", fontSize: 12 }}
            stroke="currentColor"
            opacity={0.5}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "rgba(0, 0, 0, 0.8)",
              border: "none",
              borderRadius: "8px",
              color: "#fff",
            }}
          />
          {showLegend && <Legend />}
          {lines.map((line) => (
            <Line
              key={line.dataKey}
              type="monotone"
              dataKey={line.dataKey}
              stroke={line.color}
              name={line.name || line.dataKey}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 6 }}
            />
          ))}
        </RechartsLineChart>
      </ResponsiveContainer>
    </div>
  );
};

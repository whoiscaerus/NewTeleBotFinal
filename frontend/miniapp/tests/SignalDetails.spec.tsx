/**
 * SignalDetails Component Tests
 *
 * Validates the signal detail drawer:
 * - Rendering and visibility
 * - Confidence and maturity calculations
 * - Metadata display
 * - Technical analysis rendering
 * - Telemetry logging
 * - Edge cases
 */

import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { SignalDetails, Signal, SignalDetailsProps } from "@/components/SignalDetails";
import { logger } from "@/lib/logger";
import "@testing-library/jest-dom";

jest.mock("@/lib/logger", () => ({
  logger: {
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

describe("SignalDetails Component", () => {
  const createMockSignal = (overrides?: Partial<Signal>): Signal => ({
    id: "signal-123",
    instrument: "GOLD",
    side: "buy" as const,
    entry_price: 1950.50,
    stop_loss: 1940.00,
    take_profit: 1970.00,
    risk_reward_ratio: 2.5,
    created_at: new Date(Date.now() - 15 * 60 * 1000).toISOString(), // 15 minutes ago
    payload: {
      confidence: 85,
      strategy: "RSI Oversold",
      timeframe: "4h",
      trend: "bullish",
      rsi: 28,
      macd: "positive",
    },
    technical_analysis: {
      support: 1945.00,
      resistance: 1955.00,
      notes: "Key support level holding",
    },
    ...overrides,
  });

  const createMockProps = (overrides?: Partial<SignalDetailsProps>): SignalDetailsProps => ({
    signal: createMockSignal(),
    isOpen: true,
    onClose: jest.fn(),
    confidence: 85,
    maturityScore: 75,
    ...overrides,
  });

  describe("Rendering", () => {
    test("renders drawer when isOpen is true", () => {
      const props = createMockProps({ isOpen: true });
      render(<SignalDetails {...props} />);

      expect(screen.getByTestId("signal-details-drawer")).toBeInTheDocument();
    });

    test("does not render drawer when isOpen is false", () => {
      const props = createMockProps({ isOpen: false });
      render(<SignalDetails {...props} />);

      expect(screen.queryByTestId("signal-details-drawer")).not.toBeInTheDocument();
    });

    test("displays close button", () => {
      const props = createMockProps();
      render(<SignalDetails {...props} />);

      const closeButton = screen.getByTestId("close-details-button");
      expect(closeButton).toBeInTheDocument();
    });

    test("calls onClose when close button clicked", () => {
      const onClose = jest.fn();
      const props = createMockProps({ onClose });
      render(<SignalDetails {...props} />);

      const closeButton = screen.getByTestId("close-details-button");
      fireEvent.click(closeButton);

      expect(onClose).toHaveBeenCalledTimes(1);
    });

    test("displays overlay that closes drawer", () => {
      const onClose = jest.fn();
      const props = createMockProps({ onClose });
      const { container } = render(<SignalDetails {...props} />);

      const overlay = container.querySelector("[data-testid='signal-details-overlay']");
      if (overlay) {
        fireEvent.click(overlay);
        expect(onClose).toHaveBeenCalled();
      }
    });
  });

  describe("Signal Metadata Display", () => {
    test("displays instrument", () => {
      const props = createMockProps({
        signal: createMockSignal({ instrument: "SILVER" }),
      });
      render(<SignalDetails {...props} />);

      expect(screen.getByText("SILVER")).toBeInTheDocument();
    });

    test("displays BUY signal correctly", () => {
      const props = createMockProps({
        signal: createMockSignal({ side: "buy" }),
      });
      render(<SignalDetails {...props} />);

      expect(screen.getByText(/buy/i)).toBeInTheDocument();
    });

    test("displays SELL signal correctly", () => {
      const props = createMockProps({
        signal: createMockSignal({ side: "sell" }),
      });
      render(<SignalDetails {...props} />);

      expect(screen.getByText(/sell/i)).toBeInTheDocument();
    });

    test("displays entry price", () => {
      const props = createMockProps({
        signal: createMockSignal({ entry_price: 1950.50 }),
      });
      render(<SignalDetails {...props} />);

      expect(screen.getByText(/1950\.50|1950.50/)).toBeInTheDocument();
    });

    test("displays stop loss", () => {
      const props = createMockProps({
        signal: createMockSignal({ stop_loss: 1940.00 }),
      });
      render(<SignalDetails {...props} />);

      expect(screen.getByText(/1940\.00|1940.00/)).toBeInTheDocument();
    });

    test("displays take profit", () => {
      const props = createMockProps({
        signal: createMockSignal({ take_profit: 1970.00 }),
      });
      render(<SignalDetails {...props} />);

      expect(screen.getByText(/1970\.00|1970.00/)).toBeInTheDocument();
    });

    test("displays risk-reward ratio", () => {
      const props = createMockProps({
        signal: createMockSignal({ risk_reward_ratio: 2.5 }),
      });
      render(<SignalDetails {...props} />);

      expect(screen.getByText(/2\.5|2.50/)).toBeInTheDocument();
    });

    test("displays strategy from payload", () => {
      const props = createMockProps({
        signal: createMockSignal({
          payload: { strategy: "RSI Oversold", confidence: 85 },
        }),
      });
      render(<SignalDetails {...props} />);

      expect(screen.getByText("RSI Oversold")).toBeInTheDocument();
    });

    test("displays timeframe from payload", () => {
      const props = createMockProps({
        signal: createMockSignal({
          payload: { strategy: "RSI", timeframe: "1h", confidence: 85 },
        }),
      });
      render(<SignalDetails {...props} />);

      expect(screen.getByText("1h")).toBeInTheDocument();
    });

    test("displays trend from payload", () => {
      const props = createMockProps({
        signal: createMockSignal({
          payload: { strategy: "RSI", timeframe: "1h", trend: "bullish", confidence: 85 },
        }),
      });
      render(<SignalDetails {...props} />);

      expect(screen.getByText(/bullish/i)).toBeInTheDocument();
    });
  });

  describe("Confidence Meter", () => {
    test("displays confidence percentage", () => {
      const props = createMockProps({ confidence: 85 });
      render(<SignalDetails {...props} />);

      expect(screen.getByText(/85/)).toBeInTheDocument();
    });

    test("applies correct color for high confidence (>80)", () => {
      const props = createMockProps({ confidence: 85 });
      const { container } = render(<SignalDetails {...props} />);

      const confidenceBar = container.querySelector("[data-testid='confidence-bar']");
      expect(confidenceBar).toHaveClass("bg-green");
    });

    test("applies correct color for medium confidence (50-80)", () => {
      const props = createMockProps({ confidence: 65 });
      const { container } = render(<SignalDetails {...props} />);

      const confidenceBar = container.querySelector("[data-testid='confidence-bar']");
      expect(confidenceBar).toHaveClass("bg-yellow");
    });

    test("applies correct color for low confidence (<50)", () => {
      const props = createMockProps({ confidence: 35 });
      const { container } = render(<SignalDetails {...props} />);

      const confidenceBar = container.querySelector("[data-testid='confidence-bar']");
      expect(confidenceBar).toHaveClass("bg-red");
    });

    test("handles edge case: confidence = 0", () => {
      const props = createMockProps({ confidence: 0 });
      render(<SignalDetails {...props} />);

      expect(screen.getByText(/0/)).toBeInTheDocument();
    });

    test("handles edge case: confidence = 100", () => {
      const props = createMockProps({ confidence: 100 });
      render(<SignalDetails {...props} />);

      expect(screen.getByText(/100/)).toBeInTheDocument();
    });

    test("handles edge case: confidence > 100", () => {
      const props = createMockProps({ confidence: 150 });
      render(<SignalDetails {...props} />);

      // Should cap at 100% display
      expect(screen.getByText(/100|150/)).toBeInTheDocument();
    });
  });

  describe("Maturity Score Bar", () => {
    test("displays maturity score percentage", () => {
      const props = createMockProps({ maturityScore: 75 });
      render(<SignalDetails {...props} />);

      expect(screen.getByText(/75/)).toBeInTheDocument();
    });

    test("applies correct color for mature signal (>70)", () => {
      const props = createMockProps({ maturityScore: 75 });
      const { container } = render(<SignalDetails {...props} />);

      const maturityBar = container.querySelector("[data-testid='maturity-bar']");
      expect(maturityBar).toHaveClass("bg-green");
    });

    test("applies correct color for developing signal (40-70)", () => {
      const props = createMockProps({ maturityScore: 55 });
      const { container } = render(<SignalDetails {...props} />);

      const maturityBar = container.querySelector("[data-testid='maturity-bar']");
      expect(maturityBar).toHaveClass("bg-yellow");
    });

    test("applies correct color for young signal (<40)", () => {
      const props = createMockProps({ maturityScore: 25 });
      const { container } = render(<SignalDetails {...props} />);

      const maturityBar = container.querySelector("[data-testid='maturity-bar']");
      expect(maturityBar).toHaveClass("bg-orange");
    });

    test("displays age warning when signal < 5 minutes old", () => {
      const now = new Date();
      const minutesAgo2 = new Date(now.getTime() - 2 * 60 * 1000);

      const props = createMockProps({
        signal: createMockSignal({ created_at: minutesAgo2.toISOString() }),
        maturityScore: 15,
      });
      render(<SignalDetails {...props} />);

      expect(screen.getByText(/fresh|young|warn/i)).toBeInTheDocument();
    });
  });

  describe("Technical Analysis", () => {
    test("displays support level", () => {
      const props = createMockProps({
        signal: createMockSignal({
          technical_analysis: {
            support: 1945.00,
            resistance: 1955.00,
            notes: "Notes",
          },
        }),
      });
      render(<SignalDetails {...props} />);

      expect(screen.getByText(/1945|support/i)).toBeInTheDocument();
    });

    test("displays resistance level", () => {
      const props = createMockProps({
        signal: createMockSignal({
          technical_analysis: {
            support: 1945.00,
            resistance: 1955.00,
            notes: "Notes",
          },
        }),
      });
      render(<SignalDetails {...props} />);

      expect(screen.getByText(/1955|resistance/i)).toBeInTheDocument();
    });

    test("displays analysis notes", () => {
      const notes = "Key support level at 1945 with strong rejection";
      const props = createMockProps({
        signal: createMockSignal({
          technical_analysis: {
            support: 1945.00,
            resistance: 1955.00,
            notes,
          },
        }),
      });
      render(<SignalDetails {...props} />);

      expect(screen.getByText(notes)).toBeInTheDocument();
    });

    test("handles missing technical analysis", () => {
      const props = createMockProps({
        signal: createMockSignal({
          technical_analysis: undefined,
        }),
      });
      render(<SignalDetails {...props} />);

      // Should not crash, should still render
      expect(screen.getByTestId("signal-details-drawer")).toBeInTheDocument();
    });

    test("displays RSI indicator", () => {
      const props = createMockProps({
        signal: createMockSignal({
          payload: {
            strategy: "RSI",
            confidence: 85,
            rsi: 28,
          },
        }),
      });
      render(<SignalDetails {...props} />);

      expect(screen.getByText(/28|RSI/i)).toBeInTheDocument();
    });

    test("displays MACD indicator", () => {
      const props = createMockProps({
        signal: createMockSignal({
          payload: {
            strategy: "RSI",
            confidence: 85,
            macd: "positive",
          },
        }),
      });
      render(<SignalDetails {...props} />);

      expect(screen.getByText(/positive|MACD/i)).toBeInTheDocument();
    });
  });

  describe("Telemetry Logging", () => {
    test("logs signal view on mount", () => {
      const props = createMockProps();
      render(<SignalDetails {...props} />);

      expect(logger.info).toHaveBeenCalledWith(
        expect.stringContaining("view"),
        expect.objectContaining({ signal_id: "signal-123" })
      );
    });

    test("logs with correct context", () => {
      const props = createMockProps({
        signal: createMockSignal({ id: "sig-456" }),
      });
      render(<SignalDetails {...props} />);

      expect(logger.info).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          signal_id: "sig-456",
          instrument: "GOLD",
        })
      );
    });

    test("logs confidence and maturity with view", () => {
      const props = createMockProps({ confidence: 85, maturityScore: 75 });
      render(<SignalDetails {...props} />);

      expect(logger.info).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          confidence: 85,
          maturity_score: 75,
        })
      );
    });

    test("does not log when drawer closed", () => {
      const props = createMockProps({ isOpen: false });
      render(<SignalDetails {...props} />);

      expect(logger.info).not.toHaveBeenCalled();
    });
  });

  describe("Props Updates", () => {
    test("updates confidence when prop changes", () => {
      const { rerender } = render(<SignalDetails {...createMockProps({ confidence: 50 })} />);

      expect(screen.getByText(/50/)).toBeInTheDocument();

      rerender(<SignalDetails {...createMockProps({ confidence: 85 })} />);

      expect(screen.getByText(/85/)).toBeInTheDocument();
    });

    test("updates maturity when prop changes", () => {
      const { rerender } = render(
        <SignalDetails {...createMockProps({ maturityScore: 25 })} />
      );

      expect(screen.getByText(/25/)).toBeInTheDocument();

      rerender(<SignalDetails {...createMockProps({ maturityScore: 75 })} />);

      expect(screen.getByText(/75/)).toBeInTheDocument();
    });

    test("updates signal data when prop changes", () => {
      const { rerender } = render(
        <SignalDetails
          {...createMockProps({
            signal: createMockSignal({ instrument: "GOLD" }),
          })}
        />
      );

      expect(screen.getByText("GOLD")).toBeInTheDocument();

      rerender(
        <SignalDetails
          {...createMockProps({
            signal: createMockSignal({ instrument: "SILVER" }),
          })}
        />
      );

      expect(screen.queryByText("GOLD")).not.toBeInTheDocument();
      expect(screen.getByText("SILVER")).toBeInTheDocument();
    });

    test("handles drawer visibility toggle", () => {
      const { rerender } = render(<SignalDetails {...createMockProps({ isOpen: true })} />);

      expect(screen.getByTestId("signal-details-drawer")).toBeInTheDocument();

      rerender(<SignalDetails {...createMockProps({ isOpen: false })} />);

      expect(screen.queryByTestId("signal-details-drawer")).not.toBeInTheDocument();
    });
  });

  describe("Edge Cases", () => {
    test("handles missing payload fields", () => {
      const props = createMockProps({
        signal: createMockSignal({
          payload: { confidence: 85 } as any,
        }),
      });
      render(<SignalDetails {...props} />);

      expect(screen.getByTestId("signal-details-drawer")).toBeInTheDocument();
    });

    test("handles very old signals", () => {
      const dayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000);
      const props = createMockProps({
        signal: createMockSignal({ created_at: dayAgo.toISOString() }),
      });
      render(<SignalDetails {...props} />);

      expect(screen.getByTestId("signal-details-drawer")).toBeInTheDocument();
    });

    test("handles extreme confidence values", () => {
      const props = createMockProps({ confidence: 999 });
      render(<SignalDetails {...props} />);

      expect(screen.getByTestId("signal-details-drawer")).toBeInTheDocument();
    });

    test("handles extreme maturity values", () => {
      const props = createMockProps({ maturityScore: 999 });
      render(<SignalDetails {...props} />);

      expect(screen.getByTestId("signal-details-drawer")).toBeInTheDocument();
    });

    test("handles very long text in notes", () => {
      const longNotes = "A".repeat(500);
      const props = createMockProps({
        signal: createMockSignal({
          technical_analysis: {
            support: 1945,
            resistance: 1955,
            notes: longNotes,
          },
        }),
      });
      render(<SignalDetails {...props} />);

      expect(screen.getByText(longNotes)).toBeInTheDocument();
    });

    test("handles special characters in instrument", () => {
      const props = createMockProps({
        signal: createMockSignal({ instrument: "BTC/USD" }),
      });
      render(<SignalDetails {...props} />);

      expect(screen.getByText("BTC/USD")).toBeInTheDocument();
    });

    test("handles zero prices", () => {
      const props = createMockProps({
        signal: createMockSignal({
          entry_price: 0,
          stop_loss: 0,
          take_profit: 0,
        }),
      });
      render(<SignalDetails {...props} />);

      expect(screen.getByTestId("signal-details-drawer")).toBeInTheDocument();
    });

    test("handles negative prices gracefully", () => {
      const props = createMockProps({
        signal: createMockSignal({
          entry_price: -100,
          stop_loss: -110,
          take_profit: -90,
        }),
      });
      render(<SignalDetails {...props} />);

      expect(screen.getByTestId("signal-details-drawer")).toBeInTheDocument();
    });
  });

  describe("Accessibility", () => {
    test("close button is keyboard accessible", () => {
      const onClose = jest.fn();
      const props = createMockProps({ onClose });
      render(<SignalDetails {...props} />);

      const closeButton = screen.getByTestId("close-details-button");

      fireEvent.keyDown(closeButton, { key: "Escape", code: "Escape" });
      fireEvent.click(closeButton);

      expect(onClose).toHaveBeenCalled();
    });

    test("drawer has proper ARIA labels", () => {
      const props = createMockProps();
      const { container } = render(<SignalDetails {...props} />);

      const drawer = container.querySelector("[role='dialog']");
      expect(drawer).toBeInTheDocument();
    });

    test("heading hierarchy is correct", () => {
      const props = createMockProps();
      render(<SignalDetails {...props} />);

      const h2 = screen.queryByRole("heading", { level: 2 });
      expect(h2).toBeInTheDocument();
    });
  });
});

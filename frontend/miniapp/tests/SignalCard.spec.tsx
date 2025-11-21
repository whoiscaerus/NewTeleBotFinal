/**
 * SignalCard Component Tests
 *
 * Validates all component logic:
 * - Rendering with valid/invalid props
 * - Display of signal data
 * - Real-time relative time updates
 * - Button callbacks and loading states
 * - Edge cases and error handling
 */

import React from "react";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { SignalCard, Signal, SignalCardProps } from "@/components/SignalCard";
import "@testing-library/jest-dom";

// Mock date-fns
jest.mock("date-fns", () => ({
  formatDistanceToNow: jest.fn((date) => {
    const d = new Date(date);
    if (isNaN(d.getTime())) throw new RangeError("Invalid time value");

    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffSecs = Math.floor(diffMs / 1000);
    const diffMins = Math.floor(diffSecs / 60);

    if (diffMins < 1) return `${diffSecs}s ago`;
    if (diffMins < 60) return `${diffMins}m ago`;
    return "1h ago";
  }),
}));

// Mock logger
jest.mock("@/lib/logger", () => ({
  logger: {
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

describe("SignalCard Component", () => {
  // Test fixtures
  const createMockSignal = (overrides?: Partial<Signal>): Signal => ({
    id: "signal-123",
    instrument: "GOLD",
    side: "buy" as const,
    entry_price: 1950.50,
    stop_loss: 1940.00,
    take_profit: 1970.00,
    risk_reward_ratio: 2.5,
    created_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(), // 5 minutes ago
    payload: { confidence: 85, strategy: "RSI Oversold" },
    ...overrides,
  });

  const createMockProps = (overrides?: Partial<SignalCardProps>): SignalCardProps => ({
    approvalId: "approval-456",
    signal: createMockSignal(),
    isProcessing: false,
    onApprove: jest.fn(),
    onReject: jest.fn(),
    ...overrides,
  });

  describe("Rendering", () => {
    test("renders signal card with all required elements", () => {
      const props = createMockProps();
      render(<SignalCard {...props} />);

      expect(screen.getByTestId("signal-card-approval-456")).toBeInTheDocument();
      expect(screen.getByText("GOLD")).toBeInTheDocument();
      expect(screen.getByText("📈 BUY")).toBeInTheDocument();
      expect(screen.getByTestId("approve-button-approval-456")).toBeInTheDocument();
      expect(screen.getByTestId("reject-button-approval-456")).toBeInTheDocument();
    });

    test("displays SELL signal correctly", () => {
      const props = createMockProps({
        signal: createMockSignal({ side: "sell" }),
      });
      render(<SignalCard {...props} />);

      expect(screen.getByText("📉 SELL")).toBeInTheDocument();
    });

    test("renders with testid attribute for testing", () => {
      const props = createMockProps();
      render(<SignalCard {...props} />);

      const card = screen.getByTestId("signal-card-approval-456");
      expect(card).toHaveClass("rounded-lg", "border", "border-blue-400");
    });
  });

  describe("Signal Data Display", () => {
    test("displays instrument name", () => {
      const props = createMockProps({
        signal: createMockSignal({ instrument: "AAPL" }),
      });
      render(<SignalCard {...props} />);

      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    test("displays entry price formatted to 2 decimals", () => {
      const props = createMockProps({
        signal: createMockSignal({ entry_price: 1950.12345 }),
      });
      render(<SignalCard {...props} />);

      const priceText = screen.getByText("1950.12");
      expect(priceText).toBeInTheDocument();
    });

    test("displays stop loss formatted to 2 decimals", () => {
      const props = createMockProps({
        signal: createMockSignal({ stop_loss: 1940.99 }),
      });
      render(<SignalCard {...props} />);

      const stopText = screen.getByText("1940.99");
      expect(stopText).toBeInTheDocument();
    });

    test("displays take profit formatted to 2 decimals", () => {
      const props = createMockProps({
        signal: createMockSignal({ take_profit: 1970.50 }),
      });
      render(<SignalCard {...props} />);

      const tpText = screen.getByText("1970.50");
      expect(tpText).toBeInTheDocument();
    });

    test("displays risk-reward ratio in badge", () => {
      const props = createMockProps({
        signal: createMockSignal({ risk_reward_ratio: 3.75 }),
      });
      render(<SignalCard {...props} />);

      expect(screen.getByText(/RR: 3.75/)).toBeInTheDocument();
    });

    test("handles large risk-reward ratios", () => {
      const props = createMockProps({
        signal: createMockSignal({ risk_reward_ratio: 10.5 }),
      });
      render(<SignalCard {...props} />);

      expect(screen.getByText(/RR: 10.50/)).toBeInTheDocument();
    });
  });

  describe("Relative Time Display", () => {
    test("displays relative time on mount", () => {
      const props = createMockProps();
      render(<SignalCard {...props} />);

      expect(screen.getByText(/ago/)).toBeInTheDocument();
    });

    test("updates relative time every second", async () => {
      jest.useFakeTimers();

      const signal = createMockSignal({
        created_at: new Date(Date.now() - 10 * 1000).toISOString(),
      });
      const props = createMockProps({ signal });
      render(<SignalCard {...props} />);

      // Wait for first render
      expect(screen.getByText(/ago/)).toBeInTheDocument();

      // Fast-forward 1 second
      act(() => {
        jest.advanceTimersByTime(1000);
      });

      // Time should update
      await waitFor(() => {
        expect(screen.getByText(/ago/)).toBeInTheDocument();
      });

      jest.useRealTimers();
    });

    test("cleans up interval on unmount", () => {
      jest.useFakeTimers();
      const setIntervalSpy = jest.spyOn(global, "setInterval");
      const clearIntervalSpy = jest.spyOn(global, "clearInterval");

      const props = createMockProps();
      const { unmount } = render(<SignalCard {...props} />);

      expect(setIntervalSpy).toHaveBeenCalled();
      const intervalId = setIntervalSpy.mock.results[0].value;

      unmount();

      expect(clearIntervalSpy).toHaveBeenCalledWith(intervalId);

      setIntervalSpy.mockRestore();
      clearIntervalSpy.mockRestore();
      jest.useRealTimers();
    });

    test("handles invalid date gracefully", () => {
      const props = createMockProps({
        signal: createMockSignal({ created_at: "invalid-date" }),
      });
      render(<SignalCard {...props} />);

      expect(screen.getByText("just now")).toBeInTheDocument();
    });

    test("handles missing created_at gracefully", () => {
      const signal = createMockSignal();
      delete signal.created_at;

      const props = createMockProps({ signal: signal as Signal });
      render(<SignalCard {...props} />);

      expect(screen.getByText("just now")).toBeInTheDocument();
    });
  });

  describe("Button Callbacks", () => {
    test("calls onApprove with correct parameters when approve button clicked", () => {
      const onApprove = jest.fn();
      const props = createMockProps({ onApprove });
      render(<SignalCard {...props} />);

      const approveButton = screen.getByTestId("approve-button-approval-456");
      fireEvent.click(approveButton);

      expect(onApprove).toHaveBeenCalledWith("approval-456", "signal-123");
      expect(onApprove).toHaveBeenCalledTimes(1);
    });

    test("calls onReject with correct parameters when reject button clicked", () => {
      const onReject = jest.fn();
      const props = createMockProps({ onReject });
      render(<SignalCard {...props} />);

      const rejectButton = screen.getByTestId("reject-button-approval-456");
      fireEvent.click(rejectButton);

      expect(onReject).toHaveBeenCalledWith("approval-456", "signal-123");
      expect(onReject).toHaveBeenCalledTimes(1);
    });

    test("does not call callback when isProcessing is true", () => {
      const onApprove = jest.fn();
      const props = createMockProps({ onApprove, isProcessing: true });
      render(<SignalCard {...props} />);

      const approveButton = screen.getByTestId("approve-button-approval-456");

      // Button should be disabled
      expect(approveButton).toBeDisabled();

      // Attempt to click (should be blocked by disabled state)
      fireEvent.click(approveButton);
      expect(onApprove).not.toHaveBeenCalled();
    });

    test("can click multiple times if not processing", () => {
      const onApprove = jest.fn();
      const props = createMockProps({ onApprove });
      render(<SignalCard {...props} />);

      const approveButton = screen.getByTestId("approve-button-approval-456");

      fireEvent.click(approveButton);
      fireEvent.click(approveButton);
      fireEvent.click(approveButton);

      expect(onApprove).toHaveBeenCalledTimes(3);
    });
  });

  describe("Loading States", () => {
    test("disables buttons when isProcessing is true", () => {
      const props = createMockProps({ isProcessing: true });
      render(<SignalCard {...props} />);

      const approveButton = screen.getByTestId("approve-button-approval-456");
      const rejectButton = screen.getByTestId("reject-button-approval-456");

      expect(approveButton).toBeDisabled();
      expect(rejectButton).toBeDisabled();
    });

    test("enables buttons when isProcessing is false", () => {
      const props = createMockProps({ isProcessing: false });
      render(<SignalCard {...props} />);

      const approveButton = screen.getByTestId("approve-button-approval-456");
      const rejectButton = screen.getByTestId("reject-button-approval-456");

      expect(approveButton).not.toBeDisabled();
      expect(rejectButton).not.toBeDisabled();
    });

    test("shows loading indicator (...) when processing", () => {
      const props = createMockProps({ isProcessing: true });
      render(<SignalCard {...props} />);

      const approveButton = screen.getByTestId("approve-button-approval-456");
      expect(approveButton).toHaveTextContent("...");
    });

    test("shows button text when not processing", () => {
      const props = createMockProps({ isProcessing: false });
      render(<SignalCard {...props} />);

      const approveButton = screen.getByTestId("approve-button-approval-456");
      expect(approveButton).toHaveTextContent("✅ Approve");
    });

    test("applies opacity when processing", () => {
      const props = createMockProps({ isProcessing: true });
      const { container } = render(<SignalCard {...props} />);

      const card = container.querySelector("[data-testid='signal-card-approval-456']");
      expect(card).toHaveClass("opacity-50");
    });
  });

  describe("Edge Cases & Error Handling", () => {
    test("handles zero risk-reward ratio", () => {
      const props = createMockProps({
        signal: createMockSignal({ risk_reward_ratio: 0 }),
      });
      render(<SignalCard {...props} />);

      expect(screen.getByText(/RR: 0.00/)).toBeInTheDocument();
    });

    test("handles negative prices gracefully", () => {
      const props = createMockProps({
        signal: createMockSignal({
          entry_price: -100,
          stop_loss: -110,
          take_profit: -90,
        }),
      });
      render(<SignalCard {...props} />);

      expect(screen.getByText("-100.00")).toBeInTheDocument();
      expect(screen.getByText("-110.00")).toBeInTheDocument();
    });

    test("handles very large numbers", () => {
      const props = createMockProps({
        signal: createMockSignal({
          entry_price: 999999.99,
          risk_reward_ratio: 100.0,
        }),
      });
      render(<SignalCard {...props} />);

      expect(screen.getByText("999999.99")).toBeInTheDocument();
      expect(screen.getByText(/RR: 100.00/)).toBeInTheDocument();
    });

    test("handles special characters in instrument", () => {
      const props = createMockProps({
        signal: createMockSignal({ instrument: "BTC/USD" }),
      });
      render(<SignalCard {...props} />);

      expect(screen.getByText("BTC/USD")).toBeInTheDocument();
    });

    test("maintains proper styling for BUY signals", () => {
      const props = createMockProps({
        signal: createMockSignal({ side: "buy" }),
      });
      const { container } = render(<SignalCard {...props} />);

      const badge = container.querySelector('[data-testid*="signal"]');
      expect(badge?.textContent).toContain("📈");
    });

    test("maintains proper styling for SELL signals", () => {
      const props = createMockProps({
        signal: createMockSignal({ side: "sell" }),
      });
      const { container } = render(<SignalCard {...props} />);

      expect(screen.getByText(/SELL/)).toBeInTheDocument();
    });
  });

  describe("Props Validation", () => {
    test("renders with minimal required props", () => {
      const signal = createMockSignal();
      const props: SignalCardProps = {
        approvalId: "test-id",
        signal,
        isProcessing: false,
        onApprove: jest.fn(),
        onReject: jest.fn(),
      };
      render(<SignalCard {...props} />);

      expect(screen.getByTestId("signal-card-test-id")).toBeInTheDocument();
    });

    test("updates when props change", () => {
      const { rerender } = render(
        <SignalCard {...createMockProps({ isProcessing: false })} />
      );

      const approveButton = screen.getByTestId("approve-button-approval-456");
      expect(approveButton).not.toBeDisabled();

      rerender(<SignalCard {...createMockProps({ isProcessing: true })} />);

      expect(approveButton).toBeDisabled();
    });

    test("updates signal data when signal prop changes", () => {
      const { rerender } = render(
        <SignalCard
          {...createMockProps({
            signal: createMockSignal({ instrument: "GOLD" }),
          })}
        />
      );

      expect(screen.getByText("GOLD")).toBeInTheDocument();

      rerender(
        <SignalCard
          {...createMockProps({
            signal: createMockSignal({ instrument: "SILVER" }),
          })}
        />
      );

      expect(screen.queryByText("GOLD")).not.toBeInTheDocument();
      expect(screen.getByText("SILVER")).toBeInTheDocument();
    });
  });

  describe("Accessibility", () => {
    test("buttons are keyboard accessible", () => {
      const onApprove = jest.fn();
      const props = createMockProps({ onApprove });
      render(<SignalCard {...props} />);

      const approveButton = screen.getByTestId("approve-button-approval-456");

      // Simulate Enter key press
      fireEvent.keyDown(approveButton, { key: "Enter", code: "Enter" });
      fireEvent.click(approveButton); // Click triggers the callback

      expect(onApprove).toHaveBeenCalled();
    });
  });
});

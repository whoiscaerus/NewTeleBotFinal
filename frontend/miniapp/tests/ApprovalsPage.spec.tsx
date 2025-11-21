/**
 * Approvals Page Tests
 *
 * Validates the main approval listing page:
 * - Authentication flow
 * - Signal polling and updates
 * - Approve/reject workflows
 * - State management
 * - Error handling
 * - Loading states
 */

import React from "react";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import ApprovalsPage from "@/app/approvals/page";
import * as approvalsService from "@/lib/approvals";
import { useTelegram } from "@/app/_providers/TelegramProvider";

// Mock dependencies
jest.mock("@/app/_providers/TelegramProvider");
jest.mock("@/lib/approvals");
jest.mock("@/lib/logger", () => ({
  logger: {
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));
jest.mock("@/lib/toastNotifications", () => ({
  showSuccessToast: jest.fn(),
  showErrorToast: jest.fn(),
}));
jest.mock("@/lib/hapticFeedback", () => ({
  vibrateSuccess: jest.fn(),
  vibrateError: jest.fn(),
}));
jest.mock("@/lib/telemetry", () => ({
  trackApprovalClick: jest.fn(),
  trackRejectionClick: jest.fn(),
  trackApprovalSuccess: jest.fn(),
  trackApprovalError: jest.fn(),
  trackRejectionSuccess: jest.fn(),
  trackRejectionError: jest.fn(),
}));

describe("Approvals Page", () => {
  const mockAuth = {
    user: {
      id: "user-123",
      email: "user@example.com",
      jwt_token: "valid.jwt.token",
      expires_at: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
    },
    jwt: "valid.jwt.token",
    isLoading: false,
    error: null,
  };

  const mockSignals = [
    {
      id: "approval-1",
      signal_id: "signal-1",
      approval_token: "token-1",
      expires_at: new Date(Date.now() + 3600000).toISOString(),
      signal: {
        id: "signal-1",
        instrument: "GOLD",
        side: "buy" as const,
        entry_price: 1950.50,
        stop_loss: 1940.00,
        take_profit: 1970.00,
        risk_reward_ratio: 2.5,
        created_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
        payload: { confidence: 85 },
      },
    },
    {
      id: "approval-2",
      signal_id: "signal-2",
      approval_token: "token-2",
      expires_at: new Date(Date.now() + 3600000).toISOString(),
      signal: {
        id: "signal-2",
        instrument: "SILVER",
        side: "sell" as const,
        entry_price: 25.50,
        stop_loss: 26.00,
        take_profit: 24.50,
        risk_reward_ratio: 1.5,
        created_at: new Date(Date.now() - 2 * 60 * 1000).toISOString(),
        payload: { confidence: 72 },
      },
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
    (useTelegram as jest.Mock).mockReturnValue(mockAuth);
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  describe("Authentication", () => {
    test("displays loading state when auth is loading", () => {
      (useTelegram as jest.Mock).mockReturnValue({
        user: null,
        jwt: null,
        isLoading: true,
        error: null,
      });

      render(<ApprovalsPage />);

      expect(screen.getByText(/Authenticating/i)).toBeInTheDocument();
    });

    test("displays error when not authenticated", () => {
      (useTelegram as jest.Mock).mockReturnValue({
        user: null,
        jwt: null,
        isLoading: false,
        error: "Not authenticated",
      });

      render(<ApprovalsPage />);

      expect(screen.getByText(/not authenticated|authentication required/i)).toBeInTheDocument();
    });





    test("renders page when authenticated with valid JWT", async () => {
      (approvalsService.fetchPendingApprovals as jest.Mock).mockResolvedValue([]);

      render(<ApprovalsPage />);

      await waitFor(() => {
        expect(approvalsService.fetchPendingApprovals).toHaveBeenCalledWith(
          mockAuth.user.jwt_token
        );
      });
    });
  });

  describe("Signal Loading", () => {
    test("fetches pending approvals on mount", async () => {
      (approvalsService.fetchPendingApprovals as jest.Mock).mockResolvedValue(mockSignals);

      render(<ApprovalsPage />);

      await waitFor(() => {
        expect(approvalsService.fetchPendingApprovals).toHaveBeenCalledWith(
          mockAuth.user.jwt_token
        );
      });
    });

    test("displays signals after loading", async () => {
      (approvalsService.fetchPendingApprovals as jest.Mock).mockResolvedValue(mockSignals);

      render(<ApprovalsPage />);

      await waitFor(() => {
        expect(screen.getByText("GOLD")).toBeInTheDocument();
        expect(screen.getByText("SILVER")).toBeInTheDocument();
      });
    });

    test("displays empty state when no signals pending", async () => {
      (approvalsService.fetchPendingApprovals as jest.Mock).mockResolvedValue([]);

      render(<ApprovalsPage />);

      await waitFor(() => {
        expect(screen.getByText(/no pending|no signals/i)).toBeInTheDocument();
      });
    });

    test("displays error when fetch fails", async () => {
      (approvalsService.fetchPendingApprovals as jest.Mock).mockRejectedValue(
        new Error("Network error")
      );

      render(<ApprovalsPage />);

      await waitFor(() => {
        expect(screen.getByText("Network error")).toBeInTheDocument();
      });
    });

    test("displays loading state while fetching", async () => {
      (approvalsService.fetchPendingApprovals as jest.Mock).mockImplementation(
        () => new Promise(resolve => setTimeout(() => resolve([]), 100))
      );

      render(<ApprovalsPage />);

      expect(screen.getByText(/loading|fetching/i)).toBeInTheDocument();

      act(() => {
        jest.advanceTimersByTime(100);
      });

      await waitFor(() => {
        expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
      });
    });
  });

  describe("Polling", () => {
    test("sets up polling interval on mount", async () => {
      const setIntervalSpy = jest.spyOn(global, "setInterval");

      (approvalsService.fetchPendingApprovals as jest.Mock).mockResolvedValue([]);

      render(<ApprovalsPage />);

      await waitFor(() => {
        expect(setIntervalSpy).toHaveBeenCalled();
      });

      setIntervalSpy.mockRestore();
    });

    test("fetches new signals at polling interval", async () => {
      (approvalsService.fetchPendingApprovals as jest.Mock).mockResolvedValue([]);

      render(<ApprovalsPage />);

      await waitFor(() => {
        expect(approvalsService.fetchPendingApprovals).toHaveBeenCalled();
      });

      const initialCallCount = (approvalsService.fetchPendingApprovals as jest.Mock)
        .mock.calls.length;

      // Advance time by 5 seconds (polling interval)
      act(() => {
        jest.advanceTimersByTime(5000);
      });

      await waitFor(() => {
        expect((approvalsService.fetchPendingApprovals as jest.Mock).mock.calls.length).toBeGreaterThan(
          initialCallCount
        );
      });
    });

    test("cleans up polling on unmount", () => {
      const clearIntervalSpy = jest.spyOn(global, "clearInterval");

      (approvalsService.fetchPendingApprovals as jest.Mock).mockResolvedValue([]);

      const { unmount } = render(<ApprovalsPage />);

      unmount();

      expect(clearIntervalSpy).toHaveBeenCalled();

      clearIntervalSpy.mockRestore();
    });

    test("does not poll if not authenticated", () => {
      (useTelegram as jest.Mock).mockReturnValue({
        user: null,
        jwt: null,
        isLoading: false,
        error: "Not authenticated",
      });

      const setIntervalSpy = jest.spyOn(global, "setInterval");

      render(<ApprovalsPage />);

      expect(setIntervalSpy).not.toHaveBeenCalled();

      setIntervalSpy.mockRestore();
    });
  });

  describe("Approve Signal", () => {
    test("calls approveSignal with correct parameters", async () => {
      (approvalsService.fetchPendingApprovals as jest.Mock).mockResolvedValue(mockSignals);
      (approvalsService.approveSignal as jest.Mock).mockResolvedValue({
        id: "approval-1",
        status: "approved",
      });

      render(<ApprovalsPage />);

      await waitFor(() => {
        expect(screen.getByText("GOLD")).toBeInTheDocument();
      });

      const approveButton = screen.getByTestId("approve-button-approval-1");
      fireEvent.click(approveButton);

      await waitFor(() => {
        expect(approvalsService.approveSignal).toHaveBeenCalledWith(
          mockAuth.user.jwt_token,
          "approval-1"
        );
      });
    });

    test("removes card optimistically on approve", async () => {
      (approvalsService.fetchPendingApprovals as jest.Mock).mockResolvedValue(mockSignals);
      (approvalsService.approveSignal as jest.Mock).mockResolvedValue({
        id: "approval-1",
        status: "approved",
      });

      render(<ApprovalsPage />);

      await waitFor(() => {
        expect(screen.getByText("GOLD")).toBeInTheDocument();
      });

      const approveButton = screen.getByTestId("approve-button-approval-1");

      act(() => {
        fireEvent.click(approveButton);
      });

      // Card should be removed immediately (optimistic update)
      await waitFor(() => {
        expect(screen.queryByTestId("signal-card-approval-1")).not.toBeInTheDocument();
      });
    });

    test("shows error message on approve failure", async () => {
      (approvalsService.fetchPendingApprovals as jest.Mock).mockResolvedValue(mockSignals);
      (approvalsService.approveSignal as jest.Mock).mockRejectedValue(
        new Error("Failed to approve")
      );

      render(<ApprovalsPage />);

      await waitFor(() => {
        expect(screen.getByText("GOLD")).toBeInTheDocument();
      });

      const approveButton = screen.getByTestId("approve-button-approval-1");
      fireEvent.click(approveButton);

      await waitFor(() => {
        expect(require("@/lib/toastNotifications").showErrorToast).toHaveBeenCalledWith(
          expect.stringContaining("Failed to approve")
        );
      });
    });

    test("restores card on approve error", async () => {
      (approvalsService.fetchPendingApprovals as jest.Mock).mockResolvedValue(mockSignals);
      (approvalsService.approveSignal as jest.Mock).mockRejectedValue(
        new Error("Network error")
      );

      render(<ApprovalsPage />);

      await waitFor(() => {
        expect(screen.getByText("GOLD")).toBeInTheDocument();
      });

      const approveButton = screen.getByTestId("approve-button-approval-1");
      fireEvent.click(approveButton);

      await waitFor(() => {
        // Card should be restored after error
        expect(screen.getByText("GOLD")).toBeInTheDocument();
      });
    });


  });

  describe("Reject Signal", () => {
    test("calls rejectSignal with correct parameters", async () => {
      (approvalsService.fetchPendingApprovals as jest.Mock).mockResolvedValue(mockSignals);
      (approvalsService.rejectSignal as jest.Mock).mockResolvedValue({
        id: "approval-1",
        status: "rejected",
      });

      render(<ApprovalsPage />);

      await waitFor(() => {
        expect(screen.getByText("GOLD")).toBeInTheDocument();
      });

      const rejectButton = screen.getByTestId("reject-button-approval-1");
      fireEvent.click(rejectButton);

      await waitFor(() => {
        expect(approvalsService.rejectSignal).toHaveBeenCalledWith(
          mockAuth.user.jwt_token,
          "approval-1"
        );
      });
    });

    test("removes card optimistically on reject", async () => {
      (approvalsService.fetchPendingApprovals as jest.Mock).mockResolvedValue(mockSignals);
      (approvalsService.rejectSignal as jest.Mock).mockResolvedValue({
        id: "approval-1",
        status: "rejected",
      });

      render(<ApprovalsPage />);

      await waitFor(() => {
        expect(screen.getByText("GOLD")).toBeInTheDocument();
      });

      const rejectButton = screen.getByTestId("reject-button-approval-1");

      act(() => {
        fireEvent.click(rejectButton);
      });

      // Card should be removed immediately
      await waitFor(() => {
        expect(screen.queryByTestId("signal-card-approval-1")).not.toBeInTheDocument();
      });
    });

    test("shows error message on reject failure", async () => {
      (approvalsService.fetchPendingApprovals as jest.Mock).mockResolvedValue(mockSignals);
      (approvalsService.rejectSignal as jest.Mock).mockRejectedValue(
        new Error("Failed to reject")
      );

      render(<ApprovalsPage />);

      await waitFor(() => {
        expect(screen.getByText("GOLD")).toBeInTheDocument();
      });

      const rejectButton = screen.getByTestId("reject-button-approval-1");
      fireEvent.click(rejectButton);

      await waitFor(() => {
        expect(require("@/lib/toastNotifications").showErrorToast).toHaveBeenCalledWith(
          expect.stringContaining("Failed to reject")
        );
      });
    });
  });

  describe("State Management", () => {
    test("updates signal list when new signals arrive from polling", async () => {
      const initialSignals = [mockSignals[0]];
      const updatedSignals = mockSignals;

      (approvalsService.fetchPendingApprovals as jest.Mock)
        .mockResolvedValueOnce(initialSignals)
        .mockResolvedValueOnce(updatedSignals);

      render(<ApprovalsPage />);

      await waitFor(() => {
        expect(screen.getByText("GOLD")).toBeInTheDocument();
        expect(screen.queryByText("SILVER")).not.toBeInTheDocument();
      });

      // Trigger next poll
      act(() => {
        jest.advanceTimersByTime(5000);
      });

      await waitFor(() => {
        expect(screen.getByText("SILVER")).toBeInTheDocument();
      });
    });

    test("maintains signals across re-renders", async () => {
      (approvalsService.fetchPendingApprovals as jest.Mock).mockResolvedValue(mockSignals);

      const { rerender } = render(<ApprovalsPage />);

      await waitFor(() => {
        expect(screen.getByText("GOLD")).toBeInTheDocument();
      });

      // Force re-render
      rerender(<ApprovalsPage />);

      expect(screen.getByText("GOLD")).toBeInTheDocument();
      expect(screen.getByText("SILVER")).toBeInTheDocument();
    });
  });

  describe("Error States", () => {
    test("displays retry button on fetch error", async () => {
      (approvalsService.fetchPendingApprovals as jest.Mock).mockRejectedValue(
        new Error("Network error")
      );

      render(<ApprovalsPage />);

      await waitFor(() => {
        expect(screen.getByText(/retry|try again/i)).toBeInTheDocument();
      });
    });

    test("retries fetch on retry button click", async () => {
      (approvalsService.fetchPendingApprovals as jest.Mock)
        .mockRejectedValueOnce(new Error("Network error"))
        .mockResolvedValueOnce(mockSignals);

      render(<ApprovalsPage />);

      await waitFor(() => {
        expect(screen.getByText(/retry/i)).toBeInTheDocument();
      });

      const retryButton = screen.getByText(/retry/i);
      fireEvent.click(retryButton);

      await waitFor(() => {
        expect(screen.getByText("GOLD")).toBeInTheDocument();
      });
    });


  });

  describe("Multiple Actions", () => {
    test("handles approve then reject on remaining cards", async () => {
      (approvalsService.fetchPendingApprovals as jest.Mock).mockResolvedValue(mockSignals);
      (approvalsService.approveSignal as jest.Mock).mockResolvedValue({
        status: "approved",
      });
      (approvalsService.rejectSignal as jest.Mock).mockResolvedValue({
        status: "rejected",
      });

      render(<ApprovalsPage />);

      await waitFor(() => {
        expect(screen.getByText("GOLD")).toBeInTheDocument();
        expect(screen.getByText("SILVER")).toBeInTheDocument();
      });

      // Approve first
      const approveButton = screen.getByTestId("approve-button-approval-1");
      fireEvent.click(approveButton);

      await waitFor(() => {
        expect(screen.queryByText("GOLD")).not.toBeInTheDocument();
      });

      // Reject second
      const rejectButton = screen.getByTestId("reject-button-approval-2");
      fireEvent.click(rejectButton);

      await waitFor(() => {
        expect(screen.queryByText("SILVER")).not.toBeInTheDocument();
      });
    });

    test("handles rapid consecutive approvals", async () => {
      (approvalsService.fetchPendingApprovals as jest.Mock).mockResolvedValue(mockSignals);
      (approvalsService.approveSignal as jest.Mock).mockResolvedValue({
        status: "approved",
      });

      render(<ApprovalsPage />);

      await waitFor(() => {
        expect(screen.getByText("GOLD")).toBeInTheDocument();
      });

      // Click both buttons rapidly
      const approveButtons = screen.getAllByTestId(/approve-button/);

      act(() => {
        approveButtons.forEach(button => fireEvent.click(button));
      });

      await waitFor(() => {
        expect(approvalsService.approveSignal).toHaveBeenCalledTimes(approveButtons.length);
      });
    });
  });
});

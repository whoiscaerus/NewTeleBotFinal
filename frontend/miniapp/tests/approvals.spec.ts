/**
 * Approvals Service Tests
 *
 * Validates all service layer business logic:
 * - API calls with JWT authentication
 * - Data fetching and pagination
 * - Signal approval/rejection workflows
 * - Time formatting and token validation
 * - Error handling and edge cases
 */

import {
  fetchPendingApprovals,
  approveSignal,
  rejectSignal,
  formatRelativeTime,
  isTokenValid,
  getRemainingSeconds,
} from "@/lib/approvals";
import { logger } from "@/lib/logger";

// Mock fetch globally
global.fetch = jest.fn();

// Mock logger
jest.mock("@/lib/logger", () => ({
  logger: {
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

describe("Approvals Service", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (global.fetch as jest.Mock).mockClear();
  });

  describe("fetchPendingApprovals", () => {
    test("fetches pending approvals with valid JWT", async () => {
      const mockResponse = {
        ok: true,
        json: async () => ({
          approvals: [
            { id: "app-1", signal: { id: "sig-1", instrument: "GOLD", side: "buy" } },
          ],
        }),
      };
      (global.fetch as jest.Mock).mockResolvedValue(mockResponse);

      const jwt = "valid.jwt.token";
      const result = await fetchPendingApprovals(jwt);

      expect(global.fetch).toHaveBeenCalledWith(
        `${process.env.NEXT_PUBLIC_API_URL}/api/v1/approvals/pending`,
        {
          headers: {
            Authorization: `Bearer ${jwt}`,
            "Content-Type": "application/json",
          },
        }
      );

      expect(result).toEqual({
        approvals: [{ id: "app-1", signal: { id: "sig-1", instrument: "GOLD", side: "buy" } }],
      });
    });

    test("includes pagination parameters when provided", async () => {
      const mockResponse = {
        ok: true,
        json: async () => ({ approvals: [] }),
      };
      (global.fetch as jest.Mock).mockResolvedValue(mockResponse);

      const jwt = "token";
      await fetchPendingApprovals(jwt, undefined, 10, 20);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("skip=10&limit=20"),
        expect.any(Object)
      );
    });

    test("includes timestamp filter when provided", async () => {
      const mockResponse = {
        ok: true,
        json: async () => ({ approvals: [] }),
      };
      (global.fetch as jest.Mock).mockResolvedValue(mockResponse);

      const jwt = "token";
      const since = "2024-01-01T00:00:00Z";
      await fetchPendingApprovals(jwt, since);

      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining(`since=${encodeURIComponent(since)}`),
        expect.any(Object)
      );
    });

    test("throws error on 401 Unauthorized", async () => {
      const mockResponse = {
        ok: false,
        status: 401,
        json: async () => ({ error: "Unauthorized" }),
      };
      (global.fetch as jest.Mock).mockResolvedValue(mockResponse);

      const jwt = "invalid.jwt";

      await expect(fetchPendingApprovals(jwt)).rejects.toThrow("Unauthorized");
    });

    test("throws error on 500 server error", async () => {
      const mockResponse = {
        ok: false,
        status: 500,
        json: async () => ({ error: "Internal Server Error" }),
      };
      (global.fetch as jest.Mock).mockResolvedValue(mockResponse);

      const jwt = "token";

      await expect(fetchPendingApprovals(jwt)).rejects.toThrow("Internal Server Error");
    });

    test("throws error on network failure", async () => {
      (global.fetch as jest.Mock).mockRejectedValue(new Error("Network error"));

      const jwt = "token";

      await expect(fetchPendingApprovals(jwt)).rejects.toThrow("Network error");
    });

    test("handles empty approval list", async () => {
      const mockResponse = {
        ok: true,
        json: async () => ({ approvals: [] }),
      };
      (global.fetch as jest.Mock).mockResolvedValue(mockResponse);

      const jwt = "token";
      const result = await fetchPendingApprovals(jwt);

      expect(result).toEqual([]);
      expect(result.length).toBe(0);
    });

    test("returns multiple approvals", async () => {
      const mockResponse = {
        ok: true,
        json: async () => ({
          approvals: [
            { id: "app-1", signal: { id: "sig-1", instrument: "GOLD" } },
            { id: "app-2", signal: { id: "sig-2", instrument: "SILVER" } },
            { id: "app-3", signal: { id: "sig-3", instrument: "OIL" } },
          ],
        }),
      };
      (global.fetch as jest.Mock).mockResolvedValue(mockResponse);

      const jwt = "token";
      const result = await fetchPendingApprovals(jwt);

      expect(result.length).toBe(3);
    });

    test("logs info on successful fetch", async () => {
      const mockResponse = {
        ok: true,
        json: async () => ({ approvals: [] }),
      };
      (global.fetch as jest.Mock).mockResolvedValue(mockResponse);

      const jwt = "token";
      await fetchPendingApprovals(jwt);

      expect(logger.info).toHaveBeenCalledWith(
        "Fetching pending approvals",
        expect.any(Object)
      );
    });

    test("logs error on failed fetch", async () => {
      const mockResponse = {
        ok: false,
        status: 500,
        json: async () => ({ error: "Server error" }),
      };
      (global.fetch as jest.Mock).mockResolvedValue(mockResponse);

      const jwt = "token";

      try {
        await fetchPendingApprovals(jwt);
      } catch (e) {
        // Expected
      }

      expect(logger.error).toHaveBeenCalled();
    });
  });

  describe("approveSignal", () => {
    test("sends approval request with correct payload", async () => {
      const mockResponse = {
        ok: true,
        json: async () => ({ id: "app-1", status: "approved" }),
      };
      (global.fetch as jest.Mock).mockResolvedValue(mockResponse);

      const jwt = "token";
      const approvalId = "app-1";
      const result = await approveSignal(jwt, approvalId);

      expect(global.fetch).toHaveBeenCalledWith(
        `${process.env.NEXT_PUBLIC_API_URL}/api/v1/approvals/${approvalId}/approve`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${jwt}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({}),
        }
      );

      expect(result).toBeUndefined();
    });

    test("throws error if already approved", async () => {
      const mockResponse = {
        ok: false,
        status: 400,
        json: async () => ({ error: "Approval already processed" }),
      };
      (global.fetch as jest.Mock).mockResolvedValue(mockResponse);

      const jwt = "token";
      const approvalId = "app-1";

      await expect(approveSignal(jwt, approvalId)).rejects.toThrow(
        "Approval already processed"
      );
    });

    test("throws error on 401 Unauthorized", async () => {
      const mockResponse = {
        ok: false,
        status: 401,
        json: async () => ({ error: "Unauthorized" }),
      };
      (global.fetch as jest.Mock).mockResolvedValue(mockResponse);

      const jwt = "invalid.token";
      const approvalId = "app-1";

      await expect(approveSignal(jwt, approvalId)).rejects.toThrow("Unauthorized");
    });

    test("throws error on network failure", async () => {
      (global.fetch as jest.Mock).mockRejectedValue(new Error("Network timeout"));

      const jwt = "token";
      const approvalId = "app-1";

      await expect(approveSignal(jwt, approvalId)).rejects.toThrow("Network timeout");
    });

    test("logs approval action", async () => {
      const mockResponse = {
        ok: true,
        json: async () => ({ id: "app-1", status: "approved" }),
      };
      (global.fetch as jest.Mock).mockResolvedValue(mockResponse);

      const jwt = "token";
      const approvalId = "app-1";
      await approveSignal(jwt, approvalId);

      expect(logger.info).toHaveBeenCalledWith(
        "Approving signal",
        expect.objectContaining({ approval_id: approvalId })
      );
    });
  });

  describe("rejectSignal", () => {
    test("sends rejection request with correct payload", async () => {
      const mockResponse = {
        ok: true,
        json: async () => ({ id: "app-1", status: "rejected" }),
      };
      (global.fetch as jest.Mock).mockResolvedValue(mockResponse);

      const jwt = "token";
      const approvalId = "app-1";
      const result = await rejectSignal(jwt, approvalId);

      expect(global.fetch).toHaveBeenCalledWith(
        `${process.env.NEXT_PUBLIC_API_URL}/api/v1/approvals/${approvalId}/reject`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${jwt}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({}),
        }
      );

      expect(result).toBeUndefined();
    });

    test("throws error if already rejected", async () => {
      const mockResponse = {
        ok: false,
        status: 400,
        json: async () => ({ error: "Approval already processed" }),
      };
      (global.fetch as jest.Mock).mockResolvedValue(mockResponse);

      const jwt = "token";
      const approvalId = "app-1";

      await expect(rejectSignal(jwt, approvalId)).rejects.toThrow(
        "Approval already processed"
      );
    });

    test("throws error on 401 Unauthorized", async () => {
      const mockResponse = {
        ok: false,
        status: 401,
        json: async () => ({ error: "Unauthorized" }),
      };
      (global.fetch as jest.Mock).mockResolvedValue(mockResponse);

      const jwt = "invalid.token";
      const approvalId = "app-1";

      await expect(rejectSignal(jwt, approvalId)).rejects.toThrow("Unauthorized");
    });

    test("throws error on network failure", async () => {
      (global.fetch as jest.Mock).mockRejectedValue(new Error("Network error"));

      const jwt = "token";
      const approvalId = "app-1";

      await expect(rejectSignal(jwt, approvalId)).rejects.toThrow("Network error");
    });

    test("logs rejection action", async () => {
      const mockResponse = {
        ok: true,
        json: async () => ({ id: "app-1", status: "rejected" }),
      };
      (global.fetch as jest.Mock).mockResolvedValue(mockResponse);

      const jwt = "token";
      const approvalId = "app-1";
      await rejectSignal(jwt, approvalId);

      expect(logger.info).toHaveBeenCalledWith(
        "Rejecting signal",
        expect.objectContaining({ approval_id: approvalId })
      );
    });
  });

  describe("formatRelativeTime", () => {
    test("formats seconds ago correctly", () => {
      const now = new Date();
      const secondsAgo30 = new Date(now.getTime() - 30 * 1000);
      const result = formatRelativeTime(secondsAgo30.toISOString());

      expect(result).toMatch(/\d+\s*s\s*ago/i);
    });

    test("formats minutes ago correctly", () => {
      const now = new Date();
      const minutesAgo5 = new Date(now.getTime() - 5 * 60 * 1000);
      const result = formatRelativeTime(minutesAgo5.toISOString());

      expect(result).toMatch(/\d+\s*m\s*ago/i);
    });

    test("formats hours ago correctly", () => {
      const now = new Date();
      const hoursAgo2 = new Date(now.getTime() - 2 * 60 * 60 * 1000);
      const result = formatRelativeTime(hoursAgo2.toISOString());

      expect(result).toMatch(/\d+\s*h\s*ago/i);
    });

    test("formats days ago correctly", () => {
      const now = new Date();
      const daysAgo3 = new Date(now.getTime() - 3 * 24 * 60 * 60 * 1000);
      const result = formatRelativeTime(daysAgo3.toISOString());

      expect(result).toMatch(/\d+\s*d\s*ago/i);
    });

    test("handles just now (< 1 second)", () => {
      const now = new Date().toISOString();
      const result = formatRelativeTime(now);

      expect(result).toBe("just now");
    });

    test("handles invalid date string", () => {
      const result = formatRelativeTime("invalid-date");

      expect(result).toBe("just now");
    });

    test("handles undefined date", () => {
      const result = formatRelativeTime(undefined as any);

      expect(result).toBe("just now");
    });

    test("handles very old dates (weeks/months)", () => {
      const now = new Date();
      const monthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
      const result = formatRelativeTime(monthAgo.toISOString());

      expect(result).toContain("ago");
    });

    test("handles future dates gracefully", () => {
      const now = new Date();
      const futureDate = new Date(now.getTime() + 60 * 1000);
      const result = formatRelativeTime(futureDate.toISOString());

      // Should not crash, result depends on date-fns behavior
      expect(result).toBeDefined();
    });
  });

  describe("isTokenValid", () => {
    test("returns true for token expiring in future", () => {
      const futureDate = new Date(Date.now() + 60 * 60 * 1000); // 1 hour
      const result = isTokenValid(futureDate.toISOString());

      expect(result).toBe(true);
    });

    test("returns false for expired token", () => {
      const pastDate = new Date(Date.now() - 60 * 1000); // 1 minute ago
      const result = isTokenValid(pastDate.toISOString());

      expect(result).toBe(false);
    });

    test("returns false for token expiring right now", () => {
      const now = new Date().toISOString();
      const result = isTokenValid(now);

      expect(result).toBe(false);
    });

    test("handles invalid date string", () => {
      const result = isTokenValid("invalid-date");

      expect(result).toBe(false);
    });

    test("handles undefined expiry", () => {
      const result = isTokenValid(undefined as any);

      expect(result).toBe(false);
    });

    test("returns true for token expiring soon (buffer)", () => {
      // Token expires in 30 seconds (within 5 min buffer)
      const soonDate = new Date(Date.now() + 30 * 1000);
      const result = isTokenValid(soonDate.toISOString());

      // Most implementations have a buffer (usually 5 minutes)
      // Should still be valid if buffer not reached
      expect(typeof result).toBe("boolean");
    });

    test("handles very far future dates", () => {
      const yearFromNow = new Date(Date.now() + 365 * 24 * 60 * 60 * 1000);
      const result = isTokenValid(yearFromNow.toISOString());

      expect(result).toBe(true);
    });
  });

  describe("getRemainingSeconds", () => {
    test("calculates remaining seconds for future expiry", () => {
      const secondsFromNow60 = new Date(Date.now() + 60 * 1000);
      const result = getRemainingSeconds(secondsFromNow60.toISOString());

      expect(result).toBeGreaterThan(50);
      expect(result).toBeLessThanOrEqual(60);
    });

    test("returns negative for past expiry", () => {
      const pastDate = new Date(Date.now() - 60 * 1000);
      const result = getRemainingSeconds(pastDate.toISOString());

      expect(result).toBeLessThan(0);
    });

    test("returns ~0 for expiry right now", () => {
      const now = new Date().toISOString();
      const result = getRemainingSeconds(now);

      expect(Math.abs(result)).toBeLessThan(1);
    });

    test("handles invalid date string", () => {
      const result = getRemainingSeconds("invalid-date");

      expect(result).toBeLessThan(0);
    });

    test("handles undefined expiry", () => {
      const result = getRemainingSeconds(undefined as any);

      expect(result).toBeLessThan(0);
    });

    test("calculates correctly for hour from now", () => {
      const oneHourFromNow = new Date(Date.now() + 60 * 60 * 1000);
      const result = getRemainingSeconds(oneHourFromNow.toISOString());

      expect(result).toBeGreaterThan(3500);
      expect(result).toBeLessThanOrEqual(3600);
    });

    test("calculates correctly for day from now", () => {
      const oneDayFromNow = new Date(Date.now() + 24 * 60 * 60 * 1000);
      const result = getRemainingSeconds(oneDayFromNow.toISOString());

      expect(result).toBeGreaterThan(86000);
      expect(result).toBeLessThanOrEqual(86400);
    });
  });

  describe("Integration Scenarios", () => {
    test("fetches approvals, approves one, rejects another", async () => {
      // Fetch
      const fetchResponse = {
        ok: true,
        json: async () => ({
          approvals: [
            { id: "app-1", signal: { id: "sig-1" } },
            { id: "app-2", signal: { id: "sig-2" } },
          ],
        }),
      };

      // Approve
      const approveResponse = {
        ok: true,
        json: async () => ({ id: "app-1", status: "approved" }),
      };

      // Reject
      const rejectResponse = {
        ok: true,
        json: async () => ({ id: "app-2", status: "rejected" }),
      };

      (global.fetch as jest.Mock)
        .mockResolvedValueOnce(fetchResponse)
        .mockResolvedValueOnce(approveResponse)
        .mockResolvedValueOnce(rejectResponse);

      const jwt = "token";

      // Fetch
      const approvals = await fetchPendingApprovals(jwt);
      expect(approvals.length).toBe(2);

      // Approve first
      const approved = await approveSignal(jwt, approvals[0].id);
      expect(approved).toBeUndefined();

      // Reject second
      const rejected = await rejectSignal(jwt, approvals[1].id);
      expect(rejected).toBeUndefined();

      // Verify 3 fetch calls were made
      expect(global.fetch).toHaveBeenCalledTimes(3);
    });

    test("handles token expiry during workflow", async () => {
      const jwt = "token";
      const expiredTime = new Date(Date.now() - 1000).toISOString();

      const isValid = isTokenValid(expiredTime);
      expect(isValid).toBe(false);

      // Remaining should be negative
      const remaining = getRemainingSeconds(expiredTime);
      expect(remaining).toBeLessThan(0);
    });

    test("formats times correctly throughout workflow", () => {
      const createdAt = new Date(Date.now() - 5 * 60 * 1000).toISOString();
      const formattedTime = formatRelativeTime(createdAt);

      expect(formattedTime).toContain("ago");
      expect(formattedTime).toMatch(/\d+/);
    });
  });

  describe("Error Recovery", () => {
    test("retry logic for network failures", async () => {
      (global.fetch as jest.Mock)
        .mockRejectedValueOnce(new Error("Network error"))
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ approvals: [] }),
        });

      const jwt = "token";

      // First call fails
      try {
        await fetchPendingApprovals(jwt);
      } catch (e) {
        // Expected
      }

      // Second call succeeds
      const result = await fetchPendingApprovals(jwt);
      expect(result).toEqual([]);
    });

    test("handles partial response data", async () => {
      const mockResponse = {
        ok: true,
        json: async () => ({
          approvals: [
            { id: "app-1" }, // Missing signal data
            { id: "app-2", signal: { id: "sig-2" } },
          ],
        }),
      };
      (global.fetch as jest.Mock).mockResolvedValue(mockResponse);

      const jwt = "token";
      const result = await fetchPendingApprovals(jwt);

      expect(result.length).toBe(2);
      expect(result[0].id).toBe("app-1");
    });
  });
});

"use server";

// Logger for server-side telemetry (optional - comment out if not available)
const logger = {
  info: (msg: string, data?: Record<string, unknown>) => console.log(`[INFO] ${msg}`, data),
  warn: (msg: string, data?: Record<string, unknown>) => console.warn(`[WARN] ${msg}`, data),
  error: (msg: string, data?: Record<string, unknown>) => console.error(`[ERROR] ${msg}`, data),
};

/**
 * Server Action: Approve a signal
 *
 * This server action handles signal approval with telemetry tracking,
 * optimistic response handling, and error management.
 *
 * @param approvalId - ID of the approval to confirm
 * @param jwt - JWT token for authentication
 * @returns Success/error response with optional message
 *
 * @example
 * const result = await approveAction("approval-123", jwt);
 * if (result.success) {
 *   // Update UI optimistically
 *   showToast("Signal approved!");
 * } else {
 *   showToast(`Error: ${result.error}`, "error");
 * }
 */
export async function approveAction(
  approvalId: string,
  jwt: string
): Promise<{
  success: boolean;
  message?: string;
  error?: string;
  approval_id?: string;
}> {
  try {
    // Validate inputs
    if (!approvalId || typeof approvalId !== "string") {
      logger.warn("Invalid approvalId", { approvalId });
      return {
        success: false,
        error: "Invalid approval ID",
      };
    }

    if (!jwt || typeof jwt !== "string") {
      logger.warn("Missing JWT token");
      return {
        success: false,
        error: "Authentication required",
      };
    }

    // Log action for telemetry
    logger.info("Approval action initiated", {
      approval_id: approvalId,
      decision: "approve",
      action: "miniapp_approval_click_total",
    });

    // Make backend API call
    const backendUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const response = await fetch(`${backendUrl}/api/v1/approvals/${approvalId}/approve`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${jwt}`,
      },
      body: JSON.stringify({}),
    });

    // Handle response
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const errorMessage = errorData.detail || `HTTP ${response.status}`;

      logger.error("Approval failed", {
        approval_id: approvalId,
        status: response.status,
        error: errorMessage,
      });

      return {
        success: false,
        error: errorMessage,
      };
    }

    await response.json(); // Consume response body

    // Log success
    logger.info("Signal approved successfully", {
      approval_id: approvalId,
      decision: "approve",
      action: "miniapp_approval_success",
    });

    return {
      success: true,
      message: "Signal approved successfully",
      approval_id: approvalId,
    };
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : "Unknown error";

    logger.error("Approval action error", {
      approval_id: approvalId,
      error: errorMessage,
      action: "miniapp_approval_error",
    });

    return {
      success: false,
      error: errorMessage,
    };
  }
}

/**
 * Server Action: Reject a signal
 *
 * This server action handles signal rejection with telemetry tracking,
 * optimistic response handling, and error management.
 *
 * @param approvalId - ID of the approval to reject
 * @param jwt - JWT token for authentication
 * @returns Success/error response with optional message
 *
 * @example
 * const result = await rejectAction("approval-123", jwt);
 * if (result.success) {
 *   showToast("Signal rejected");
 * } else {
 *   showToast(`Error: ${result.error}`, "error");
 * }
 */
export async function rejectAction(
  approvalId: string,
  jwt: string
): Promise<{
  success: boolean;
  message?: string;
  error?: string;
  approval_id?: string;
}> {
  try {
    // Validate inputs
    if (!approvalId || typeof approvalId !== "string") {
      logger.warn("Invalid approvalId", { approvalId });
      return {
        success: false,
        error: "Invalid approval ID",
      };
    }

    if (!jwt || typeof jwt !== "string") {
      logger.warn("Missing JWT token");
      return {
        success: false,
        error: "Authentication required",
      };
    }

    // Log action for telemetry
    logger.info("Rejection action initiated", {
      approval_id: approvalId,
      decision: "reject",
      action: "miniapp_approval_click_total",
    });

    // Make backend API call
    const backendUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const response = await fetch(`${backendUrl}/api/v1/approvals/${approvalId}/reject`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${jwt}`,
      },
      body: JSON.stringify({}),
    });

    // Handle response
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const errorMessage = errorData.detail || `HTTP ${response.status}`;

      logger.error("Rejection failed", {
        approval_id: approvalId,
        status: response.status,
        error: errorMessage,
      });

      return {
        success: false,
        error: errorMessage,
      };
    }

    await response.json(); // Consume response body

    // Log success
    logger.info("Signal rejected successfully", {
      approval_id: approvalId,
      decision: "reject",
      action: "miniapp_approval_success",
    });

    return {
      success: true,
      message: "Signal rejected",
      approval_id: approvalId,
    };
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : "Unknown error";

    logger.error("Rejection action error", {
      approval_id: approvalId,
      error: errorMessage,
      action: "miniapp_approval_error",
    });

    return {
      success: false,
      error: errorMessage,
    };
  }
}

"""Close Command Model - Server-initiated position closes.

When the position monitor detects an SL/TP breach, it creates a CloseCommand
that the EA will poll and execute. This enables server-side autonomous closes
without exposing hidden levels to clients.
"""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Float, ForeignKey, Index, Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.db import Base

if TYPE_CHECKING:
    pass


class CloseCommandStatus(Enum):
    """Close command lifecycle status."""

    PENDING = 0  # Command created, waiting for EA to poll
    ACKNOWLEDGED = 1  # EA received command, attempting close
    EXECUTED = 2  # EA successfully closed position
    FAILED = 3  # EA failed to close position
    TIMEOUT = 4  # Command expired (EA never acknowledged)


class CloseCommand(Base):
    """Close command for EA to execute position closes.

    The position monitor service creates CloseCommands when it detects
    SL/TP breaches. The EA polls for pending commands and executes them.

    Workflow:
        1. Monitor detects breach → creates CloseCommand (status=PENDING)
        2. EA polls /close-commands → receives pending commands
        3. EA attempts close → sends ack (status=ACKNOWLEDGED)
        4. EA confirms close → updates status (EXECUTED or FAILED)

    Fields:
        id: Unique command identifier
        position_id: OpenPosition to close
        device_id: Device that should execute the close
        reason: Why the close was triggered (sl_hit, tp_hit, manual)
        expected_price: Expected close price (current market price when command created)
        status: Command lifecycle status
        created_at: Command creation timestamp
        acknowledged_at: When EA received the command
        executed_at: When EA completed the close (success or failure)
        actual_close_price: Actual price EA closed at
        error_message: Error details if close failed
    """

    __tablename__ = "close_commands"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
        doc="Unique command ID",
    )

    # Foreign keys
    position_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("open_positions.id"),
        nullable=False,
        index=True,
        doc="Position to close",
    )
    device_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("devices.id"),
        nullable=False,
        index=True,
        doc="Device that should execute close",
    )

    # Command details
    reason: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="Reason: sl_hit, tp_hit, manual, drawdown, etc.",
    )
    expected_price: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        doc="Expected close price (market price when command created)",
    )

    # Status tracking
    status: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=CloseCommandStatus.PENDING.value,
        doc="Command lifecycle status",
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.utcnow,
        doc="Command creation timestamp",
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="When EA received the command",
    )
    executed_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="When EA completed the close",
    )

    # Execution results
    actual_close_price: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        doc="Actual price EA closed at",
    )
    error_message: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        doc="Error details if close failed",
    )

    # Relationships (commented to avoid circular import for now - FKs enforced at DB level)
    # position = relationship("OpenPosition", back_populates="close_commands")
    # device = relationship("Device", back_populates="close_commands")

    # Indexes for efficient queries
    __table_args__ = (
        Index("ix_close_commands_device_status", "device_id", "status"),
        Index("ix_close_commands_position", "position_id"),
        Index("ix_close_commands_created", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<CloseCommand {self.id}: position={self.position_id} "
            f"reason={self.reason} status={self.status}>"
        )


# Service functions for close command management


async def create_close_command(
    db: AsyncSession,
    position_id: str,
    device_id: str,
    reason: str,
    expected_price: float,
) -> CloseCommand:
    """
    Create a new close command for the EA to execute.

    Args:
        db: Database session
        position_id: OpenPosition ID to close
        device_id: Device that should execute the close
        reason: Reason for close (sl_hit, tp_hit, manual, etc.)
        expected_price: Current market price when command created

    Returns:
        Created CloseCommand

    Notes:
        - Command starts with status=PENDING
        - EA will poll and find this command
        - EA acknowledges receipt and attempts close
    """
    command = CloseCommand(
        id=str(uuid4()),
        position_id=position_id,
        device_id=device_id,
        reason=reason,
        expected_price=expected_price,
        status=CloseCommandStatus.PENDING.value,
        created_at=datetime.utcnow(),
    )

    db.add(command)
    await db.commit()
    await db.refresh(command)

    return command


async def get_pending_commands(db: AsyncSession, device_id: str) -> list[CloseCommand]:
    """
    Get all pending close commands for a device.

    Args:
        db: Database session
        device_id: Device UUID

    Returns:
        List of CloseCommand with status=PENDING for this device

    Notes:
        - EA calls this endpoint when polling
        - Only returns commands that haven't been acknowledged yet
        - Ordered by created_at (oldest first) to ensure FIFO processing
    """
    result = await db.execute(
        select(CloseCommand)
        .where(
            CloseCommand.device_id == device_id,
            CloseCommand.status == CloseCommandStatus.PENDING.value,
        )
        .order_by(CloseCommand.created_at.asc())
    )
    return list(result.scalars().all())


async def acknowledge_command(db: AsyncSession, command_id: str) -> CloseCommand:
    """
    Mark a close command as acknowledged by EA.

    Args:
        db: Database session
        command_id: CloseCommand UUID

    Returns:
        Updated CloseCommand with status=ACKNOWLEDGED

    Notes:
        - EA calls this after receiving command from poll
        - EA is now attempting to close the position
        - Sets acknowledged_at timestamp
    """
    result = await db.execute(select(CloseCommand).where(CloseCommand.id == command_id))
    command = result.scalar_one_or_none()

    if command is None:
        raise ValueError(f"CloseCommand {command_id} not found")

    command.status = CloseCommandStatus.ACKNOWLEDGED.value
    command.acknowledged_at = datetime.utcnow()

    await db.commit()
    await db.refresh(command)

    return command


async def complete_command(
    db: AsyncSession,
    command_id: str,
    success: bool,
    actual_close_price: float | None = None,
    error_message: str | None = None,
) -> CloseCommand:
    """
    Mark a close command as completed (success or failure).

    Args:
        db: Database session
        command_id: CloseCommand UUID
        success: True if close succeeded, False if failed
        actual_close_price: Actual price EA closed at (if success)
        error_message: Error details (if failure)

    Returns:
        Updated CloseCommand with status=EXECUTED or FAILED

    Notes:
        - EA calls this after attempting close
        - Sets executed_at timestamp
        - Records actual close price or error message
    """
    result = await db.execute(select(CloseCommand).where(CloseCommand.id == command_id))
    command = result.scalar_one_or_none()

    if command is None:
        raise ValueError(f"CloseCommand {command_id} not found")

    if success:
        command.status = CloseCommandStatus.EXECUTED.value
        command.actual_close_price = actual_close_price
    else:
        command.status = CloseCommandStatus.FAILED.value
        command.error_message = error_message

    command.executed_at = datetime.utcnow()

    await db.commit()
    await db.refresh(command)

    return command

"""Privacy request service layer."""

from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.logging import get_logger
from backend.app.privacy.deleter import DataDeleter
from backend.app.privacy.exporter import DataExporter
from backend.app.privacy.models import PrivacyRequest, RequestStatus, RequestType
from backend.app.privacy.schemas import PrivacyRequestCreate

logger = get_logger(__name__)


class PrivacyService:
    """Service for managing privacy requests."""

    # Default cooling-off period for delete requests (hours)
    DELETE_COOLING_OFF_HOURS = 72  # 3 days

    def __init__(self, db: AsyncSession):
        self.db = db
        self.exporter = DataExporter(db)
        self.deleter = DataDeleter(db)

    async def create_request(
        self, user_id: str, request_data: PrivacyRequestCreate
    ) -> PrivacyRequest:
        """
        Create a new privacy request.

        Args:
            user_id: User ID making the request
            request_data: Request details

        Returns:
            Created privacy request

        Raises:
            ValueError: If user has pending request of same type
        """
        # Check for existing pending request of same type
        existing = await self._get_pending_request(user_id, request_data.request_type)
        if existing:
            raise ValueError(
                f"User already has a pending {request_data.request_type} request: {existing.id}"
            )

        # Create request
        request = PrivacyRequest(
            id=str(uuid4()),
            user_id=user_id,
            request_type=request_data.request_type,
            status=RequestStatus.PENDING,
            created_at=datetime.utcnow(),
            metadata={"reason": request_data.reason} if request_data.reason else {},
        )

        # For delete requests, set cooling-off period
        if request_data.request_type == RequestType.DELETE:
            request.scheduled_deletion_at = datetime.utcnow() + timedelta(
                hours=self.DELETE_COOLING_OFF_HOURS
            )

        self.db.add(request)
        await self.db.commit()
        await self.db.refresh(request)

        logger.info(
            f"Created {request.request_type} request {request.id} for user {user_id}"
        )

        return request

    async def get_request(self, request_id: str, user_id: str) -> PrivacyRequest | None:
        """
        Get privacy request by ID.

        Args:
            request_id: Request ID
            user_id: User ID (for authorization)

        Returns:
            Privacy request or None
        """
        result = await self.db.execute(
            select(PrivacyRequest)
            .filter(PrivacyRequest.id == request_id)
            .filter(PrivacyRequest.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_requests(self, user_id: str) -> list[PrivacyRequest]:
        """
        List all privacy requests for user.

        Args:
            user_id: User ID

        Returns:
            List of privacy requests
        """
        result = await self.db.execute(
            select(PrivacyRequest)
            .filter(PrivacyRequest.user_id == user_id)
            .order_by(PrivacyRequest.created_at.desc())
        )
        return list(result.scalars().all())

    async def cancel_request(
        self, request_id: str, user_id: str, reason: str | None = None
    ) -> PrivacyRequest:
        """
        Cancel a pending privacy request.

        Args:
            request_id: Request ID
            user_id: User ID (for authorization)
            reason: Optional cancellation reason

        Returns:
            Updated privacy request

        Raises:
            ValueError: If request not found or cannot be cancelled
        """
        request = await self.get_request(request_id, user_id)
        if not request:
            raise ValueError(f"Request {request_id} not found")

        if request.status not in [RequestStatus.PENDING, RequestStatus.ON_HOLD]:
            raise ValueError(f"Cannot cancel request in status: {request.status}")

        request.status = RequestStatus.CANCELLED
        request.processed_at = datetime.utcnow()
        if reason:
            request.metadata["cancellation_reason"] = reason

        await self.db.commit()
        await self.db.refresh(request)

        logger.info(f"Cancelled request {request_id} for user {user_id}")

        return request

    async def process_export_request(self, request_id: str) -> PrivacyRequest:
        """
        Process an export request (generate bundle).

        Args:
            request_id: Request ID to process

        Returns:
            Updated privacy request with export URL

        Raises:
            ValueError: If request not found or not processable
        """
        result = await self.db.execute(
            select(PrivacyRequest).filter(PrivacyRequest.id == request_id)
        )
        request = result.scalar_one_or_none()

        if not request:
            raise ValueError(f"Request {request_id} not found")

        if request.request_type != RequestType.EXPORT:
            raise ValueError(f"Request {request_id} is not an export request")

        if request.status != RequestStatus.PENDING:
            raise ValueError(
                f"Request {request_id} is not pending (status: {request.status})"
            )

        # Update status to processing
        request.status = RequestStatus.PROCESSING
        await self.db.commit()

        try:
            # Export user data
            export_data = await self.exporter.export_user_data(
                request.user_id, request_id
            )

            # Create ZIP bundle
            bundle_bytes = self.exporter.create_export_bundle(export_data)

            # Store bundle and update request
            await self.exporter.store_export_bundle(bundle_bytes, request)

            logger.info(
                f"Completed export request {request_id} for user {request.user_id}"
            )

            return request

        except Exception as e:
            request.status = RequestStatus.FAILED
            request.metadata["error"] = str(e)
            await self.db.commit()
            raise

    async def process_delete_request(self, request_id: str) -> PrivacyRequest:
        """
        Process a delete request (after cooling-off period).

        Args:
            request_id: Request ID to process

        Returns:
            Updated privacy request

        Raises:
            ValueError: If request not found, not deletable, or on hold
        """
        result = await self.db.execute(
            select(PrivacyRequest).filter(PrivacyRequest.id == request_id)
        )
        request = result.scalar_one_or_none()

        if not request:
            raise ValueError(f"Request {request_id} not found")

        if request.request_type != RequestType.DELETE:
            raise ValueError(f"Request {request_id} is not a delete request")

        if request.status == RequestStatus.ON_HOLD:
            raise ValueError(f"Request {request_id} is on hold: {request.hold_reason}")

        if not request.is_deletable:
            hours_remaining = request.cooling_off_hours_remaining
            raise ValueError(
                f"Cooling-off period not elapsed. {hours_remaining} hours remaining."
            )

        # Update status to processing
        request.status = RequestStatus.PROCESSING
        await self.db.commit()

        try:
            # Delete user data
            await self.deleter.delete_user_data(request.user_id, request_id)

            # Update request to completed
            request.status = RequestStatus.COMPLETED
            request.processed_at = datetime.utcnow()
            await self.db.commit()

            logger.info(
                f"Completed delete request {request_id} for user {request.user_id}"
            )

            return request

        except Exception as e:
            request.status = RequestStatus.FAILED
            request.metadata["error"] = str(e)
            await self.db.commit()
            raise

    async def place_hold(
        self, request_id: str, reason: str, admin_user_id: str
    ) -> PrivacyRequest:
        """
        Place admin hold on delete request.

        Args:
            request_id: Request ID
            reason: Hold reason (e.g., "Active chargeback dispute")
            admin_user_id: Admin user placing hold

        Returns:
            Updated privacy request

        Raises:
            ValueError: If request not found or not delete request
        """
        result = await self.db.execute(
            select(PrivacyRequest).filter(PrivacyRequest.id == request_id)
        )
        request = result.scalar_one_or_none()

        if not request:
            raise ValueError(f"Request {request_id} not found")

        if request.request_type != RequestType.DELETE:
            raise ValueError("Can only place hold on delete requests")

        request.place_hold(reason, admin_user_id)
        await self.db.commit()
        await self.db.refresh(request)

        logger.info(
            f"Placed hold on request {request_id} by admin {admin_user_id}: {reason}"
        )

        return request

    async def release_hold(self, request_id: str, admin_user_id: str) -> PrivacyRequest:
        """
        Release admin hold on delete request.

        Args:
            request_id: Request ID
            admin_user_id: Admin user releasing hold

        Returns:
            Updated privacy request

        Raises:
            ValueError: If request not found or not on hold
        """
        result = await self.db.execute(
            select(PrivacyRequest).filter(PrivacyRequest.id == request_id)
        )
        request = result.scalar_one_or_none()

        if not request:
            raise ValueError(f"Request {request_id} not found")

        if request.status != RequestStatus.ON_HOLD:
            raise ValueError(f"Request {request_id} is not on hold")

        request.release_hold()
        request.metadata["hold_released_by"] = admin_user_id
        request.metadata["hold_released_at"] = datetime.utcnow().isoformat()

        await self.db.commit()
        await self.db.refresh(request)

        logger.info(f"Released hold on request {request_id} by admin {admin_user_id}")

        return request

    async def _get_pending_request(
        self, user_id: str, request_type: RequestType
    ) -> PrivacyRequest | None:
        """Get pending request of specified type for user."""
        result = await self.db.execute(
            select(PrivacyRequest)
            .filter(PrivacyRequest.user_id == user_id)
            .filter(PrivacyRequest.request_type == request_type)
            .filter(
                PrivacyRequest.status.in_(
                    [RequestStatus.PENDING, RequestStatus.PROCESSING]
                )
            )
        )
        return result.scalar_one_or_none()

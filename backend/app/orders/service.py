"""Order service for order lifecycle management."""

import logging
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.orders.models import Order, OrderItem

logger = logging.getLogger(__name__)

# Order status codes
ORDER_PENDING = 0
ORDER_COMPLETED = 1
ORDER_FAILED = 2
ORDER_CANCELLED = 3

STATUS_NAMES = {
    ORDER_PENDING: "pending",
    ORDER_COMPLETED: "completed",
    ORDER_FAILED: "failed",
    ORDER_CANCELLED: "cancelled",
}


class OrderService:
    """Service for managing orders and order lifecycle."""

    def __init__(self, db: AsyncSession):
        """Initialize order service.

        Args:
            db: Database session
        """
        self.db = db

    async def create_order(
        self,
        user_id: str,
        product_tier_id: str,
        base_price: float,
        final_price: float,
        currency: str = "GBP",
        quantity: int = 1,
        notes: str | None = None,
    ) -> Order:
        """Create a new order.

        Args:
            user_id: User ID
            product_tier_id: Product tier ID
            base_price: Price before markups
            final_price: Final price after markups/discounts
            currency: Currency code (default 'GBP')
            quantity: Number of units (default 1)
            notes: Optional notes

        Returns:
            Created Order

        Raises:
            ValueError: If validation fails
        """
        try:
            if final_price < 0:
                raise ValueError("Final price cannot be negative")

            order = Order(
                id=str(uuid4()),
                user_id=user_id,
                product_tier_id=product_tier_id,
                quantity=quantity,
                base_price=base_price,
                final_price=final_price,
                currency=currency,
                status=ORDER_PENDING,
                notes=notes,
            )

            self.db.add(order)
            await self.db.commit()
            await self.db.refresh(order)

            logger.info(
                f"Created order: {order.id}",
                extra={
                    "order_id": order.id,
                    "user_id": user_id,
                    "amount": final_price,
                    "currency": currency,
                },
            )

            return order

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error creating order: {e}", exc_info=True)
            raise

    async def add_order_item(
        self,
        order_id: str,
        product_tier_id: str,
        unit_price: float,
        quantity: int = 1,
    ) -> OrderItem:
        """Add item to order.

        Args:
            order_id: Order ID
            product_tier_id: Product tier ID
            unit_price: Price per unit
            quantity: Number of units

        Returns:
            Created OrderItem
        """
        try:
            total_price = unit_price * quantity

            item = OrderItem(
                id=str(uuid4()),
                order_id=order_id,
                product_tier_id=product_tier_id,
                quantity=quantity,
                unit_price=unit_price,
                total_price=total_price,
            )

            self.db.add(item)
            await self.db.commit()
            await self.db.refresh(item)

            logger.info(
                f"Added order item: {item.id}",
                extra={
                    "order_id": order_id,
                    "product_tier_id": product_tier_id,
                    "quantity": quantity,
                },
            )

            return item

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error adding order item: {e}", exc_info=True)
            raise

    async def get_order(self, order_id: str) -> Order | None:
        """Get order by ID.

        Args:
            order_id: Order ID

        Returns:
            Order or None if not found
        """
        try:
            query = (
                select(Order)
                .where(Order.id == order_id)
                .options(selectinload(Order.items))
            )
            result = await self.db.execute(query)
            order = result.scalars().first()
            return order
        except Exception as e:
            logger.error(f"Error getting order {order_id}: {e}", exc_info=True)
            raise

    async def get_user_orders(
        self,
        user_id: str,
        status: int | None = None,
        limit: int = 20,
    ) -> list[Order]:
        """Get orders for user.

        Args:
            user_id: User ID
            status: Filter by status (optional)
            limit: Max results (default 20)

        Returns:
            List of orders for user
        """
        try:
            query = select(Order).where(Order.user_id == user_id)

            if status is not None:
                query = query.where(Order.status == status)

            query = (
                query.order_by(desc(Order.created_at))
                .limit(limit)
                .options(selectinload(Order.items))
            )

            result = await self.db.execute(query)
            orders = list(result.scalars().unique().all())

            logger.info(
                f"Loaded {len(orders)} orders for user {user_id}",
                extra={"user_id": user_id, "count": len(orders)},
            )

            return orders

        except Exception as e:
            logger.error(
                f"Error getting orders for user {user_id}: {e}",
                exc_info=True,
            )
            raise

    async def update_order_status(
        self,
        order_id: str,
        new_status: int,
        transaction_id: str | None = None,
        payment_method: str | None = None,
    ) -> Order:
        """Update order status.

        Args:
            order_id: Order ID
            new_status: New status code
            transaction_id: Optional transaction ID
            payment_method: Optional payment method

        Returns:
            Updated Order

        Raises:
            ValueError: If order not found
        """
        try:
            order = await self.get_order(order_id)
            if not order:
                raise ValueError(f"Order not found: {order_id}")

            order.status = new_status
            if transaction_id:
                order.transaction_id = transaction_id
            if payment_method:
                order.payment_method = payment_method

            self.db.add(order)
            await self.db.commit()
            await self.db.refresh(order)

            status_name = STATUS_NAMES.get(new_status, str(new_status))
            logger.info(
                f"Updated order status to {status_name}",
                extra={
                    "order_id": order_id,
                    "status": new_status,
                    "transaction_id": transaction_id,
                },
            )

            return order

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating order status: {e}", exc_info=True)
            raise

    async def cancel_order(self, order_id: str, reason: str | None = None) -> Order:
        """Cancel an order.

        Args:
            order_id: Order ID
            reason: Optional cancellation reason

        Returns:
            Cancelled Order
        """
        try:
            order = await self.get_order(order_id)
            if not order:
                raise ValueError(f"Order not found: {order_id}")

            if order.status == ORDER_CANCELLED:
                logger.warning(f"Order already cancelled: {order_id}")
                return order

            order.status = ORDER_CANCELLED
            order.notes = reason or ""

            self.db.add(order)
            await self.db.commit()
            await self.db.refresh(order)

            logger.info(
                f"Cancelled order: {order_id}",
                extra={"order_id": order_id, "reason": reason},
            )

            return order

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error cancelling order: {e}", exc_info=True)
            raise

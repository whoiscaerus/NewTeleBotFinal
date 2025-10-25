"""Order database models for tracking purchases."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String

from backend.app.core.db import Base


class Order(Base):
    """Order for product tier purchase.

    Tracks subscription orders with pricing and payment status.
    """

    __tablename__ = "orders"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False, index=True)  # Foreign key to users.id
    product_tier_id = Column(
        String(36), nullable=False
    )  # Foreign key to product_tiers.id
    quantity = Column(Integer, nullable=False, default=1)
    base_price = Column(Float, nullable=False)  # Price before markups
    final_price = Column(Float, nullable=False)  # Price after markups/discounts
    currency = Column(String(3), nullable=False, default="GBP")
    status = Column(
        Integer, nullable=False, default=0
    )  # 0=pending, 1=completed, 2=failed, 3=cancelled
    payment_method = Column(String(20), nullable=True)  # 'stripe', 'telegram_stars'
    transaction_id = Column(String(255), nullable=True)  # Payment processor ID
    notes = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_orders_user", "user_id"),
        Index("ix_orders_user_created", "user_id", "created_at"),
        Index("ix_orders_status", "status"),
        Index("ix_orders_transaction_id", "transaction_id"),
    )

    def __repr__(self) -> str:
        return f"<Order {self.id}: {self.final_price} {self.currency} (status={self.status})>"


class OrderItem(Base):
    """Individual item in an order.

    Links order to product tier with pricing.
    """

    __tablename__ = "order_items"

    id = Column(String(36), primary_key=True)
    order_id = Column(String(36), ForeignKey("orders.id"), nullable=False)
    product_tier_id = Column(
        String(36), nullable=False
    )  # Foreign key to product_tiers.id
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Float, nullable=False)
    total_price = Column(Float, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (Index("ix_order_items_order", "order_id"),)

    def __repr__(self) -> str:
        return f"<OrderItem {self.id}: qty={self.quantity} £{self.total_price}>"

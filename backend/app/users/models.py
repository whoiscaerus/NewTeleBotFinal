"""User models."""

from sqlalchemy import Column, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class User(Base):
    """User model."""

    __tablename__ = "users"

    id = Column(String, primary_key=True)
    email = Column(String, nullable=False, unique=True)
    username = Column(String)
    status = Column(String, default="active")

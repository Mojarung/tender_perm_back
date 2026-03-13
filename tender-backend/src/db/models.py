"""SQLAlchemy ORM models for STE catalog and Contracts."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from src.db.session import Base


class STECatalog(Base):
    """STE (Стандартная Товарная Единица) catalog item."""

    __tablename__ = "ste_catalog"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ste_id = Column(Integer, nullable=False, index=True, unique=True)
    name = Column(String, nullable=False)
    category = Column(String, nullable=True)
    manufacturer = Column(String, nullable=True)
    raw_characteristics = Column(Text, nullable=True)
    parsed_characteristics = Column(JSONB, nullable=True)
    embedding = Column(Vector(384), nullable=True)

    __table_args__ = (
        Index(
            "ix_ste_embedding_hnsw",
            embedding,
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    def __repr__(self) -> str:
        return f"<STECatalog(ste_id={self.ste_id}, name='{self.name}')>"


class Contract(Base):
    """Contract record linked to an STE item."""

    __tablename__ = "contracts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id = Column(Integer, nullable=False, index=True)
    ste_id = Column(Integer, nullable=False, index=True)
    purchase_name = Column(String, nullable=True)
    ste_position_name = Column(String, nullable=True)
    quantity = Column(Numeric, nullable=True)
    unit = Column(String, nullable=True)
    price_per_unit = Column(Numeric, nullable=True)
    purchase_method = Column(String, nullable=True)
    initial_contract_cost = Column(Numeric, nullable=True)
    final_contract_cost = Column(Numeric, nullable=True)
    discount_percent = Column(Numeric, nullable=True)
    contract_date = Column(DateTime, nullable=True, index=True)
    customer_inn = Column(String, nullable=True)
    customer_region = Column(String, nullable=True)
    supplier_inn = Column(String, nullable=True)
    supplier_region = Column(String, nullable=True)
    vat_rate = Column(String, nullable=True)

    def __repr__(self) -> str:
        return f"<Contract(contract_id={self.contract_id}, ste_id={self.ste_id})>"

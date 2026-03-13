from sqlalchemy import Column, String, Numeric, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from pgvector.sqlalchemy import Vector
from core.database import Base
import uuid

class SteCatalog(Base):
    __tablename__ = "ste_catalog"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ste_id = Column(String, index=True, unique=True, nullable=False)
    name = Column(String, nullable=False)
    category = Column(String)
    manufacturer = Column(String)
    raw_characteristics = Column(Text)
    parsed_characteristics = Column(JSONB)
    embedding = Column(Vector(384))

class Contract(Base):
    __tablename__ = "contracts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id = Column(String, index=True, nullable=False)
    ste_id = Column(String, ForeignKey("ste_catalog.ste_id"), index=True, nullable=False)
    purchase_name = Column(String)
    quantity = Column(Numeric)
    price_per_unit = Column(Numeric, nullable=False)
    contract_date = Column(DateTime, index=True)
    customer_region = Column(String)
    supplier_region = Column(String)
    vat_rate = Column(String)

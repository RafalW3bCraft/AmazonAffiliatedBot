"""SQLAlchemy 2.x sync storage for the commerce domain.

Supports postgresql:// and sqlite:/// URLs from COMMERCE_DATABASE_URL.
Payment storage must be durable: an empty URL or 'memory' raises RuntimeError.
sqlite gets create_all on init; postgres applies the idempotent DDL from
migrations/001_commerce.sql on init.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .exceptions import DuplicateCapture, DuplicateRequest, InvalidStateTransition
from .schemas import CartQuoteData, CatalogProduct, QuoteLine

_MIGRATION_SQL = Path(__file__).resolve().parent.parent / "migrations" / "001_commerce.sql"


class Base(DeclarativeBase):
    metadata = MetaData()


class MerchantProduct(Base):
    __tablename__ = "merchant_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    stock: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="MERCHANT")
    rights_evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class CartQuote(Base):
    __tablename__ = "cart_quotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    quote_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    items_json: Mapped[str] = mapped_column(JSON, nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="OPEN")
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class CheckoutAttempt(Base):
    __tablename__ = "checkout_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cart_quote_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cart_quotes.id"), nullable=False
    )
    buyer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    paypal_order_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PaymentCapture(Base):
    __tablename__ = "payment_captures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    checkout_attempt_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("checkout_attempts.id"), nullable=False
    )
    paypal_capture_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime)


class PaymentEvent(Base):
    __tablename__ = "payment_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_event_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    verification_result: Mapped[str] = mapped_column(String(24), nullable=False)
    processing_state: Mapped[str] = mapped_column(String(24), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_redacted: Mapped[str] = mapped_column(Text, nullable=False, default="")
    approved_quote_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class AuditAction(Base):
    __tablename__ = "audit_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class CommerceStorage:
    """Sync storage facade. One instance per process is fine."""

    def __init__(self, database_url: str):
        if not database_url or database_url.strip().lower() in ("", "memory"):
            raise RuntimeError(
                "COMMERCE_DATABASE_URL must be a durable postgresql:// or "
                "sqlite:/// URL; payment storage must not be in-memory."
            )
        self.database_url = database_url
        self.is_postgres = database_url.startswith("postgresql")
        self.engine = create_engine(database_url, future=True)
        self._session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        if self.is_postgres:
            self._apply_migration()
        else:
            Base.metadata.create_all(self.engine)

    def _apply_migration(self) -> None:
        if not _MIGRATION_SQL.exists():
            raise RuntimeError(f"missing migration file: {_MIGRATION_SQL}")
        sql_text = _MIGRATION_SQL.read_text(encoding="utf-8")
        with self.engine.begin() as conn:
            for statement in sql_text.split(";"):
                stmt = statement.strip()
                if stmt:
                    conn.exec_driver_sql(stmt)

    # -- lifecycle ------------------------------------------------------

    def ready(self) -> bool:
        try:
            with self.engine.connect() as conn:
                conn.exec_driver_sql("SELECT 1")
            return True
        except Exception:
            return False

    def session(self):
        return self._session_factory()

    # -- products -------------------------------------------------------

    def upsert_products(self, products: list[CatalogProduct]) -> None:
        with self._session_factory.begin() as s:
            for p in products:
                row = s.scalar(
                    select(MerchantProduct).where(MerchantProduct.sku == p.sku)
                )
                if row is None:
                    row = MerchantProduct(sku=p.sku)
                row.title = p.title
                row.description = p.description
                row.price = p.price
                row.currency = p.currency
                row.stock = p.stock
                row.version = p.version
                row.source = p.source
                row.rights_evidence = p.rights_evidence
                row.active = p.active
                s.add(row)

    # -- quotes ---------------------------------------------------------

    def create_quote(self, quote: CartQuoteData) -> CartQuote:
        with self._session_factory.begin() as s:
            row = CartQuote(
                quote_id=quote.quote_id,
                actor_id=quote.actor_id,
                currency=quote.currency,
                items_json=[item.model_dump(mode="json") for item in quote.items],
                total=quote.total,
                status=quote.status,
                expires_at=quote.expires_at.replace(tzinfo=None),
            )
            s.add(row)
            s.flush()
            s.refresh(row)
            return row

    def get_quote(self, quote_id: str) -> CartQuote | None:
        with self._session_factory() as s:
            return s.scalar(select(CartQuote).where(CartQuote.quote_id == quote_id))

    def get_quote_by_pk(self, pk: int) -> CartQuote | None:
        with self._session_factory() as s:
            return s.get(CartQuote, pk)

    def update_quote_status(self, quote_id: str, status: str) -> None:
        with self._session_factory.begin() as s:
            row = s.scalar(select(CartQuote).where(CartQuote.quote_id == quote_id))
            if row is not None:
                row.status = status

    @staticmethod
    def quote_to_data(row: CartQuote) -> CartQuoteData:
        raw_items = row.items_json
        if isinstance(raw_items, str):
            raw_items = json.loads(raw_items)
        return CartQuoteData(
            quote_id=row.quote_id,
            actor_id=row.actor_id,
            currency=row.currency,
            items=[QuoteLine.model_validate(i) for i in raw_items],
            total=row.total,
            expires_at=row.expires_at.replace(tzinfo=timezone.utc)
            if row.expires_at.tzinfo is None
            else row.expires_at,
            status=row.status,
        )

    # -- checkout attempts ----------------------------------------------

    def create_checkout_attempt(
        self, cart_quote_id: int, buyer_id: str, request_id: str, status: str
    ) -> CheckoutAttempt:
        with self._session_factory.begin() as s:
            row = CheckoutAttempt(
                cart_quote_id=cart_quote_id,
                buyer_id=buyer_id,
                request_id=request_id,
                status=status,
            )
            s.add(row)
            try:
                s.flush()
            except IntegrityError as exc:
                raise DuplicateRequest(request_id) from exc
            s.refresh(row)
            return row

    def attach_paypal_order(self, attempt_id: int, paypal_order_id: str) -> None:
        with self._session_factory.begin() as s:
            row = s.get(CheckoutAttempt, attempt_id)
            if row is not None:
                row.paypal_order_id = paypal_order_id

    def get_attempt(
        self,
        attempt_id: int | None = None,
        request_id: str | None = None,
        paypal_order_id: str | None = None,
    ) -> CheckoutAttempt | None:
        with self._session_factory() as s:
            stmt = select(CheckoutAttempt)
            if attempt_id is not None:
                stmt = stmt.where(CheckoutAttempt.id == attempt_id)
            elif request_id is not None:
                stmt = stmt.where(CheckoutAttempt.request_id == request_id)
            elif paypal_order_id is not None:
                stmt = stmt.where(
                    CheckoutAttempt.paypal_order_id == paypal_order_id
                )
            else:
                raise ValueError("one of attempt_id/request_id/paypal_order_id required")
            return s.scalar(stmt)

    def set_attempt_status(
        self,
        attempt_id: int,
        new_status: str,
        allowed_from: tuple[str, ...] | None = None,
    ) -> bool:
        """Transition attempt status.

        If allowed_from is given, uses an atomic UPDATE ... WHERE status IN
        (...) so concurrent workers can't double-transition (single-flight).
        Returns True if the row was transitioned, False if a concurrent
        worker already moved it (or allowed_from didn't match).
        """
        with self._session_factory.begin() as s:
            if allowed_from is None:
                row = s.get(CheckoutAttempt, attempt_id)
                if row is None:
                    return False
                row.status = new_status
                row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                return True
            from sqlalchemy import update

            result = s.execute(
                update(CheckoutAttempt)
                .where(
                    CheckoutAttempt.id == attempt_id,
                    CheckoutAttempt.status.in_(allowed_from),
                )
                .values(
                    status=new_status,
                    updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
            )
            return getattr(result, "rowcount", 0) == 1

    def require_transition(
        self, attempt_id: int, new_status: str, allowed_from: tuple[str, ...]
    ) -> None:
        if not self.set_attempt_status(attempt_id, new_status, allowed_from):
            raise InvalidStateTransition(
                f"attempt {attempt_id}: cannot move to {new_status} "
                f"from any of {allowed_from}"
            )

    # -- captures -------------------------------------------------------

    def record_capture(
        self,
        attempt_id: int,
        capture_id: str,
        amount: Decimal,
        currency: str,
        status: str,
        verified_at: datetime | None,
    ) -> PaymentCapture:
        with self._session_factory.begin() as s:
            row = PaymentCapture(
                checkout_attempt_id=attempt_id,
                paypal_capture_id=capture_id,
                amount=amount,
                currency=currency,
                status=status,
                verified_at=verified_at,
            )
            s.add(row)
            try:
                s.flush()
            except IntegrityError as exc:
                raise DuplicateCapture(capture_id) from exc
            s.refresh(row)
            return row

    def get_capture(
        self,
        capture_id: str | None = None,
        attempt_id: int | None = None,
    ) -> PaymentCapture | None:
        with self._session_factory() as s:
            stmt = select(PaymentCapture)
            if capture_id is not None:
                stmt = stmt.where(PaymentCapture.paypal_capture_id == capture_id)
            elif attempt_id is not None:
                stmt = stmt.where(PaymentCapture.checkout_attempt_id == attempt_id)
            else:
                raise ValueError("capture_id or attempt_id required")
            return s.scalar(stmt)

    # -- webhook events ---------------------------------------------------

    def record_event(
        self,
        provider_event_id: str,
        event_type: str,
        verification_result: str,
        processing_state: str,
    ) -> bool:
        """Idempotent webhook insert. Returns False if already recorded."""
        with self._session_factory.begin() as s:
            existing = s.scalar(
                select(PaymentEvent).where(
                    PaymentEvent.provider_event_id == provider_event_id
                )
            )
            if existing is not None:
                return False
            s.add(
                PaymentEvent(
                    provider_event_id=provider_event_id,
                    event_type=event_type,
                    verification_result=verification_result,
                    processing_state=processing_state,
                )
            )
            return True

    # -- reporting --------------------------------------------------------

    def list_orders(self, limit: int = 50, offset: int = 0) -> list[dict]:
        with self._session_factory() as s:
            rows = s.scalars(
                select(CheckoutAttempt)
                .order_by(CheckoutAttempt.id.desc())
                .limit(limit)
                .offset(offset)
            ).all()
            return [
                {
                    "attempt_id": r.id,
                    "cart_quote_id": r.cart_quote_id,
                    "buyer_id": r.buyer_id,
                    "request_id": r.request_id,
                    "paypal_order_id": r.paypal_order_id,
                    "status": r.status,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                }
                for r in rows
            ]

    def funnel_stats(self) -> dict:
        with self._session_factory() as s:
            by_status = dict(
                s.execute(
                    select(CheckoutAttempt.status, func.count())
                    .group_by(CheckoutAttempt.status)
                ).all()
            )
            verified_total = s.scalar(
                select(func.coalesce(func.sum(PaymentCapture.amount), 0)).where(
                    PaymentCapture.status == "COMPLETED"
                )
            )
            return {
                "attempts_by_status": {k: int(v) for k, v in by_status.items()},
                "verified_capture_total": str(verified_total),
            }

    # -- agent sessions / audit -------------------------------------------

    def record_agent_session(
        self,
        actor_id: str,
        model: str,
        input_hash: str,
        output_redacted: str,
        approved_quote_id: str | None = None,
    ) -> None:
        with self._session_factory.begin() as s:
            s.add(
                AgentSession(
                    actor_id=actor_id,
                    model=model,
                    input_hash=input_hash,
                    output_redacted=output_redacted,
                    approved_quote_id=approved_quote_id,
                )
            )

    def audit(
        self,
        actor_id: str,
        operation: str,
        subject_id: str,
        status: str,
        correlation_id: str = "",
    ) -> None:
        with self._session_factory.begin() as s:
            s.add(
                AuditAction(
                    actor_id=actor_id,
                    operation=operation,
                    subject_id=subject_id,
                    status=status,
                    correlation_id=correlation_id,
                )
            )

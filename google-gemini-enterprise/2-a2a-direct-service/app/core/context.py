from contextvars import ContextVar

current_order_id: ContextVar[str] = ContextVar("current_order_id", default=None)
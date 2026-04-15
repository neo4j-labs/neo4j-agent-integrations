from contextvars import ContextVar

current_order_id: ContextVar[str] = ContextVar("current_order_id", default=None)
current_user_email: ContextVar[str] = ContextVar("current_user_email", default=None)
current_request_tokens: ContextVar[int] = ContextVar("current_request_tokens", default=0)
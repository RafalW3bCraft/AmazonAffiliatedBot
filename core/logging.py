import logging
import uuid
from contextvars import ContextVar

run_id: ContextVar[str] = ContextVar("run_id", default="no-run")
deal_id: ContextVar[str] = ContextVar("deal_id", default="no-deal")


class CorrelationFilter(logging.Filter):
    def filter(self, record):
        record.run_id = run_id.get()
        record.deal_id = deal_id.get()
        return True


def configure_logging(level=logging.INFO):
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] run=%(run_id)s deal=%(deal_id)s %(name)s: %(message)s"
    ))
    handler.addFilter(CorrelationFilter())
    logging.root.setLevel(level)
    logging.root.handlers = [handler]


def new_run_context() -> str:
    rid = str(uuid.uuid4())[:8]
    run_id.set(rid)
    return rid

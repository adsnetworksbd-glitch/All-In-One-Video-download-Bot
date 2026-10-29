import logging, re, sys

class SensitiveDataFilter(logging.Filter):
    def __init__(self):
        super().__init__()
        self.patterns = [
            re.compile(r"([0-9]{8,10}:[a-zA-Z0-9_-]{35})"),
            re.compile(r'(Bearer\s+)([a-zA-Z0-9_\-\.]{20,})')
        ]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for p in self.patterns: record.msg = p.sub("[REDACTED_SECRET]", record.msg)
        return True

def setup_logger(name: str = "downloader_bot") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s - %(message)s"))
        h.addFilter(SensitiveDataFilter())
        logger.addHandler(h)
    return logger

logger = setup_logger()
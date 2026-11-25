"""Read Turkish bank statement exports into clean, typed transactions."""

from .classify import TYPES, classify, find_counterparty, find_iban, iban_is_valid
from .errors import StatementError
from .parse import fold, parse_amount, parse_date
from .statement import Statement, Transaction, read

__version__ = "0.1.0"

__all__ = [
    "TYPES",
    "Statement",
    "StatementError",
    "Transaction",
    "classify",
    "find_counterparty",
    "find_iban",
    "fold",
    "iban_is_valid",
    "parse_amount",
    "parse_date",
    "read",
]

"""Hakiki: the tech log for AI agents.

A signed, hash-chained record of what an agent did, which model it ran on and
who approved each action.
"""

from .checkpoint import make_checkpoint, read_checkpoints
from .keys import (
    generate_keypair,
    key_id,
    load_private_key,
    load_public_key,
    save_private_key,
    save_public_key,
)
from .ledger import Approval, ApprovalRejected, Ledger
from .verify import INCOMPLETE, INTACT, TAMPERED, VerifyResult, verify

__version__ = "0.1.0"

__all__ = [
    "Ledger",
    "Approval",
    "ApprovalRejected",
    "generate_keypair",
    "verify",
    "VerifyResult",
    "INTACT",
    "TAMPERED",
    "INCOMPLETE",
    "key_id",
    "load_private_key",
    "load_public_key",
    "save_private_key",
    "save_public_key",
    "make_checkpoint",
    "read_checkpoints",
    "__version__",
]

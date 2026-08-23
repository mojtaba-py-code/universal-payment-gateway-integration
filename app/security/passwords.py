"""Password hashing using Argon2id.

Argon2id is the current OWASP-recommended password hashing algorithm. The
``argon2-cffi`` hasher embeds the algorithm, parameters, and salt inside the
encoded hash, so verification and transparent re-hashing on parameter upgrades
are handled for us.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

# Parameters tuned for interactive auth: strong but not so slow that login
# latency suffers. Adjust per deployment benchmarking.
_hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2)


def hash_password(plain: str) -> str:
    """Return an Argon2id encoded hash for ``plain``."""
    if not plain:
        raise ValueError("password must not be empty")
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time verification. Returns ``False`` on any mismatch."""
    try:
        return _hasher.verify(hashed, plain)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def needs_rehash(hashed: str) -> bool:
    """True if the stored hash used weaker parameters and should be upgraded."""
    try:
        return _hasher.check_needs_rehash(hashed)
    except InvalidHashError:
        return True

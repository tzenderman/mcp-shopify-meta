"""In-memory session store for extended authentication persistence."""

import logging
import os
import secrets
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

SESSION_TTL_DAYS = int(os.getenv("SESSION_TTL_DAYS", "30"))
SESSION_ENABLED = os.getenv("SESSION_ENABLED", "true").lower() == "true"


@dataclass
class Session:
    """Represents an authenticated user session."""

    session_id: str
    user_email: str
    created_at: float
    expires_at: float


class SessionStore:
    """In-memory session storage with TTL management.

    Sessions are keyed by session_id and indexed by email for
    single-session-per-user enforcement.
    """

    def __init__(self, ttl_days: int = SESSION_TTL_DAYS):
        self._sessions: dict[str, Session] = {}
        self._email_to_session: dict[str, str] = {}
        self._ttl_seconds = ttl_days * 24 * 60 * 60
        logger.info(f"SessionStore initialized with {ttl_days} day TTL")

    def create_session(self, user_email: str) -> Session:
        """Create a new session for a user, invalidating any prior session."""
        existing_session_id = self._email_to_session.get(user_email.lower())
        if existing_session_id:
            logger.info(f"Invalidating existing session for {user_email}")
            self._sessions.pop(existing_session_id, None)

        session_id = secrets.token_urlsafe(32)
        now = time.time()
        session = Session(
            session_id=session_id,
            user_email=user_email.lower(),
            created_at=now,
            expires_at=now + self._ttl_seconds,
        )

        self._sessions[session_id] = session
        self._email_to_session[user_email.lower()] = session_id

        self._cleanup_expired()

        logger.info(f"Created session for {user_email}, expires in {SESSION_TTL_DAYS} days")
        return session

    def get_session(self, session_id: str) -> Session | None:
        """Get a session by ID if it exists and hasn't expired."""
        session = self._sessions.get(session_id)
        if session and session.expires_at > time.time():
            return session

        if session:
            logger.info(f"Session expired for {session.user_email}")
            self.delete_session(session_id)

        return None

    def delete_session(self, session_id: str) -> None:
        """Delete a session by ID."""
        session = self._sessions.pop(session_id, None)
        if session:
            self._email_to_session.pop(session.user_email, None)
            logger.info(f"Deleted session for {session.user_email}")

    def delete_session_by_email(self, email: str) -> None:
        """Delete a session by user email."""
        session_id = self._email_to_session.get(email.lower())
        if session_id:
            self.delete_session(session_id)

    def _cleanup_expired(self) -> None:
        """Remove all expired sessions."""
        now = time.time()
        expired = [
            (sid, s.user_email)
            for sid, s in self._sessions.items()
            if s.expires_at <= now
        ]
        for session_id, email in expired:
            del self._sessions[session_id]
            self._email_to_session.pop(email, None)

        if expired:
            logger.info(f"Cleaned up {len(expired)} expired session(s)")

    @property
    def active_session_count(self) -> int:
        """Return count of active (non-expired) sessions."""
        self._cleanup_expired()
        return len(self._sessions)


session_store = SessionStore()

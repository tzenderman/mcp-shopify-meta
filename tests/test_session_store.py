"""Tests for SessionStore in-memory session management."""

import time

import pytest

from shopify_meta.utils.session_store import SessionStore


def test_create_session():
    """Test creating a new session."""
    store = SessionStore(ttl_days=1)
    session = store.create_session("user@example.com")
    assert session.user_email == "user@example.com"
    assert session.session_id is not None
    assert len(session.session_id) > 0
    assert session.expires_at > session.created_at


def test_get_session_valid():
    """Test getting a valid session."""
    store = SessionStore(ttl_days=1)
    session = store.create_session("user@example.com")
    retrieved = store.get_session(session.session_id)
    assert retrieved is not None
    assert retrieved.user_email == "user@example.com"
    assert retrieved.session_id == session.session_id


def test_get_session_expired():
    """Test that expired sessions return None."""
    store = SessionStore(ttl_days=1)
    session = store.create_session("user@example.com")
    # Manually expire the session
    session.expires_at = time.time() - 1
    retrieved = store.get_session(session.session_id)
    assert retrieved is None


def test_get_session_nonexistent():
    """Test getting a non-existent session."""
    store = SessionStore(ttl_days=1)
    assert store.get_session("nonexistent-id") is None


def test_single_session_per_user():
    """Test that creating a new session invalidates the old one."""
    store = SessionStore(ttl_days=1)
    session1 = store.create_session("user@example.com")
    session2 = store.create_session("user@example.com")
    # Old session should be invalid
    assert store.get_session(session1.session_id) is None
    # New session should be valid
    assert store.get_session(session2.session_id) is not None
    assert session1.session_id != session2.session_id


def test_delete_session():
    """Test deleting a session by ID."""
    store = SessionStore(ttl_days=1)
    session = store.create_session("user@example.com")
    store.delete_session(session.session_id)
    assert store.get_session(session.session_id) is None


def test_delete_session_by_email():
    """Test deleting a session by email."""
    store = SessionStore(ttl_days=1)
    session = store.create_session("user@example.com")
    store.delete_session_by_email("user@example.com")
    assert store.get_session(session.session_id) is None


def test_active_session_count():
    """Test active session count."""
    store = SessionStore(ttl_days=1)
    assert store.active_session_count == 0
    store.create_session("user1@example.com")
    assert store.active_session_count == 1
    store.create_session("user2@example.com")
    assert store.active_session_count == 2
    # Creating another session for user1 should keep count at 2
    store.create_session("user1@example.com")
    assert store.active_session_count == 2

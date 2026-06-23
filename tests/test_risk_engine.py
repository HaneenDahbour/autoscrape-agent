"""
Tests for src/policy/risk_engine.py

Covers:
  - Sensitive fields are blocked (risk_level=high, allowed=False)
  - Public fields are permitted (risk_level=low, allowed=True)
  - Mixed sensitive + public fields are blocked
  - Decision is always appended to ctx.decisions
"""

import pytest
from src.models import JobContext
from src.policy.risk_engine import run_risk_engine


def make_ctx(fields: list[str]) -> JobContext:
    return JobContext(url="https://example.com", fields=fields, outputs=["csv"])


# ── Blocking cases ────────────────────────────────────────────────────────────

class TestRiskEngineBlocks:

    def test_blocks_password(self):
        ctx = run_risk_engine(make_ctx(["password"]))
        assert ctx.risk_level == "high"
        assert ctx.allowed is False

    def test_blocks_token(self):
        ctx = run_risk_engine(make_ctx(["token"]))
        assert ctx.risk_level == "high"
        assert ctx.allowed is False

    def test_blocks_cookie(self):
        ctx = run_risk_engine(make_ctx(["cookie"]))
        assert ctx.risk_level == "high"
        assert ctx.allowed is False

    def test_blocks_session(self):
        ctx = run_risk_engine(make_ctx(["session"]))
        assert ctx.risk_level == "high"
        assert ctx.allowed is False

    def test_blocks_credit_card(self):
        ctx = run_risk_engine(make_ctx(["credit_card"]))
        assert ctx.risk_level == "high"
        assert ctx.allowed is False

    def test_blocks_national_id(self):
        ctx = run_risk_engine(make_ctx(["national_id"]))
        assert ctx.risk_level == "high"
        assert ctx.allowed is False

    def test_blocks_phone_number(self):
        ctx = run_risk_engine(make_ctx(["phone_number"]))
        assert ctx.risk_level == "high"
        assert ctx.allowed is False

    def test_blocks_private_email(self):
        ctx = run_risk_engine(make_ctx(["private_email"]))
        assert ctx.risk_level == "high"
        assert ctx.allowed is False

    def test_blocks_mixed_sensitive_and_safe(self):
        """If even one sensitive field is requested, the whole job is blocked."""
        ctx = run_risk_engine(make_ctx(["title", "url", "password"]))
        assert ctx.risk_level == "high"
        assert ctx.allowed is False

    def test_blocked_decision_appended(self):
        ctx = run_risk_engine(make_ctx(["token"]))
        decisions = [d for d in ctx.decisions if d["layer"] == "risk_engine"]
        assert len(decisions) == 1
        assert decisions[0]["decision"] == "blocked"

    def test_blocked_error_appended(self):
        ctx = run_risk_engine(make_ctx(["password"]))
        assert len(ctx.errors) > 0

    def test_authorization_status_blocked(self):
        ctx = run_risk_engine(make_ctx(["session"]))
        assert ctx.authorization_status == "blocked"


# ── Allowing cases ────────────────────────────────────────────────────────────

class TestRiskEngineAllows:

    def test_allows_title_and_url(self):
        ctx = run_risk_engine(make_ctx(["title", "url"]))
        assert ctx.risk_level == "low"
        assert ctx.allowed is True

    def test_allows_price(self):
        ctx = run_risk_engine(make_ctx(["price"]))
        assert ctx.risk_level == "low"
        assert ctx.allowed is True

    def test_allows_availability(self):
        ctx = run_risk_engine(make_ctx(["availability"]))
        assert ctx.risk_level == "low"
        assert ctx.allowed is True

    def test_allows_email_generic(self):
        """'email' (generic) is not in the blocklist; only 'private_email' is."""
        ctx = run_risk_engine(make_ctx(["email"]))
        assert ctx.risk_level == "low"
        assert ctx.allowed is True

    def test_permitted_decision_appended(self):
        ctx = run_risk_engine(make_ctx(["title", "url"]))
        decisions = [d for d in ctx.decisions if d["layer"] == "risk_engine"]
        assert len(decisions) == 1
        assert decisions[0]["decision"] == "permitted"

    def test_no_errors_on_safe_fields(self):
        ctx = run_risk_engine(make_ctx(["title", "url", "price"]))
        assert len(ctx.errors) == 0

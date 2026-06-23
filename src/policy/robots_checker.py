"""
robots_checker.py — Robots.txt compliance layer.

Purpose:
  Fetch and parse the site's robots.txt before any scraping begins.
  If the target path is disallowed for our User-Agent, block the job.
  If robots.txt cannot be fetched, continue with a warning (some sites
  legitimately don't publish one).

We identify as "AutoScrapeAgent/1.0" so site operators can identify and
block us if they choose — this is the ethical thing to do.

Decision logged: allowed / warning / blocked.
"""

import urllib.robotparser
import urllib.parse
from src.models import JobContext

USER_AGENT = "AutoScrapeAgent/1.0"


def run_robots_checker(ctx: JobContext) -> JobContext:
    """
    Check robots.txt for the target URL.

    Sets:
      ctx.allowed         — False if robots.txt explicitly disallows our path
      ctx.authorization_status — "blocked", "warning", or "permitted"
    Appends a decision to ctx.decisions.
    """
    # If a previous layer already blocked the job, skip this check
    if not ctx.allowed:
        ctx.decisions.append({
            "layer": "robots_checker",
            "decision": "skipped",
            "reason": "Job already blocked by a previous layer; robots check skipped.",
        })
        return ctx

    parsed = urllib.parse.urlparse(ctx.url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    path = parsed.path or "/"

    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)

    try:
        rp.read()
    except Exception as exc:
        # Network error or robots.txt unreachable — continue with warning
        warning = (
            f"Could not read robots.txt at {robots_url}: {exc}. "
            f"Proceeding with caution."
        )
        ctx.warnings.append(warning)
        ctx.authorization_status = "warning"
        ctx.decisions.append({
            "layer": "robots_checker",
            "decision": "warning",
            "reason": warning,
        })
        return ctx

    if rp.can_fetch(USER_AGENT, ctx.url):
        reason = (
            f"robots.txt at {robots_url} permits '{USER_AGENT}' "
            f"to access path '{path}'."
        )
        ctx.authorization_status = "permitted"
        ctx.decisions.append({
            "layer": "robots_checker",
            "decision": "permitted",
            "reason": reason,
        })
    else:
        ctx.allowed = False
        ctx.authorization_status = "blocked"
        reason = (
            f"robots.txt at {robots_url} disallows '{USER_AGENT}' "
            f"from accessing path '{path}'. Job blocked."
        )
        ctx.errors.append(reason)
        ctx.decisions.append({
            "layer": "robots_checker",
            "decision": "blocked",
            "reason": reason,
        })

    return ctx

"""IT Helpdesk Triage Agent (Scenario 5) — Claude Agent SDK (Python).

Coordinator agent that triages inbound helpdesk requests:
ingest -> classify -> enrich -> decide -> act -> log.

See ../../CLAUDE.md for the shared contracts and conventions.
"""

__version__ = "0.1.0"


def _load_env() -> None:
    """Load env vars (e.g. ANTHROPIC_API_KEY) from a .env file if one exists.

    Runs at import so the key is in the environment before the SDK client is
    built. Safe no-op when python-dotenv isn't installed or no .env is present —
    the key can still come from the real environment. Existing environment
    variables take precedence over .env (load_dotenv does not override).
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    from pathlib import Path

    # scenario root == parent of the helpdesk_agent package directory
    scenario_root_env = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(scenario_root_env)  # no-op if the file doesn't exist
    load_dotenv()  # also pick up a .env in the current working directory


_load_env()

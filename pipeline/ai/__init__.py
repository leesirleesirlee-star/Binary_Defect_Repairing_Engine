"""AI prompt builder and provider transport for the G2 audit (module: ai).

The prompt is assembled only from structured, source-free inputs; the provider
key stays in the host process environment and never reaches the prompt, the
report, the repository or a log.
"""

from .prompt import DEFECT_DESCRIPTION, build_prompt, load_system_prompt
from .provider import ProviderError, call_chat, load_fixplan_schema, run_plan

__all__ = [
    "DEFECT_DESCRIPTION",
    "ProviderError",
    "build_prompt",
    "call_chat",
    "load_fixplan_schema",
    "load_system_prompt",
    "run_plan",
]

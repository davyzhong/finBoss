"""AI 提示词模板包"""

from services.ai.prompts.attribution_prompt import ATTRIBUTION_SYSTEM_PROMPT
from services.ai.prompts.card_format_prompt import CARD_FORMAT_SYSTEM_PROMPT
from services.ai.prompts.nl_query_prompt import (
    NL_QUERY_EXAMPLES,
    NL_QUERY_SYSTEM_PROMPT,
    RESULT_EXPLAIN_PROMPT,
)

__all__ = [
    "NL_QUERY_SYSTEM_PROMPT",
    "RESULT_EXPLAIN_PROMPT",
    "NL_QUERY_EXAMPLES",
    "ATTRIBUTION_SYSTEM_PROMPT",
    "CARD_FORMAT_SYSTEM_PROMPT",
]

"""测试提示词模板加载"""
import pytest
from services.ai.prompts import (
    NL_QUERY_SYSTEM_PROMPT,
    RESULT_EXPLAIN_PROMPT,
    NL_QUERY_EXAMPLES,
    ATTRIBUTION_SYSTEM_PROMPT,
)


def test_nl_query_prompt_has_examples():
    assert len(NL_QUERY_EXAMPLES) == 3
    assert all("question" in e and "sql" in e for e in NL_QUERY_EXAMPLES)


def test_nl_query_prompt_has_schema():
    assert "dm.dm_ar_summary" in NL_QUERY_SYSTEM_PROMPT
    assert "dm.dm_customer_ar" in NL_QUERY_SYSTEM_PROMPT
    assert "std.std_ar" in NL_QUERY_SYSTEM_PROMPT


def test_nl_query_prompt_blocks_dangerous():
    """Verify dangerous SQL operations are mentioned in prohibition rules."""
    # The prompt contains the prohibition rule for INSERT/UPDATE/DELETE/DROP
    assert "INSERT/UPDATE/DELETE/DROP" in NL_QUERY_SYSTEM_PROMPT
    # Should not contain permission patterns like "INSERT INTO"
    assert "INSERT INTO" not in NL_QUERY_SYSTEM_PROMPT
    assert "DROP TABLE" not in NL_QUERY_SYSTEM_PROMPT.upper()


def test_result_explain_prompt_has_placeholder():
    assert "{query}" in RESULT_EXPLAIN_PROMPT
    assert "{sql}" in RESULT_EXPLAIN_PROMPT
    assert "{result}" in RESULT_EXPLAIN_PROMPT


def test_attribution_prompt_has_dimensions():
    assert "customer" in ATTRIBUTION_SYSTEM_PROMPT
    assert "time" in ATTRIBUTION_SYSTEM_PROMPT
    assert "product" not in ATTRIBUTION_SYSTEM_PROMPT  # Phase 4 only

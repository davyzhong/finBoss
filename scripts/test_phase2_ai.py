#!/usr/bin/env python3
"""Phase 2 AI 功能测试脚本

测试 Ollama、Milvus、RAG 和 NL 查询的端到端流程。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx


BASE_URL = "http://localhost:8000"


def test_health() -> bool:
    """测试 AI 服务健康检查"""
    print("\n1. 测试 AI 服务健康检查...")
    resp = httpx.get(f"{BASE_URL}/api/v1/ai/health", timeout=10)
    data = resp.json()
    print(f"   Ollama: {'✅ 可用' if data['ollama'] else '❌ 不可用'}")
    print(f"   Milvus: {'✅ 可用' if data['milvus'] else '❌ 不可用'}")
    return data["ollama"] and data["milvus"]


def test_rag_search() -> bool:
    """测试 RAG 知识库检索"""
    print("\n2. 测试 RAG 知识库检索...")
    queries = [
        "逾期率如何计算",
        "应收账款是什么",
        "信用额度管控规则",
    ]
    all_passed = True
    for q in queries:
        resp = httpx.get(
            f"{BASE_URL}/api/v1/ai/rag/search",
            params={"query": q, "top_k": 1},
            timeout=15,
        )
        if resp.status_code == 200:
            result = resp.json()
            print(f"   ✅ '{q}' → {result['count']} 条结果")
        else:
            print(f"   ❌ '{q}' → 错误: {resp.status_code}")
            all_passed = False
    return all_passed


def test_nl_query(question: str, expected_keywords: list[str]) -> bool:
    """测试自然语言查询"""
    print(f"\n3. 测试 NL 查询: {question}")
    print(f"   期望关键词: {expected_keywords}")
    try:
        resp = httpx.post(
            f"{BASE_URL}/api/v1/ai/query",
            params={"question": question},
            timeout=180,
        )
        if resp.status_code != 200:
            print(f"   ❌ HTTP {resp.status_code}: {resp.text[:200]}")
            return False

        data = resp.json()
        if not data.get("success"):
            print(f"   ❌ 查询失败: {data.get('error')}")
            return False

        sql = data.get("sql", "")
        result_count = len(data.get("result", []))
        explanation = data.get("explanation", "")[:100]

        print(f"   ✅ SQL: {sql[:80]}...")
        print(f"   ✅ 结果: {result_count} 条记录")
        print(f"   ✅ 解释: {explanation}...")

        # 检查 SQL 是否合理
        if not sql.upper().startswith("SELECT"):
            print(f"   ⚠️ 警告: SQL 不是 SELECT 语句")
            return False

        return True
    except httpx.TimeoutException:
        print(f"   ❌ 请求超时（60秒）")
        return False
    except Exception as e:
        print(f"   ❌ 错误: {e}")
        return False


def main() -> None:
    print("=" * 60)
    print("FinBoss Phase 2 AI 功能测试")
    print("=" * 60)

    results = []

    # 1. 健康检查
    results.append(("AI 健康检查", test_health()))

    # 2. RAG 搜索
    results.append(("RAG 搜索", test_rag_search()))

    # 3. NL 查询 (需要 Ollama 模型就绪)
    nl_queries = [
        ("本月应收总额是多少", ["应收", "AR", "SELECT"]),
        ("哪些客户逾期了", ["逾期", "客户", "SELECT"]),
        ("C001 公司的逾期率", ["C001", "逾期", "SELECT"]),
    ]
    for question, keywords in nl_queries:
        results.append((f"NL查询: {question}", test_nl_query(question, keywords)))

    # 汇总
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status} - {name}")

    passed_count = sum(1 for _, p in results if p)
    print(f"\n通过: {passed_count}/{len(results)}")


if __name__ == "__main__":
    main()

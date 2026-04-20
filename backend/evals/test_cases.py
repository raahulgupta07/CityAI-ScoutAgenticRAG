"""
Evaluation test cases for the ITSM Agent.
Based on Scout's evaluation pattern.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TestCase:
    question: str
    expected_strings: list[str]          # Must appear in answer
    category: str                        # procedure, navigation, content, edge_case
    golden_doc: Optional[str] = None     # Expected document ID in sources
    golden_pages: list[int] = field(default_factory=list)  # Expected pages
    description: str = ""                # What this test validates


# ── Test Cases ───────────────────────────────────────────────────────────────

PROCEDURE_TESTS = [
    TestCase(
        question="How do I reset a City Family password?",
        expected_strings=["Settings", "Users", "password"],
        category="procedure",
        golden_doc="SOP_IT_CH_AMS_CF_002",
        description="Basic procedure lookup — should find password reset SOP",
    ),
    TestCase(
        question="How to set up POS shop settings in Odoo?",
        expected_strings=["POS", "Odoo"],
        category="procedure",
        golden_doc="SOP_IT_CFC_AMS_ODOO_001",
        description="Odoo POS configuration procedure",
    ),
    TestCase(
        question="How to create a new site in Gold Central?",
        expected_strings=["Gold Central", "site"],
        category="procedure",
        golden_doc="SOP_IT_CMHL_AMS_GLDCENTRAL_001",
        description="Gold Central new site creation",
    ),
    TestCase(
        question="What is the process to set up a new warehouse?",
        expected_strings=["warehouse"],
        category="procedure",
        golden_doc="SOP_IT_CMHL_AMS_GOLDSTK_010",
        description="Warehouse setup in GOLD Stock",
    ),
]

NAVIGATION_TESTS = [
    TestCase(
        question="What documents do we have about Thailand?",
        expected_strings=["Thailand"],
        category="navigation",
        description="Should find Thailand Arrival Card via keyword/semantic search",
    ),
    TestCase(
        question="Show me all documents about immigration",
        expected_strings=["immigration"],
        category="navigation",
        description="Should find immigration-related docs",
    ),
    TestCase(
        question="What documents are in the Enterprise department?",
        expected_strings=["document"],
        category="navigation",
        description="Should list docs filtered by department",
    ),
    TestCase(
        question="Which documents mention Odoo?",
        expected_strings=["Odoo"],
        category="navigation",
        description="Cross-doc search for a specific system",
    ),
]

CONTENT_TESTS = [
    TestCase(
        question="What is the PO number in the import document?",
        expected_strings=["15675"],
        category="content",
        description="Extract specific fact from a document",
    ),
    TestCase(
        question="Who is responsible for password reset?",
        expected_strings=["HR", "support"],
        category="content",
        golden_doc="SOP_IT_CH_AMS_CF_002",
        description="Extract role/responsibility from SOP",
    ),
]

EDGE_CASE_TESTS = [
    TestCase(
        question="asdfjkl random gibberish xyz",
        expected_strings=["couldn't find", "available", "rephrase"],
        category="edge_case",
        description="Gibberish query should explain search path and suggest alternatives",
    ),
    TestCase(
        question="What is the company's pet policy?",
        expected_strings=["couldn't find", "not", "available"],
        category="edge_case",
        description="Missing document — should say not found, not hallucinate",
    ),
    TestCase(
        question="summarize it",
        expected_strings=[],  # Just shouldn't crash
        category="edge_case",
        description="Ambiguous query without context — should ask or list docs",
    ),
]

ALL_TEST_CASES = PROCEDURE_TESTS + NAVIGATION_TESTS + CONTENT_TESTS + EDGE_CASE_TESTS


def get_test_cases(category: Optional[str] = None) -> list[TestCase]:
    if category:
        return [tc for tc in ALL_TEST_CASES if tc.category == category]
    return ALL_TEST_CASES

"""execute_code tool 단위 테스트"""
import pytest

from koclaw.tools.execute_code import ExecuteCodeTool


# ── Tool 스키마 ───────────────────────────────────────────────────────────────

def test_tool_name():
    assert ExecuteCodeTool().name == "execute_code"


def test_tool_is_sandboxed():
    assert ExecuteCodeTool().is_sandboxed is True


def test_tool_has_code_parameter():
    schema = ExecuteCodeTool().schema()
    assert "code" in schema["parameters"]["properties"]


def test_tool_code_is_required():
    schema = ExecuteCodeTool().schema()
    assert "code" in schema["parameters"]["required"]


def test_tool_has_language_parameter():
    schema = ExecuteCodeTool().schema()
    assert "language" in schema["parameters"]["properties"]

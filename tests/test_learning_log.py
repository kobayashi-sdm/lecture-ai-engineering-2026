"""保存前の停止と、承認・拒否後のファイル状態を実際のPydantic AIで検証する。"""

import json
from datetime import datetime

import pytest
from pydantic_ai import DeferredToolRequests, DeferredToolResults
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from app import tools
from app.agent import agent, run_with_approval

CONTENT = "ツールの実行前に利用者の承認を確認する。"


def saving_model(calls=None):
    """呼び出しを固定する偽モデル。承認処理やファイル保存は本物を使う。"""
    calls = calls or [ToolCallPart("save_learning_log", {"lecture": 3, "content": CONTENT}, "save-1")]

    def respond(messages, info):
        returns = [part for msg in messages for part in msg.parts if isinstance(part, ToolReturnPart)]
        if not returns:
            return ModelResponse(parts=calls)
        return ModelResponse(parts=[TextPart("\n".join(str(part.content) for part in returns))])

    return FunctionModel(respond)


@pytest.fixture
def log_dir(tmp_path, monkeypatch):
    path = tmp_path / "learning_log"
    monkeypatch.setattr(tools, "LEARNING_LOG_DIR", path)
    return path


def test_make_quiz_uses_definition_from_requested_lecture():
    quiz = json.loads(tools.make_quiz(2))
    assert any(
        quiz == {"question": f"「{entry['term']}」の意味は？", "answer": entry["definition"]}
        for entry in tools.load_glossary() if entry["lecture"] == 2
    )


@pytest.mark.parametrize("lecture", [0, -1, 999])
def test_make_quiz_handles_missing_lecture(lecture):
    assert "error" in json.loads(tools.make_quiz(lecture))


def test_save_preserves_japanese_and_does_not_overwrite(log_dir):
    first = json.loads(tools.save_learning_log(3, CONTENT))
    first_file = log_dir / first["path"].split("/")[-1]
    before = first_file.read_bytes()
    second = json.loads(tools.save_learning_log(3, "次に復習する内容"))
    assert first["status"] == second["status"] == "saved"
    assert first["path"] != second["path"]
    assert first_file.read_bytes() == before
    assert len(list(log_dir.glob("*.json"))) == 2
    stored = json.loads(before)
    assert stored["content"] == CONTENT
    assert stored["lecture"] == 3
    assert datetime.fromisoformat(stored["saved_at"]).utcoffset().total_seconds() == 0


@pytest.mark.parametrize("lecture,content", [(0, CONTENT), (-1, CONTENT), (3, ""), (3, " \n　")])
def test_invalid_log_does_not_create_directory(log_dir, lecture, content):
    assert json.loads(tools.save_learning_log(lecture, content))["status"] == "error"
    assert not log_dir.exists()


def test_symlink_destination_is_rejected(log_dir, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    log_dir.symlink_to(outside, target_is_directory=True)
    assert json.loads(tools.save_learning_log(3, CONTENT))["status"] == "error"
    assert list(outside.iterdir()) == []


def test_write_failure_is_reported_as_error(log_dir):
    log_dir.write_text("既存ファイル", encoding="utf-8")
    assert json.loads(tools.save_learning_log(3, CONTENT))["status"] == "error"
    assert log_dir.read_text(encoding="utf-8") == "既存ファイル"


@pytest.mark.parametrize("approved", [True, False])
def test_deferred_request_stops_before_any_save(log_dir, approved):
    model = saving_model()
    paused = agent.run_sync("第3回の学習内容を保存して", model=model)
    assert isinstance(paused.output, DeferredToolRequests)
    assert len(paused.output.approvals) == 1
    call = paused.output.approvals[0]
    assert call.tool_name == "save_learning_log"
    assert call.args_as_dict() == {"lecture": 3, "content": CONTENT}
    assert not log_dir.exists()

    result = agent.run_sync(
        model=model,
        message_history=paused.all_messages(),
        deferred_tool_results=DeferredToolResults(approvals={call.tool_call_id: approved}),
    )
    assert isinstance(result.output, str)
    files = list(log_dir.glob("*.json"))
    assert len(files) == int(approved)
    if approved:
        assert json.loads(files[0].read_text(encoding="utf-8"))["content"] == CONTENT
    else:
        assert not log_dir.exists()


@pytest.mark.parametrize("reply,approved", [("y", True), ("YES", True), ("はい", True), ("n", False), ("", False), ("maybe", False)])
def test_cli_approval_and_denial(log_dir, monkeypatch, capsys, reply, approved):
    def answer(prompt):
        assert not log_dir.exists()
        assert "[y/N]" in prompt
        shown = capsys.readouterr().out
        assert CONTENT in shown and "learning_log/" in shown
        return reply

    monkeypatch.setattr("builtins.input", answer)
    result = run_with_approval(agent, "学習内容を保存して", model=saving_model(), trace=True)
    assert isinstance(result.output, str)
    assert len(list(log_dir.glob("*.json"))) == int(approved)
    assert result.usage.requests == 2
    assert result.usage.tool_calls == int(approved)
    assert f": {'approved' if approved else 'denied'}" in capsys.readouterr().out


@pytest.mark.parametrize("error", [EOFError, KeyboardInterrupt])
def test_interrupted_input_denies_save(log_dir, monkeypatch, error):
    def interrupted(prompt):
        raise error()

    monkeypatch.setattr("builtins.input", interrupted)
    result = run_with_approval(agent, "学習内容を保存して", model=saving_model())
    assert isinstance(result.output, str)
    assert not log_dir.exists()


def test_each_pending_call_needs_its_own_decision(log_dir, monkeypatch):
    calls = [
        ToolCallPart("save_learning_log", {"lecture": 3, "content": "保存する記録"}, "save-a"),
        ToolCallPart("save_learning_log", {"lecture": 3, "content": "拒否する記録"}, "save-b"),
    ]
    replies = iter(["y", "n"])
    monkeypatch.setattr("builtins.input", lambda _: next(replies))
    result = run_with_approval(agent, "2件を記録して", model=saving_model(calls))
    files = list(log_dir.glob("*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text(encoding="utf-8"))["content"] == "保存する記録"
    assert result.usage.requests == 2


def test_read_only_request_does_not_ask_for_approval(log_dir, monkeypatch):
    def unexpected(prompt):
        pytest.fail("読み取りだけの質問で承認を求めた")

    monkeypatch.setattr("builtins.input", unexpected)
    result = run_with_approval(agent, "LoRAとは？", model=TestModel(call_tools=["search_glossary"]))
    assert isinstance(result.output, str)
    assert not log_dir.exists()

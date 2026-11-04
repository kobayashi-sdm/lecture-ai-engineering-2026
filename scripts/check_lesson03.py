"""APIなしで第3回のツール・承認処理を実行し、検証結果を保存する。

実行: uv run python -m scripts.check_lesson03
FunctionModel の呼び出しは固定であり、LLMが自律的に選んだ結果ではない。
"""

import contextlib
import io
import json
import platform
import tempfile
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from unittest.mock import patch

from pydantic_ai import DeferredToolRequests
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from app import tools
from app.agent import agent, print_tools, print_trace, run_with_approval

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "lectures" / "03" / "results"
CONTENT = "エージェントでは、モデルがツール呼び出しを要求し、プログラムが承認後に実行する。"


def fixed_model(calls):
    def respond(messages, info):
        returns = [part for msg in messages for part in msg.parts if isinstance(part, ToolReturnPart)]
        if not returns:
            return ModelResponse(parts=calls)
        return ModelResponse(parts=[TextPart("\n".join(str(part.content) for part in returns))])

    return FunctionModel(respond)


def summarize(result):
    return {
        "requests": result.usage.requests,
        "tool_calls": result.usage.tool_calls,
        "calls": [
            {"name": part.tool_name, "args": part.args_as_dict(), "id": part.tool_call_id}
            for msg in result.all_messages() for part in msg.parts if isinstance(part, ToolCallPart)
        ],
        "output": result.output,
    }


def main():
    RESULTS.mkdir(parents=True, exist_ok=True)
    report = {
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "mode": "APIなし。FunctionModelでツール呼び出しを固定し、承認・保存・再開は実際のコードを実行。",
        "python": platform.python_version(),
        "pydantic_ai": version("pydantic-ai-slim"),
        "google_genai": version("google-genai"),
        "live_gemini_executed": False,
        "exercise": {},
        "approval": {},
    }
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        print("APIなしの検証。以下のツール呼び出しはFunctionModelで固定しています。")
        print_tools(agent)
        cases = [
            ("homework_levels", "宿題の3レベルとは？", [ToolCallPart("search_glossary", {"query": "3レベル"}, "levels")]),
            ("lora_qlora", "LoRAとQLoRAの違いは？", [ToolCallPart("search_glossary", {"query": "LoRA"}, "lora"), ToolCallPart("search_glossary", {"query": "QLoRA"}, "qlora")]),
            ("quiz", "第2回の内容から確認問題を1問出して", [ToolCallPart("make_quiz", {"lecture": 2}, "quiz")]),
        ]
        for name, question, calls in cases:
            print(f"\n=== {name} ===")
            result = run_with_approval(agent, question, model=fixed_model(calls))
            print(result.output)
            print_trace(result)
            report["exercise"][name] = summarize(result)

        for name, reply in [("approved", "y"), ("denied", "n"), ("empty", "")]:
            with tempfile.TemporaryDirectory(prefix="aie-lesson03-") as temp:
                log_dir = Path(temp) / "learning_log"
                call = ToolCallPart("save_learning_log", {"lecture": 3, "content": CONTENT}, f"save-{name}")
                model = fixed_model([call])
                with patch.object(tools, "LEARNING_LOG_DIR", log_dir):
                    pending = agent.run_sync("第3回の学習内容を記録して", model=model)
                    assert isinstance(pending.output, DeferredToolRequests)
                    assert not log_dir.exists()

                    def answer(prompt):
                        assert not log_dir.exists()
                        print(prompt + reply)
                        return reply

                    print(f"\n=== {name} ===")
                    with patch("builtins.input", answer):
                        result = run_with_approval(agent, "第3回の学習内容を記録して", model=model, trace=True)
                    print(result.output)
                    print_trace(result)
                    files = sorted(log_dir.glob("*.json"))
                    assert len(files) == (1 if name == "approved" else 0)
                    saved = [json.loads(path.read_text(encoding="utf-8")) for path in files]
                    print(f"[state] 保存されたJSONファイル: {len(files)} 件")
                    report["approval"][name] = {
                        "directory_exists_before_approval": False,
                        "reply": reply,
                        "saved_file_count": len(files),
                        "saved_records": saved,
                        **summarize(result),
                    }
                    if saved:
                        (RESULTS / "saved_log_example.json").write_text(
                            json.dumps(saved[0], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                        )

    (RESULTS / "offline_trace.txt").write_text(
        "\n".join(line.rstrip() for line in stream.getvalue().splitlines()) + "\n", encoding="utf-8"
    )
    (RESULTS / "offline_results.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("APIなしの検証: 成功（承認1件、拒否0件、空入力0件の保存）")
    print(f"結果: {RESULTS}")


if __name__ == "__main__":
    main()

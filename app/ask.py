"""第1回: 素のLLMに質問するスクリプト。

使い方:
    uv run python -m app.ask "LoRAとは何ですか？"
    uv run python -m app.ask            # 質問を省略すると、講座に固有の質問をする
    uv run python -m app.ask --interactive "LoRAとは何ですか？"  # 続けて質問する

ツールを持たない「素の」呼び出し。--interactive では会話履歴を保って質問を続ける。
講座に固有のことを聞くと、「分からない」と答えるか、一般論でもっともらしく答える
（講座の実際とは違う）ことを確かめよう。
（第3回で、用語集を検索できるエージェントにして改善する）
"""

import argparse

from google import genai
from google.genai.chats import Chat
from google.genai import errors

from app.config import MODEL, api_error_message, get_api_key

# 講座に固有の質問。正しい答えは data/glossary.json の homework-levels にある
DEFAULT_QUESTION = "AIE2026の講座の宿題にある「3レベル」とは何ですか？"


def ask(chat: Chat, question: str) -> str:
    response = chat.send_message(question)

    usage = response.usage_metadata
    if usage is None:
        print("[tokens] 使用量情報なし")
    else:
        print(
            f"[tokens] 入力={usage.prompt_token_count} "
            f"出力={usage.candidates_token_count}"
        )

    return response.text


def main() -> None:
    parser = argparse.ArgumentParser(description="素のLLMに質問する")
    parser.add_argument("question", nargs="?", default=DEFAULT_QUESTION)
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="回答後も会話履歴を保ったまま質問を続ける（空行で終了）",
    )
    args = parser.parse_args()

    print(f"[model] {MODEL}")
    question = args.question
    try:
        client = genai.Client(api_key=get_api_key())
        chat = client.chats.create(model=MODEL)
        while True:
            print(f"[質問] {question}\n")
            print(ask(chat, question))
            if not args.interactive:
                break
            try:
                question = input("\n次の質問（空行で終了）> ").strip()
            except EOFError:
                break
            if not question:
                break
    except errors.APIError as e:
        print(api_error_message(e.code, e.message))
        raise SystemExit(1)


if __name__ == "__main__":
    main()

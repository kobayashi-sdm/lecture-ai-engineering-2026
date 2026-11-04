"""第3回: エージェントに持たせるツール。

ここに書いた関数の docstring と型ヒントが、そのままモデルへの「ツールの説明文」になる。
説明文を書き換えると、モデルがツールを使うかどうか・どんな引数で呼ぶかが変わる。
"""

import json
import random
from datetime import datetime, timezone
from functools import cache
from pathlib import Path
from uuid import uuid4

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LEARNING_LOG_DIR = Path(__file__).resolve().parent.parent / "learning_log"
MAX_RESULTS = 3


@cache
def load_glossary() -> list[dict]:
    with open(DATA_DIR / "glossary.json", encoding="utf-8") as f:
        return json.load(f)["terms"]


def _normalize(text: str) -> str:
    return text.casefold().replace(" ", "").replace("　", "")


def _names(entry: dict) -> list[str]:
    return [_normalize(entry["term"]), _normalize(entry["id"])] + [
        _normalize(a) for a in entry["aliases"]
    ]


def search_glossary(query: str) -> str:
    """講座の用語集から用語を検索し、定義と、どの回で扱うかを返す。

    AIエンジニアリングの用語や、この講座（AIE2026）に固有の言葉について
    答える前に使うこと。query には調べたい用語を1つだけ入れる（例: "LoRA"）。
    """
    q = _normalize(query)
    if not q:
        return "検索語が空です。調べたい用語を1つ指定してください。"
    glossary = load_glossary()

    exact = [e for e in glossary if q in _names(e)]
    # 「r」のような短い別名が何にでも当たらないよう、名前側が短いものは除く
    partial = [
        e for e in glossary
        if e not in exact and any(q in n or (len(n) >= 3 and n in q) for n in _names(e))
    ]
    in_definition = [
        e for e in glossary
        if e not in exact and e not in partial and q in _normalize(e["definition"])
    ]
    hits = (exact + partial + in_definition)[:MAX_RESULTS]

    if not hits:
        return f"用語集に「{query}」は見つかりませんでした。"
    return json.dumps(
        [
            {
                "term": e["term"],
                "lecture": e["lecture"],
                "definition": e["definition"],
                "related": e["related"],
            }
            for e in hits
        ],
        ensure_ascii=False,
    )


def get_lecture_summary(lecture: int) -> str:
    """指定した回（1始まりの整数）の講義の要点を返す。

    「第3回では何を学ぶ？」のように、回の内容や関係を聞かれたときに使う。
    """
    path = DATA_DIR / "lectures" / f"{lecture:02d}.md"
    if not path.exists():
        available = sorted(p.stem for p in (DATA_DIR / "lectures").glob("*.md"))
        return f"第{lecture}回の要点はまだありません。用意されている回: {', '.join(available)}"
    return path.read_text(encoding="utf-8")


def make_quiz(lecture: int) -> str:
    """指定した回の用語から1つを選び、確認問題と答えを返す。

    「第2回の確認問題を出して」のように、復習用の問題を求められたときに使う。
    lecture には講義の回を1始まりの整数で指定する。
    """
    entries = [entry for entry in load_glossary() if entry["lecture"] == lecture]
    if not entries:
        return json.dumps(
            {"error": f"第{lecture}回の用語は用語集にありません。"}, ensure_ascii=False
        )
    entry = random.choice(entries)
    return json.dumps(
        {"question": f"「{entry['term']}」の意味は？", "answer": entry["definition"]},
        ensure_ascii=False,
    )


def save_learning_log(lecture: int, content: str) -> str:
    """利用者が保存を依頼した学習内容を learning_log/ にJSONで新規保存する。

    「第3回で学んだことを記録して」のように、学習記録の保存を明示的に
    求められたときに使う。lecture は1始まりの講義回、content は保存する
    学習内容。内容が曖昧なら先に利用者に確認する。呼び出しはCLIでの承認待ちに
    なり、利用者が承認した場合だけ実行される。保存先と日時はプログラムが決める。
    """
    if type(lecture) is not int or lecture < 1:
        return json.dumps({"status": "error", "error": "講義回は1以上の整数を指定してください。"}, ensure_ascii=False)
    if not content.strip():
        return json.dumps({"status": "error", "error": "学習内容が空です。"}, ensure_ascii=False)

    now = datetime.now(timezone.utc)
    record = {"lecture": lecture, "content": content, "saved_at": now.isoformat()}
    filename = f"{now:%Y%m%dT%H%M%S%fZ}_{uuid4().hex}.json"
    try:
        if LEARNING_LOG_DIR.is_symlink():
            return json.dumps({"status": "error", "error": "保存先にシンボリックリンクは使えません。"}, ensure_ascii=False)
        LEARNING_LOG_DIR.mkdir(parents=True, exist_ok=True)
        with (LEARNING_LOG_DIR / filename).open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    except OSError:
        return json.dumps({"status": "error", "error": "学習記録を保存できませんでした。保存先と書き込み権限を確認してください。"}, ensure_ascii=False)
    return json.dumps(
        {"status": "saved", "path": f"learning_log/{filename}", **record}, ensure_ascii=False
    )

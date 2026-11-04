# 第3回 解答

## 演習

- 第1回（素のLLM）とエージェントの回答の違い：Gemini API キーが未設定のため、実モデルによる回答比較は未実行。コード上では、`app.ask` は質問をそのままモデルに渡し、`app.agent` はツールの検索結果を会話に戻して回答を続ける構成になっている。
- 追加したツール：`make_quiz(lecture: int) -> str`。指定した回の用語を1つ選び、用語の意味を問う問題と、その定義を答えとしてJSONで返す。用語がない回ではエラーメッセージを返す。
- docstring：「第2回の確認問題を出して」のように復習用の問題を求められたときに使う、と記載した。`INSTRUCTIONS` にも、確認問題を求められたら `make_quiz` を使う指示を追加した。

APIを使わない検証では、次のツール呼び出しと戻り値を確認した。

| 検証内容 | ツールと引数 | `requests` | 実行されたツール数 |
|---|---|---:|---:|
| 宿題の3レベル | `search_glossary(query="3レベル")` | 2 | 1 |
| LoRAとQLoRA | `search_glossary(query="LoRA")`、`search_glossary(query="QLoRA")` | 2 | 2 |
| 第2回の確認問題 | `make_quiz(lecture=2)` | 2 | 1 |

この検証は `FunctionModel` で呼び出すツールと引数を固定したもの。`requests` は偽モデルへの要求回数であり、Geminiへの実際の呼び出し回数ではない。ツールの登録・実行・結果の受け渡しは実際のPydantic AIで確認した。実行記録は `results/offline_trace.txt`、詳細は `results/offline_results.json` に保存した。

## 宿題

### 取り組んだレベル

実装。

### やったこと

`app/tools.py` に `save_learning_log(lecture: int, content: str) -> str` を追加した。講義回・学習内容・UTCの保存日時を `learning_log/` 内のJSONファイルに保存する。ファイル名は日時とUUIDで生成し、排他的な新規作成で既存ファイルの上書きを防ぐ。空の学習内容や1未満の講義回は保存せず、書き込みに失敗した場合も保存成功を返さない。

`app/agent.py` では次のように登録した。

```python
agent = Agent(instructions=INSTRUCTIONS, output_type=[str, DeferredToolRequests])
agent.tool_plain(tools.save_learning_log, requires_approval=True)
```

保存が要求されると `DeferredToolRequests` で一度停止する。CLIでツール名・講義回・保存内容・保存先を表示し、利用者に `[y/N]` で確認する。承認・拒否をツール呼び出しIDに対応付けた `DeferredToolResults` と、`result.all_messages()` の会話履歴を渡して再開する。`y`・`yes`・`はい` の場合のみ承認し、空入力・その他の入力・EOF・入力中断は拒否する。

### 結果

Python 3.12.14、pydantic-ai-slim 2.57.0、google-genai 2.31.0で検証した。講座指定の `uv.lock` は変更していない。

| 条件 | 承認前の保存ファイル | 再開後の保存ファイル | 結果 |
|---|---:|---:|---|
| `y`で承認 | 0 | 1 | JSONの講義回・学習内容・日時を確認 |
| `n`で拒否 | 0 | 0 | ツール本体を実行せず、拒否の結果を返して再開 |
| 空入力 | 0 | 0 | 拒否として再開 |
| EOF・入力中断 | 0 | 0 | 拒否として再開 |

承認時の記録の抜粋：

```text
この内容を保存しますか？ [y/N]: y
[approval] save_learning_log (save-approved): approved
[state] 保存されたJSONファイル: 1 件
```

拒否時の記録の抜粋：

```text
この内容を保存しますか？ [y/N]: n
[approval] save_learning_log (save-denied): denied
The tool call was denied.
[state] 保存されたJSONファイル: 0 件
```

講座付属テストと追加テストを合わせて **34件すべて成功**した。複数の保存要求に対する個別の承認・拒否、上書き防止、不正な入力、書き込み失敗、読み取りだけの質問で承認を求めないことも確認した。

上記はAPIを使わない検証結果。承認・ファイル保存・会話の再開は実際に実行したが、Geminiが依頼を解釈して適切なツールを選ぶか、拒否後に自然な日本語で応答するかは未確認。

### 気づき・疑問

「保存前に確認する」と指示文に書くだけでは、実行を確実に止める仕組みにはならない。`requires_approval=True` により、ツール本体が動く前にプログラム側で停止できる。

承認後の再開には、承認結果だけでなく会話履歴とツール呼び出しIDが必要になる。また、拒否時もモデルへの要求は発生するため、モデルへの要求回数と実際に実行されたツール数は分けて読む必要がある。完了の確認には、回答文に加えて保存先のファイル状態を確かめることが有効だった。

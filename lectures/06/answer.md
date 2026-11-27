# 第6回 解答

## 演習

- STEP 1 のツールの名前：glossary_search_glossary
- STEP 2 の [tool call]：glossary_search_glossary({'query': '3レベル'})
- STEP 3 の [tool call]：fetch_fetch({'url': 'https://modelcontextprotocol.io/'})
- STEP 4 の [tool call]：
  - aws_aws___search_documentation({'search_phrase': 'Amazon S3 バージョニング 概要', 'topics': ['general']})
  - aws_aws___search_documentation({'search_phrase': 'Using versioning in S3 buckets', 'topics': ['general']})
- 気づき・疑問：STEP 4 では、aws のツールが5個増え、名前は `aws_aws___…` と接頭辞が二重になった。入力トークンは STEP 2 の 913 に対して STEP 4 は 11,450、モデル応答は3回だった。外部サーバーのツール説明と検索結果が、そのまま入力に乗るためだと考えた。

## 宿題

- 取り組んだレベル：実装
- やったこと：第3回で作った `make_quiz` を `app/tools.py` に移し、`app/mcp_server.py` で公開した。範囲外の回では、理由と出題できる回を返すようにした（0以下なら「1以上の整数で指定」、用語のない回なら「用語集にないため出題できない。出題できる回: 第1回、第2回、第3回、第4回、第6回」）。テストを3件足した（[差分](results/hw_make_quiz.diff)）。「第99回のクイズを作って」で、返し方を4通りに変えて比べた。
- 結果：

  | 返し方 | モデルに渡った内容 | 回答 |
  |---|---|---|
  | `return`（出題できる回つき） | `[tool return]` に全文 | 出題できる回を5つ挙げ、どれにするか聞き返した |
  | `return`（第3回の元の文） | 「第99回の用語は用語集にありません。」 | 「講座は第何回までを想定されているでしょうか？」と利用者に聞き返した |
  | `raise ValueError` | `[tool error]` に「Error executing tool make_quiz」だけ | 「第1回〜第N回など」と、回を特定できなかった |
  | `raise ToolError` | `[tool error]` に全文 | `return` 版と同じく5つ挙げた |

  第2回・第5回でも試し、第2回は出題、第5回は出題できる回を示して断った。pytest は24件すべて通った。
- 気づき・疑問：`ValueError` で書いた文はサーバーのログに出るだけで、モデルには届かなかった。MCP の SDK は、想定外の例外の文を外に出さず、`ToolError` のときだけ文を渡す作りだった。内部の情報を漏らさないためだと思う。モデルが次に何をするかは、返す文に「代わりにできること」があるかで変わった。

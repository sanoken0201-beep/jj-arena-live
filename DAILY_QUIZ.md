# 今日のクイズ（2026-10 日本語監修・問題拡張）

- 日本時間0:00を境に1日10問。各カテゴリ1問、正解は10pt、不正解は5pt。1日の最大獲得は100pt。
- 10カテゴリ×23問＝230問（基礎・標準200問＋記事に基づく応用30問）。カテゴリごとに23問が巡回し、同カテゴリの同じ問題はバンクが固定されている限り23日周期。選択肢の表示順は日ごとに変化。
- Pot Odds / Equity / MDF / SPR / ICM / Combo / Range / Bet sizing / Vocabulary / Hand reasoning。数値だけでなく前提・理由・レンジと相手への対応を問う。
- 問題文・選択肢・解説は日本語の可読性を監査する。英語用語は必要に応じて短い説明や用語集を付け、専門語を無理に直訳しない。計算問題は分母やタイ・レーキの前提を明示し、実戦判断問題は単一正解の条件を明示する。
- 問題セットと回答時の内容をDB保存。日中の再起動・配信で未回答の問題や正解は変わらない。翌日から新バンクを利用。
- PostgreSQLのユーザー行ロック（SQLiteは書き込みロック）で同時回答を直列化。回答とポイント台帳は同じトランザクションで確定し、一意制約でも二重加算を防ぐ。
- 配信当日に旧クイズで獲得済みのポイントも上限に含める。旧実装で既に100ptを超えていた場合は削除せず、その日の追加加点を停止する。
- 管理者のみ `/api/admin/console/quiz-stats` で問題キー・内容版別の初回回答数、正答数、正答率を確認できる。再送は集計しない。個人名・ユーザーIDは出力しない。
- 30回答未満は標本不足、正答率90%以上は簡単すぎる候補、30%以下は難しすぎる候補。それ以外は範囲内。これは教材改善の目安であり自動削除・難易度変更は行わない。

## 検証

`smoke_test_daily_quiz.py` はSQLiteの実HTTP、16並列取得・回答、上限、他ユーザーの問題、無効回答、0:00更新、旧ポイント移行、障害時のロールバックを検証する。
`--postgres` はlocalhostの専用CI DB `jj_arena_ci` に限定して同じ検証を実行する。
`smoke_test_daily_quiz_ui.js` は再構築した本番JavaScriptから実装を取り出し、文字列選択肢、解説、二重クリック、通信失敗、終了・翌日更新を検証する。

記事の日本語限定、ランキング、ポイント管理、ユーザー管理、WebSocket、ハンド解析の既存回帰試験もCIで継続する。

## 2026-10-11 監修と公開上の注意

- 既存160問の出題経路を確認し、専門用語の一律置換によって生じる「ベット持ちうる手札の候補」などの不自然な複合語を避ける。一般用語は原則そのまま使用し、用語集で補う。
- コール必要勝率、純ブラフの損益分岐、MDF、SPR、オールインの比較について、簡潔で明確な日本語の定型文を用いる。
- 追加40問は10カテゴリに4問ずつ配分。選択肢・正答・解説の整合性を点検し、キーの一意性、20日ローテーション、代表的な数値問題を回帰テストで守る。
- 問題追加によって既存回答やポイント台帳を更新しない。確定済みの当日セットを保持し、翌日の新規出題から追加問題のローテーションが有効になる。管理画面で追加した問題については引き続きDBで個別管理する。
- GPTが生成した問題は文章の自然さだけでは数学的な正しさを保証できないため、公開前に管理者が正解・誤答・根拠を確認する運用を推奨する。

## 応用30問：GTO Wizard Blog 参考（2026-10-11）

- `quiz_advanced_bank.py` に10カテゴリ×3問を独立設問として追加。元記事の設問や文章は転載せず、原理を参考にした別の数値例・4択・解説を作成している。
- 出題タイトルの先頭に「【応用】」を表示。通常問題と同じ各カテゴリのプールから1日1問ずつローテーションするため、応用問題だけを毎日固定出題しない。
- 各問は `difficulty=intermediate`、`source_title`、`source_url` を持ち、回答前APIには出典を出さず、回答後APIおよび回答解説画面に出典を表示する。
- 出題の前提（チップEV/賞金EV、相手のレンジ、引き分け、ポット額、将来ストリート、ベット頻度）を明示。ソルバー特有の細かい混合頻度の暗記を避ける。
- 既存回答・確定済み当日セット・ポイント台帳は改変しない。問題バンクだけの更新として翌日の生成から反映される。

参考文献一覧と各問の参照先は `quiz_advanced_bank.py` の `SOURCES` と各問題行の参照キーを正本とする。主要記事：

- [MDF & Alpha](https://blog.gtowizard.com/mdf-alpha/)
- [Mathematical Misconceptions in Poker](https://blog.gtowizard.com/mathematical-misconceptions-in-poker/)
- [Equity Realization](https://blog.gtowizard.com/equity-realization/)
- [Pot Geometry](https://blog.gtowizard.com/pot-geometry/)
- [The Mechanics of C-Bet Sizing](https://blog.gtowizard.com/the-mechanics-of-c-bet-sizing/)
- [Blockers & Unblockers](https://blog.gtowizard.com/blockers-unblockers-the-secret-to-picking-great-bluffs/)
- [What Is the Bubble Factor?](https://blog.gtowizard.com/what-is-the-bubble-factor-in-poker-tournaments/)
- [How Does ICM Impact PKO Strategy?](https://blog.gtowizard.com/how-does-icm-impact-pko-strategy/)
- [MDF vs ICM](https://blog.gtowizard.com/mdf-vs-icm-rethinking-bluffing-defense-strategies-in-mtts/)
- [Do Solvers Have Targets?](https://blog.gtowizard.com/do-solvers-have-targets/)
- [10 Tips for Multiway Pots](https://blog.gtowizard.com/10-tips-multiway-pots-in-poker/)
- [The Math of Multi-Street Bluffs](https://blog.gtowizard.com/the-math-of-multistreet-bluffs/)

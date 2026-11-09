# JJ Arena Learning Sources

ホームの「今日の学び」で使用する外部ソースの許可リストです。

## Articles

### GTO Wizard Japan

- Purpose: 日本語のGTO・ICM・MTT・エクスプロイト・ソルバー解説
- Feed: `https://japan.gtowizard.com/blog/feed/`
- Allowed host: `japan.gtowizard.com`
- Priority: highest

英語だけのタイトル、News、動画一覧投稿は記事枠から除外します。フィードが取得できない場合でも、日本語の検証済み記事を固定フォールバックとして返します。

ホームとPoker Labの「今週の記事」は、公式RSSと日本語の検証済み固定候補から最大24本を取得し、日本時間の月曜00:00を境に掲載記事を切り替えます。候補が4本以上ある場合は週2本ずつ重複しない組み合わせで巡回し、同一候補プールの前週と翌週では同じ記事を表示しません。候補が2〜3本なら週1本、1本のみなら同じ記事が残るため、新しい候補の追加が必要です。外部サイトの新規公開を保証する仕組みではなく、既存記事の週替わり紹介です。画面への再訪・表示復帰時も更新します。

## YouTube

### GTO Wizard Japan

GTO Wizard Japanの日本語動画ページで公式に案内されているYouTube動画だけを固定候補として利用します。GTO戦略、MTTソリューション、ICM、Study機能などの学習用途を優先します。

### ヨコサワポーカーチャンネル

- Channel ID: `UCuhdzbvkmR75piBs4VsMFMA`
- Purpose: 日本語のポーカー戦略・GTO・ハンド解説
- Feed: YouTube公式Atom feed

### POKER BROTHERS

- Channel ID: `UCispM9GhGBT5XUC5VbLNl6Q`
- Purpose: 戦略学習に加え、国内トッププレイヤーの大会・遠征・挑戦を通じたモチベーション
- Feed: YouTube公式Atom feed

## Selection policy

- YouTube一般検索の結果をそのまま自動掲載しない。
- 動画フィードから、戦略・学習キーワードまたは大会・挑戦キーワードを含むものだけを候補にする。
- `strategy` と `motivation` の両方がホームに残るように選定する。
- 外部サイト障害時も固定フォールバックを表示する。
- サーバーからアクセスするURLはコード内allowlistだけに限定し、ユーザー入力URLをfetchしない。
- 記事本文・動画内容の転載は行わず、タイトル、短い説明、公開日、リンク、サムネイルのみを表示する。

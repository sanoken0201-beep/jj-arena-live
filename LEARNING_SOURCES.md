# JJ Arena Learning Sources

ホームの「今日の学び」で使用する外部ソースの許可リストです。

## Articles

### GTO Wizard Japan

- Purpose: 日本語のGTO・ICM・MTT・エクスプロイト・ソルバー解説
- Feed: `https://japan.gtowizard.com/blog/feed/`
- Allowed host: `japan.gtowizard.com`
- Priority: highest

英語だけのタイトル、News、動画一覧投稿は記事枠から除外します。フィードが取得できない場合でも、日本語の検証済み記事を固定フォールバックとして返します。

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

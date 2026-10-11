"""Original Japanese application questions inspired by publicly available poker theory articles.

Each row: key | question | correct | wrong1 | wrong2 | wrong3 | explanation | source.
Questions and explanations are independently written, not copied from articles.
The source reference supports the underlying strategic concept; numeric examples
are independently constructed from explicitly stated assumptions.
"""
from __future__ import annotations

SOURCES = {
    "math": ("Mathematical Misconceptions in Poker", "https://blog.gtowizard.com/mathematical-misconceptions-in-poker/"),
    "mdf": ("MDF & Alpha", "https://blog.gtowizard.com/mdf-alpha/"),
    "equity": ("Equity Realization", "https://blog.gtowizard.com/equity-realization/"),
    "geometry": ("Pot Geometry", "https://blog.gtowizard.com/pot-geometry/"),
    "sizing": ("The Mechanics of C-Bet Sizing", "https://blog.gtowizard.com/the-mechanics-of-c-bet-sizing/"),
    "bluff": ("Blockers & Unblockers: The Secret to Picking Great Bluffs", "https://blog.gtowizard.com/blockers-unblockers-the-secret-to-picking-great-bluffs/"),
    "bubble": ("What Is the Bubble Factor in Poker Tournaments?", "https://blog.gtowizard.com/what-is-the-bubble-factor-in-poker-tournaments/"),
    "pko": ("How Does ICM Impact PKO Strategy?", "https://blog.gtowizard.com/how-does-icm-impact-pko-strategy/"),
    "icm_mdf": ("MDF vs ICM: Rethinking Bluffing & Defense Strategies in MTTs", "https://blog.gtowizard.com/mdf-vs-icm-rethinking-bluffing-defense-strategies-in-mtts/"),
    "river": ("Do Solvers Have Targets?", "https://blog.gtowizard.com/do-solvers-have-targets/"),
    "multi": ("10 Tips for Multiway Pots in Poker", "https://blog.gtowizard.com/10-tips-multiway-pots-in-poker/"),
    "multistreet": ("The Math of Multi-Street Bluffs", "https://blog.gtowizard.com/the-math-of-multistreet-bluffs/"),
    "range": ("What Is Equity in Poker?", "https://blog.gtowizard.com/what-is-equity-in-poker/"),
    "solving": ("How to Study GTO Solutions", "https://blog.gtowizard.com/how-to-study-gto-solutions/"),
}

ADVANCED_ROWS = {
    "pot_odds": """
raise-pot-25|リバーでポット100にあなたが50をベットし、相手が合計150にレイズしました。あと100のコールで勝敗が確定し、手数料も引き分けもない場合、必要勝率は何%ですか？|25%|40%|55%|70%|コール後の最終ポットは100＋150＋150＝400。追加コール100÷400＝25%です。|math
tie-call-fold|リバーでポット100に100をベットされました。20%で勝ち、20%で引き分け、60%で負けます。引き分けではポットを半分ずつ分けます。費用以外の影響を無視すると？|フォールドが有利|コールが有利|損益分岐|どちらも必ず負の期待値|エクイティは20%＋20%÷2＝30%。必要勝率100÷300＝約33.3%なのでフォールドが有利です。|math
weighted-bluffcatch|リバーでポット100に相手が100をベット。相手のベットレンジには常にベットするバリュー12コンボと純ブラフ6コンボのみがあり、あなたはバリューに必ず負けブラフに必ず勝ちます。手数料なしなら？|コールとフォールドは同じ期待値|コールが必ず利益的|フォールドが必ず利益的|バリューが多いのでコールの勝率は0%|ブラフ比率は6÷18＝33.3%。ポットベットのコール必要勝率100÷300＝33.3%で損益分岐です。|math
""",
    "equity": """
eqr-calc|現在のポットが200、あるハンドの生エクイティが40%、エクイティ実現率が75%と推定されています。『エクイティ×実現率×ポット』で近似した期待回収額は？|60|80|100|150|0.40×0.75×200＝60。生エクイティだけなら80ですが、実現率を考慮すると60です。|equity
eqr-position|同じハンドと相手レンジでも、ポジションが悪い側の生エクイティをそのまま将来の利益とみなせない主な理由は？|後のストリートで不利なベットを受け、十分に実現できない場合がある|ポジションだけでデッキの枚数が減る|生エクイティはポジションによって定義が変わる|ポジションが悪い側は絶対にブラフできない|ショーダウンまで無料で進めるとは限らず、先に行動する不利が実現率を下げる場合があります。|equity
weighted-equity|相手レンジの60%に対して自分のエクイティが20%、残る40%に対して70%です。全ハンドがこの2群に分かれるなら平均エクイティは？|40%|20%|60%|80%|0.60×20%＋0.40×70%＝12%＋28%＝40%。ハンド群の出現頻度で重み付けします。|range
""",
    "mdf": """
mdf-overbet|ポット200に相手が300を純ブラフするとします。コールされた純ブラフには勝ち目がありません。このブラフを自動的な利益にしない最低継続頻度はいくつですか？|40%|20%|60%|80%|必要な継続頻度はポット÷（ポット＋ベット）＝200÷500＝40%です。|mdf
mdf-check-ev|相手のブラフ候補はチェックすれば期待利益5、ベットすれば期待利益0と推定されています。純ブラフのベット利益を0に抑えれば、ベットとチェックを無差別にできていますか？|いいえ。チェックのほうが期待利益が5高い|はい。ベット利益が0なら必ず無差別|はい。最低継続頻度を守ればチェック利益は消える|いいえ。ベット利益は必ずマイナスになる|無差別になるには選択肢同士の期待値が等しい必要があります。0と5では等しくありません。|math
mdf-vs-payout|トーナメントの賞金ジャンプが大きく、コールによる敗退リスクが高い局面です。通常の純ブラフ向けMDFを機械的に守らない理由は？|チップ損益と賞金期待値の損失が同じ比率とは限らない|MDFはリバーでしか計算できないため|賞金ジャンプがあるとブラフは不可能だから|トーナメントではポット額が無意味になるため|順位賞金の非線形な価値がチップの損益を変えるため、単純なMDFを最適防御の法則として使えません。|icm_mdf
""",
    "spr": """
geom-pot-pot|ターン開始時にポット100、双方の残りスタック400。ターンとリバーで同じポット比率のベットが毎回コールされ、リバーでちょうどオールインする場合、各ストリートのベット比率は？|毎回100%ポット|毎回50%ポット|毎回150%ポット|毎回200%ポット|ターンで100を打ちコールされるとポット300、残り300。リバーで300を打つので両方100%ポットです。|geometry
geom-ratio|ターンのポット100、双方の残りスタック200。ターンとリバーで同じポット比率のベットをして毎回コールされ、最後にちょうどオールインする比率は約何%ですか？|62%|40%|80%|100%|ベット比率をxとすると総投資は100x＋100x(1＋2x)＝200。x²＋x＝1からx≈0.618です。|geometry
geom-nut-why|残り2ストリートで一方に極めて強いバリューと弱いブラフが集中し、相手には主にブラフキャッチャーがある理想化した状況です。ジオメトリックサイズが理論的に有利な理由は？|同じポット比率で最終オールインに向かい、相手の全体的な継続範囲を広げやすい|毎ストリートのベット額を同額にできる|相手の強いハンドを物理的に減らす|必ずブラフのフォールド率を100%にする|幾何学的ベットはポット比率をそろえて全額を投資し、理想的な極端レンジでは広い防御を引き出します。|geometry
""",
    "combo": """
weighted-value-bluffs|リバーのベットレンジはバリュー6コンボが毎回ベット、ブラフ12コンボが50%の頻度でベットするとします。ベットした中のブラフ比率は何%ですか？|50%|33%|60%|67%|重み付きブラフは12×0.5＝6コンボ。バリュー6と合わせた12コンボの半分がブラフです。|math
weighted-groups|相手はA群12コンボを50%、B群8コンボを25%でベットします。ベットを観測した後、相手のベットレンジに占めるA群の割合は？|75%|25%|50%|95%|A群は6コンボ、B群は2コンボ。ベットレンジ全体8のうち6なので75%です。|range
aks-blocked-two|見えているカードがA♠とK♥の2枚だけの場合、相手が持てるAKs（同じスートのAK）は何コンボ残りますか？|2コンボ|1コンボ|3コンボ|4コンボ|スペードのAKとハートのAKは作れず、クラブとダイヤの2コンボが残ります。|bluff
""",
    "vocabulary": """
advanced-bubble-factor|『オールインで負けたときに失う賞金期待値 ÷ 勝ったときに増える賞金期待値』を指す指標は？|バブルファクター|SPR|レンジアドバンテージ|エクイティ実現率|バブルファクターはオールインで失う賞金期待値と得る賞金期待値の比で、ICM圧力を表す指標です。|bubble
advanced-geometry|残りの各ストリートでポットに対する同じ割合をベットし、最後にオールインへ到達するサイズ設計は？|ジオメトリックベット|ブロックベット|プローブベット|ドンクベット|同一のポット比率を使い、ポットの成長と残りスタックに合わせる設計です。|geometry
advanced-unblock|自分のカードが相手のフォールドする候補ハンドを減らさずに残している性質を、ブラフ候補の評価では何と呼びますか？|アンブロックしている|ドミネートしている|キャップされている|エクイティが確定している|相手のフォールド候補を妨げずに残す性質はアンブロッカーの考え方で、ブラフ選択に役立ちます。|bluff
""",
    "icm": """
bf-ratio|あるオールインで負けると賞金期待値を120失い、勝つと80増えるとします。バブルファクターは何ですか？|1.5|0.67|2.0|2.5|失う額÷得る額＝120÷80＝1.5です。|bubble
bf-equity|勝率pで賞金期待値が100増え、1-pで150失う単純な二択です。行動の損益分岐に必要な勝率は何%ですか？|60%|40%|50%|75%|100p－150(1－p)＝0からp＝150÷250＝60%。賞金の増減額を使う単純化です。|bubble
pko-negative-risk|通常のMTTと異なり、PKOで賞金獲得のチャンスがあるオールインのリスクプレミアムが負になることはありますか？|あります。獲得可能なバウンティの価値が十分大きい場合です|ありません。常に正です|バウンティの有無では変わりません|必ずどの状況でも負になります|賞金期待値に即時のバウンティ報酬が加わり、リスクプレミアムが負になる局面もあります。|pko
""",
    "bet_sizing": """
polar-river-bluffs|リバーのポット100に100をベット。ベットレンジはコールされれば必ず勝つバリュー12コンボと、必ず負ける純ブラフのみ。相手のブラフキャッチャーをコールとフォールドで無差別にするブラフは何コンボですか？|6コンボ|4コンボ|8コンボ|12コンボ|ポットベットに対する必要勝率は100÷300＝1/3。ブラフ÷（12＋ブラフ）＝1/3から6コンボです。|math
range-vs-nuts|あるフロップで自分にはレンジ全体の平均勝率で優位がありますが、相手のほうが最強クラスのハンドを多く持ちます。この情報から一般的に導けるのは？|ベット頻度を上げる要素はあっても、大サイズには慎重になる|平均勝率が高ければ必ずオーバーベットする|相手のナッツ優位はベット額に関係しない|最強ハンドの多い側が必ず毎回チェックする|平均的なレンジ優位はベット頻度と関わり、ナッツ優位は大きいサイズを支える要素です。|sizing
triple-barrel-fold|フロップでポット100、残りスタックは十分。純ブラフでフロップ・ターン・リバーに毎回ポットサイズをベットし、相手はフロップとターンを必ずコールします。リバーで何%降ろせば全体のブラフが損益分岐ですか？|72%|50%|60%|90%|フロップ100、ターン300、リバー900を投資。相手がリバーで降りれば純利益500、コールなら損失1300。1300÷1800＝約72.2%です。|multistreet
""",
    "range": """
relative-advantage|ボード上で自分のレンジ全体は平均的に優勢ですが、相手のほうが最強クラスのハンドを多く持てます。このとき正しい説明は？|自分に平均的なレンジ優位、相手にナッツ優位が両立する|平均的なレンジ優位とナッツ優位は常に一致する|自分のハンドはすべて相手より強い|相手は強いハンドを全く持てない|分布の平均と最上位の厚さは別で、両者の優位が異なるプレイヤーに分かれる場合があります。|range
river-bluff-selection|リバーで強い相手ハンドを減らす効果が同じ程度の純ブラフ候補が2つあります。片方だけが相手のフォールド候補を多くブロックしているなら、通常どちらを優先しますか？|フォールド候補をブロックしにくいほう|フォールド候補を多くブロックするほう|スートだけで無条件に決める|どちらも必ず同じ期待値になる|降りるハンドを相手レンジに残すアンブロッカーが、他条件同じならブラフの成功率に有利です。|bluff
betting-weight|相手のA群8コンボが毎回ベット、B群16コンボが25%だけベットするとします。ベットを見た後のA群の割合は？|67%|33%|50%|85%|A群8、B群4の重み付きコンボで、A群は8÷12＝約66.7%です。|range
""",
    "hand_reasoning": """
indifference-target|リバーの大きいベットで相手の中間的なブラフキャッチャーがコールとフォールドを混ぜる均衡戦略があります。このベットの理論上の狙いとして適切なのは？|相手のブラフキャッチャーを複数行動で無差別にすること|相手が必ずコールするよう操作すること|相手が必ずフォールドするよう操作すること|自分のブラフを常に勝たせること|均衡戦略は相手の特定の行動を予測するのではなく、複数行動の期待値を近づけます。|river
board-change-rethink|フロップでナッツ優位があると考えて大きくベットし、ターンに相手レンジで多いストレートを完成させるカードが落ちました。まず検討するべきことは？|新しい最強ハンドの分布を再評価し、ベット額と頻度を見直す|フロップの優位はターンでも必ず固定する|すべてのハンドで自動的にオールインする|相手のプリフロップレンジを完全に無視する|ターンで完成し得る最強ハンドが変われば、ポラライズやベットサイズの根拠も変わります。|sizing
multiway-nutdraw|3人でフロップの大きいベットにセミブラフを考えています。最も重視すべき一般的な違いは？|複数人の強い続行レンジに対してナッツ級へ改善できるかをより重視する|3人以上ならどんなフラッシュドローも必ずオールインする|2人相手なら相手のコール範囲は必ず広くなるので無視する|多人数ではポジションが存在しなくなる|多人数ポットでは続行するハンドが強くなりやすく、上位の役に改善できる見込みがより重要です。|multi
""",
}


def validate() -> None:
    assert len(ADVANCED_ROWS) == 10
    for category, text in ADVANCED_ROWS.items():
        rows = [row.strip() for row in text.strip().splitlines() if row.strip()]
        assert len(rows) == 3, (category, len(rows))
        for row in rows:
            parts = row.split("|")
            assert len(parts) == 8, (category, row)
            assert parts[7] in SOURCES, (category, parts[7])
            assert len(set(parts[2:6])) == 4, (category, parts[0])


validate()

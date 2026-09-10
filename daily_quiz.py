from __future__ import annotations

import copy
import hashlib
import json
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field


JST = ZoneInfo("Asia/Tokyo")
DAILY_QUIZ_SIZE = 10
DAILY_QUIZ_REWARD = 10
QUIZ_SET_VERSION = "2026-09-v3"
MIN_VARIANTS_PER_CATEGORY = 12


class DailyQuizAnswerIn(BaseModel):
    question_id: str = Field(min_length=8, max_length=120)
    answer: str = Field(min_length=1, max_length=80)


def _q(
    key: str,
    category: str,
    category_label: str,
    prompt: str,
    choices: list[tuple[str, str]],
    correct: str,
    explanation: str,
) -> dict[str, Any]:
    values = [str(v) for v, _ in choices]
    if len(values) != 4 or len(set(values)) != 4 or str(correct) not in values:
        raise ValueError(f"invalid quiz question {key}")
    return {
        "key": key,
        "category": category,
        "category_label": category_label,
        "prompt": prompt,
        "choices": [{"value": str(v), "label": str(label)} for v, label in choices],
        "correct": str(correct),
        "explanation": explanation,
    }


def _pct(values: list[int]) -> list[tuple[str, str]]:
    return [(str(v), f"{v}%") for v in values]


def _broad_pct(correct: int) -> list[tuple[str, str]]:
    """Return meaningfully separated choices, not arithmetic-near misses."""
    mapping = {
        9: [9, 25, 50, 80], 11: [11, 30, 55, 80], 13: [13, 30, 55, 80],
        15: [15, 35, 60, 80], 17: [17, 35, 55, 80], 20: [20, 40, 60, 80],
        22: [22, 45, 65, 85], 25: [25, 45, 65, 85], 26: [26, 50, 70, 85],
        29: [29, 50, 70, 85], 30: [30, 50, 70, 80], 33: [33, 50, 70, 85],
        35: [20, 35, 60, 80], 38: [20, 38, 60, 80], 40: [20, 40, 60, 80],
        43: [20, 43, 65, 85], 50: [20, 35, 50, 80], 55: [20, 40, 55, 80],
        60: [20, 40, 60, 80], 67: [20, 40, 67, 85], 75: [20, 40, 60, 75],
        80: [20, 40, 60, 80],
    }
    if correct not in mapping:
        raise ValueError(f"no broad percentage choices for {correct}")
    values = mapping[correct]
    if min(abs(v - correct) for v in values if v != correct) < 10:
        raise ValueError(f"percentage distractors too close for {correct}")
    return _pct(values)


def _pot_odds_questions() -> list[dict[str, Any]]:
    rows = [
        (100, 75, 30), (100, 50, 25), (100, 100, 33), (150, 50, 20),
        (100, 25, 17), (120, 80, 29), (200, 100, 25), (150, 150, 33),
        (80, 40, 25), (200, 50, 17), (300, 100, 20), (50, 50, 33),
        (250, 125, 25), (90, 30, 20), (200, 200, 33),
    ]
    return [
        _q(
            f"pot-{pot}-{bet}", "pot_odds", "ポットオッズ",
            f"ポット{pot}に相手が{bet}をベット。あなたは{bet}をコールすればショーダウンで終了するとします。コールに必要な最低勝率は約何%？",
            _broad_pct(correct), str(correct),
            f"{bet}を払って最終ポット{pot + bet + bet}を争うので、{bet} / {pot + bet + bet} ≈ {correct}%です。",
        ) for pot, bet, correct in rows
    ]


def _bluff_questions() -> list[dict[str, Any]]:
    rows = [
        (100, 50, 33), (100, 100, 50), (100, 200, 67), (150, 50, 25),
        (80, 120, 60), (200, 50, 20), (200, 100, 33), (150, 150, 50),
        (300, 100, 25), (50, 100, 67), (120, 80, 40), (80, 20, 20),
        (200, 300, 60), (250, 250, 50), (75, 25, 25),
    ]
    return [
        _q(
            f"bluff-{pot}-{bet}", "bluff_math", "ブラフ損益分岐",
            f"リバーでポット{pot}に{bet}を純粋なブラフとしてベット。コールされたら必ず負けるとすると、必要な最低フォールド率は約何%？",
            _broad_pct(correct), str(correct),
            f"{bet}をリスクして{pot}を獲得するので、{bet} / ({pot} + {bet}) ≈ {correct}%です。",
        ) for pot, bet, correct in rows
    ]


def _equity_questions() -> list[dict[str, Any]]:
    rows = [
        (30, 35, "call"), (30, 24, "fold"), (33, 40, "call"), (33, 28, "fold"),
        (25, 25, "equal"), (20, 18, "fold"), (20, 27, "call"), (40, 47, "call"),
        (40, 31, "fold"), (50, 50, "equal"), (17, 22, "call"), (17, 12, "fold"),
        (29, 34, "call"), (29, 23, "fold"), (33, 33, "equal"),
    ]
    choices = [("call", "コール"), ("fold", "フォールド"), ("equal", "損益分岐で同じEV"), ("unknown", "この情報だけでは判断不能")]
    out = []
    for need, equity, answer in rows:
        relation = "上回る" if equity > need else "下回る" if equity < need else "一致する"
        conclusion = "コールが+EV" if answer == "call" else "フォールド" if answer == "fold" else "損益分岐"
        out.append(_q(
            f"decision-{need}-{equity}", "equity_decision", "意思決定",
            f"相手のオールインに対するコール必要勝率が{need}%。あなたの推定勝率は{equity}%です。レーキ・ICM・タイを無視したchipEVだけなら最も適切なのは？",
            choices, answer,
            f"推定勝率{equity}%は必要勝率{need}%と{relation}ため、chipEV基準では{conclusion}です。",
        ))
    return out


def _vocabulary_questions() -> list[dict[str, Any]]:
    return [
        _q("term-squeeze", "vocabulary", "ポーカー語彙", "プリフロップで、1人がオープンレイズし、別の1人以上がコールした後にさらにリレイズするプレイは？", [("squeeze", "スクイーズ"), ("probe", "プローブベット"), ("float", "フロート"), ("donk", "ドンクベット")], "squeeze", "レイザーとコーラーの双方へ圧力をかけるリレイズをスクイーズと呼びます。"),
        _q("term-blocker", "vocabulary", "ポーカー語彙", "自分が特定カードを持つことで、相手があるハンドを持てる組み合わせ数が減る効果は？", [("blocker", "ブロッカー"), ("rake", "レーキ"), ("overlay", "オーバーレイ"), ("variance", "バリアンス")], "blocker", "自分のカードが相手の候補コンボを物理的に減らす効果がブロッカーです。"),
        _q("term-capped", "vocabulary", "ポーカー語彙", "アクション経過から、レンジ上限に非常に強いハンドがほとんど含まれない状態は？", [("capped", "キャップされたレンジ"), ("polar", "ポラライズレンジ"), ("merged", "マージドレンジ"), ("uncapped", "アンキャップドレンジ")], "capped", "非常に強いハンドを持ちにくくレンジ上限が制限された状態をcappedと呼びます。"),
        _q("term-polar", "vocabulary", "ポーカー語彙", "非常に強いバリューとブラフを中心に構成され、中間の強さが少ないベットレンジは？", [("polar", "ポラライズ"), ("linear", "リニア"), ("capped", "キャップ"), ("condensed", "コンデンス")], "polar", "強いバリューとブラフという両端を中心にした構造がポラライズです。"),
        _q("term-linear", "vocabulary", "ポーカー語彙", "最上位から一定の強さまで、比較的連続して強いハンドを含めるレイズレンジは？", [("linear", "リニア"), ("polar", "ポラライズ"), ("capped", "キャップ"), ("air", "エアー")], "linear", "強い順に連続的なハンドを含める構造をリニアと表現します。"),
        _q("term-spr", "vocabulary", "ポーカー語彙", "SPRが表す比率は？", [("spr", "エフェクティブスタック ÷ ポット"), ("mdf", "ポット ÷ ベット"), ("equity", "勝率 ÷ オッズ"), ("rake", "レーキ ÷ ポット")], "spr", "SPRはStack-to-Pot Ratioで、エフェクティブスタックをポットで割る比率です。"),
        _q("term-mdf", "vocabulary", "ポーカー語彙", "MDFの意味として最も適切なのは？", [("mdf", "相手の自動利益ブラフを防ぐ基準となる最低ディフェンス頻度"), ("spr", "スタックとポットの比率"), ("icm", "賞金をチップへ変換する固定倍率"), ("ev", "勝率そのもの")], "mdf", "MDFはMinimum Defense Frequencyです。実戦の最適防御頻度と常に同一とは限りません。"),
        _q("term-icm", "vocabulary", "ポーカー語彙", "ICMが扱うものとして最も適切なのは？", [("icm", "スタック分布と賞金構造から各スタックの金銭価値を近似するモデル"), ("spr", "ポットに対するスタック比率"), ("mdf", "最低ディフェンス頻度"), ("equity", "ショーダウン勝率")], "icm", "ICMはトーナメントチップの金銭価値を非線形に近似します。"),
        _q("term-nut-advantage", "vocabulary", "ポーカー語彙", "一方のレンジにナッツ級の非常に強いハンドが相対的に多い状態は？", [("nut", "ナッツアドバンテージ"), ("range", "レンジアドバンテージ"), ("blocker", "ブロッカー"), ("overlay", "オーバーレイ")], "nut", "レンジ上部の最強クラスを多く持てる側にはナッツアドバンテージがあります。"),
        _q("term-range-advantage", "vocabulary", "ポーカー語彙", "レンジ全体の平均的なエクイティが相手より高い状態を表す語は？", [("range", "レンジアドバンテージ"), ("nut", "ナッツアドバンテージ"), ("squeeze", "スクイーズ"), ("block", "ブロックベット")], "range", "レンジ全体で平均的に優位な側をレンジアドバンテージがあると表現します。"),
        _q("term-donk", "vocabulary", "ポーカー語彙", "前ストリートのアグレッサーではないOOP側が、次ストリートでその相手より先にベットするプレイは？", [("donk", "ドンクベット"), ("cbet", "コンティニュエーションベット"), ("squeeze", "スクイーズ"), ("coldcall", "コールドコール")], "donk", "前ストリートのアグレッサーへOOPから先に打つベットをドンクベットと呼びます。"),
        _q("term-overbet", "vocabulary", "ポーカー語彙", "オーバーベットの一般的な意味は？", [("overbet", "現在のポット額を上回るサイズのベット"), ("allin", "必ずオールインになるベット"), ("min", "最小レイズ"), ("threebet", "プリフロップ3ベット")], "overbet", "ポット額より大きいベットサイズをオーバーベットと呼びます。"),
        _q("term-float", "vocabulary", "ポーカー語彙", "フロップで直ちに強いハンドがなくてもコールし、後のストリートでポット獲得を狙うプレイを表す語は？", [("float", "フロート"), ("squeeze", "スクイーズ"), ("donk", "ドンク"), ("limp", "リンプ")], "float", "後のストリートで主導権やフォールドを狙うための軽いコールをフロートと呼びます。"),
        _q("term-coldcall", "vocabulary", "ポーカー語彙", "自分がまだチップを入れていない状態で、レイズに対してリレイズせずコールすることは？", [("coldcall", "コールドコール"), ("checkraise", "チェックレイズ"), ("probe", "プローブ"), ("isolate", "アイソレート")], "coldcall", "それまでアクションへ参加していないプレイヤーがレイズをコールするのがコールドコールです。"),
        _q("term-effective", "vocabulary", "ポーカー語彙", "2人のオールイン可能額を実質的に決める『エフェクティブスタック』は通常どれ？", [("shorter", "2人のうち短い方のスタック"), ("larger", "2人のうち大きい方のスタック"), ("sum", "2人のスタック合計"), ("average", "2人の平均スタック")], "shorter", "相手より多い超過分は相手から獲得できないため、短い方がエフェクティブスタックです。"),
    ]


def _combo_questions() -> list[dict[str, Any]]:
    return [
        _q("combo-pair", "combos", "コンボ計算", "ホールデムで特定のポケットペア（例: 88）は、カードが1枚も見えていないとき何コンボ？", [("4", "4コンボ"), ("6", "6コンボ"), ("12", "12コンボ"), ("16", "16コンボ")], "6", "同じランク4枚から2枚を選ぶのでC(4,2)=6コンボです。"),
        _q("combo-suited", "combos", "コンボ計算", "特定のスーテッド非ペアハンド（例: A5s）は何コンボ？", [("4", "4コンボ"), ("6", "6コンボ"), ("12", "12コンボ"), ("16", "16コンボ")], "4", "4つのスートそれぞれに1通りあるため4コンボです。"),
        _q("combo-offsuit", "combos", "コンボ計算", "特定のオフスート非ペアハンド（例: KQo）は何コンボ？", [("4", "4コンボ"), ("6", "6コンボ"), ("12", "12コンボ"), ("16", "16コンボ")], "12", "全16コンボから4つのスーテッドを除き12コンボです。"),
        _q("combo-ak", "combos", "コンボ計算", "カードが1枚も見えていないとき、AK（suitedとoffsuit両方）は合計何コンボ？", [("4", "4コンボ"), ("9", "9コンボ"), ("12", "12コンボ"), ("16", "16コンボ")], "16", "Aは4枚、Kも4枚なので4×4=16コンボです。"),
        _q("combo-aa-one-block", "combos", "コンボ計算", "あなたがAを1枚持っています。相手がAAを持てる残りコンボ数は？", [("1", "1コンボ"), ("3", "3コンボ"), ("6", "6コンボ"), ("12", "12コンボ")], "3", "残りAは3枚。その3枚から2枚を選ぶので3コンボです。"),
        _q("combo-ak-two-block", "combos", "コンボ計算", "あなたがAを1枚とKを1枚持っています。相手がAKを持てる残りコンボ数は？", [("4", "4コンボ"), ("6", "6コンボ"), ("9", "9コンボ"), ("12", "12コンボ")], "9", "残りA3枚×残りK3枚=9コンボです。"),
        _q("combo-aa-two-visible", "combos", "コンボ計算", "あなたの手札とボードを合わせてAが2枚見えています。相手がAAを持てる残りコンボ数は？", [("1", "1コンボ"), ("2", "2コンボ"), ("3", "3コンボ"), ("6", "6コンボ")], "1", "残りAは2枚しかないため、その2枚を使う1コンボだけです。"),
        _q("combo-qq-one-visible", "combos", "コンボ計算", "Qが1枚見えています。相手がQQを持てる残りコンボ数は？", [("1", "1コンボ"), ("3", "3コンボ"), ("6", "6コンボ"), ("9", "9コンボ")], "3", "残りQ3枚から2枚を選ぶので3コンボです。"),
        _q("combo-nonpair-all", "combos", "コンボ計算", "異なる2ランクの特定ハンド（例: KQ）をスート指定なしで数えると何コンボ？", [("4", "4コンボ"), ("8", "8コンボ"), ("12", "12コンボ"), ("16", "16コンボ")], "16", "K4枚×Q4枚=16コンボです。"),
        _q("combo-two-pairs", "combos", "コンボ計算", "AAとKKという2種類の特定ポケットペアを合わせると、カードが見えていないとき何コンボ？", [("6", "6コンボ"), ("8", "8コンボ"), ("12", "12コンボ"), ("16", "16コンボ")], "12", "AA6コンボ+KK6コンボ=12コンボです。"),
        _q("combo-three-suited", "combos", "コンボ計算", "A5s・A4s・A3sの3種類を合わせると、カードが見えていないとき何コンボ？", [("8", "8コンボ"), ("12", "12コンボ"), ("24", "24コンボ"), ("36", "36コンボ")], "12", "各スーテッドハンド4コンボ×3種類=12コンボです。"),
        _q("combo-two-offsuit", "combos", "コンボ計算", "KQoとKJoの2種類を合わせると、カードが見えていないとき何コンボ？", [("12", "12コンボ"), ("16", "16コンボ"), ("24", "24コンボ"), ("32", "32コンボ")], "24", "各オフスート非ペアハンド12コンボ×2種類=24コンボです。"),
        _q("combo-starting-total", "combos", "コンボ計算", "ホールデムで2枚のスターティングハンドの組み合わせ総数は？（順序は区別しない）", [("169", "169"), ("1081", "1081"), ("1326", "1326"), ("2652", "2652")], "1326", "52枚から2枚を選ぶのでC(52,2)=1326です。"),
        _q("combo-aa-three-visible", "combos", "コンボ計算", "Aが3枚見えているとき、相手がAAを持つことは何コンボ残る？", [("0", "0コンボ"), ("1", "1コンボ"), ("3", "3コンボ"), ("6", "6コンボ")], "0", "未確認のAは1枚だけなので、相手が2枚のAを同時に持つことはできません。"),
        _q("combo-ak-one-a-visible", "combos", "コンボ計算", "Aが1枚見えていてKは1枚も見えていません。相手のAK（スート指定なし）は何コンボ？", [("8", "8コンボ"), ("12", "12コンボ"), ("16", "16コンボ"), ("20", "20コンボ")], "12", "残りA3枚×K4枚=12コンボです。"),
    ]


def _tournament_questions() -> list[dict[str, Any]]:
    return [
        _q("icm-risk-premium", "tournament", "トーナメント思考", "ICM上のリスクプレミアムが正のオールイン判断では、通常コール側に必要な勝率は純粋なchipEV基準と比べてどうなる？", [("higher", "高くなる"), ("same", "同じ"), ("lower", "低くなる"), ("zero", "0%になる")], "higher", "敗退リスクの金銭的コストがあるため、一般にchipEVより高いエクイティが必要です。"),
        _q("icm-linear", "tournament", "トーナメント思考", "ICMについて正しい説明は？", [("nonlinear", "2倍のチップが必ず2倍の賞金EVになるわけではない"), ("linear", "チップは常に1枚あたり同じ金銭価値"), ("cards", "ホールカードだけから賞金EVを計算する"), ("rake", "レーキ率を決めるモデル")], "nonlinear", "ICMではチップの金銭価値は非線形です。"),
        _q("icm-input", "tournament", "トーナメント思考", "標準的なICM計算で中心となる入力はどれ？", [("stacks", "各プレイヤーのスタックと賞金構造"), ("cards", "各プレイヤーのホールカード"), ("tells", "ライブテル"), ("rake", "キャッシュゲームのレーキ")], "stacks", "ICMはスタック分布とpayoutを使って賞金EVを近似します。"),
        _q("bubble-factor", "tournament", "トーナメント思考", "バブルファクターが1より大きい状況の意味として最も近いものは？", [("asymmetry", "同量のチップを失う金銭的痛みが、得る利益より大きい"), ("double", "勝てば賞金EVが必ず2倍"), ("norisk", "敗退リスクがない"), ("rake", "レーキが1%以上ある")], "asymmetry", "失うチップと得るチップの賞金EVが非対称になる圧力を表します。"),
        _q("satellite", "tournament", "トーナメント思考", "同額シートを獲得するサテライトのバブル付近で、通過に十分な大スタックの追加チップ価値が低下しやすい主因は？", [("seat", "1位でもギリギリ通過でも得るシート価値が同じだから"), ("rake", "レーキが突然増えるから"), ("blind", "ブラインドが停止するから"), ("cards", "強いカードが配られにくくなるから")], "seat", "同一価値のシートを争う形式では、通過に十分な量を超えた追加チップの限界価値が小さくなります。"),
        _q("icm-when", "tournament", "トーナメント思考", "ICMの影響が特に大きくなりやすい局面は？", [("payout", "バブルやファイナルテーブルなど賞金ジャンプが近い局面"), ("first", "大会最初のハンドなら常に最大"), ("cash", "通常のキャッシュゲーム"), ("practice", "賞金価値のない練習卓")], "payout", "残り人数と賞金差が意思決定へ直結する局面ほどICMの影響が大きくなります。"),
        _q("icm-chip-leader", "tournament", "トーナメント思考", "ファイナルテーブルで他全員をカバーするチップリーダーが持つ構造的な圧力として最も適切なのは？", [("cover", "相手に敗退リスクを負わせられる"), ("cards", "強いカードが配られやすい"), ("blind", "ブラインドを払わなくてよい"), ("fixed", "常にオールインすべき")], "cover", "カバーされた側はオールインで敗退し得るため、チップリーダーはそのリスクを利用できることがあります。"),
        _q("icm-short-double", "tournament", "トーナメント思考", "ICM下でショートスタックがダブルアップしたとき、賞金EVについて一般に正しいのは？", [("notdouble", "チップが2倍でも賞金EVが必ず2倍になるわけではない"), ("double", "賞金EVも必ず正確に2倍"), ("zero", "賞金EVは変わらない"), ("negative", "必ず減る")], "notdouble", "ICMのチップ価値は非線形なので、チップ倍率と賞金EV倍率は一致しません。"),
        _q("icm-cash", "tournament", "トーナメント思考", "通常のキャッシュゲーム判断に標準ICMを直接適用しない主な理由は？", [("cashvalue", "チップ自体が額面の金銭価値を持ち、トーナメント賞金順位への変換が不要だから"), ("cards", "キャッシュではホールカードを使わないから"), ("blinds", "ブラインドがないから"), ("allin", "オールインできないから")], "cashvalue", "標準ICMはトーナメントの有限な賞金構造へチップを対応させるモデルです。"),
        _q("icm-payjump", "tournament", "トーナメント思考", "他条件が同じなら、大きな賞金ジャンプが目前にあるほど一般に何への配慮が重要になる？", [("survival", "敗退リスクと賞金EV"), ("rake", "キャッシュレーキ"), ("deck", "デッキ枚数"), ("seat", "物理的な座席位置")], "survival", "賞金ジャンプが近いほど、チップEVだけでなく敗退による賞金EV損失が重要になります。"),
        _q("icm-zero-sum", "tournament", "トーナメント思考", "ICMで自分の賞金EVが増えるとき、その増加分について最も適切なのは？", [("redistributed", "他プレイヤーの賞金EVから再配分される"), ("created", "大会の賞金総額がその場で増える"), ("rake", "レーキとして消える"), ("chips", "チップ総量が増える")], "redistributed", "固定された賞金総額の中で各プレイヤーの期待値が配分されます。"),
        _q("satellite-first", "tournament", "トーナメント思考", "10人に同額シートが与えられるサテライトで1位通過と10位通過の直接の賞品価値は？", [("same", "同じ"), ("firstdouble", "1位が2倍"), ("tenthzero", "10位は0"), ("stack", "終了スタックに比例")], "same", "同一シートを獲得する形式なら通過順位そのものによる賞品価値は同じです。"),
        _q("icm-cover-not-rule", "tournament", "トーナメント思考", "相手をカバーしているという事実だけから『必ず広くコールすべき』と結論づけられる？", [("no", "いいえ。レンジ・スタック・payout等も必要"), ("yes", "はい。常に広くコール"), ("fold", "常にフォールド"), ("cards", "カードに関係なくオールイン")], "no", "カバーは重要な要因ですが、それだけで最適レンジは決まりません。"),
        _q("icm-model", "tournament", "トーナメント思考", "ICMは何を直接モデル化していない？", [("skill", "将来のスキル差やポジション上の優位"), ("stacks", "現在のスタック量"), ("payout", "賞金構造"), ("players", "残りプレイヤー数")], "skill", "標準ICMは現在スタックとpayoutから近似し、将来のスキル差などは直接モデル化しません。"),
        _q("icm-bubble-call", "tournament", "トーナメント思考", "マネーバブルで同じオールインスポットをchipEVだけで評価した場合と比べ、ICMを考慮したコールレンジは一般にどうなりやすい？", [("tighter", "タイトになりやすい"), ("identical", "必ず完全に同一"), ("anytwo", "必ずAny Two"), ("zero", "必ず0ハンド")], "tighter", "コール側は敗退リスクを負うため、正のリスクプレミアムがある場面ではタイト化しやすいです。"),
    ]


def _action_questions() -> list[dict[str, Any]]:
    return [
        _q("action-squeeze", "action_reasoning", "アクション理解", "UTGがオープン、HJがコール、その後BTNが大きくリレイズ。このBTNのアクションは？", [("squeeze", "スクイーズ"), ("probe", "プローブ"), ("donk", "ドンク"), ("float", "フロート")], "squeeze", "レイザーとコーラーがいる状態へのリレイズなのでスクイーズです。"),
        _q("action-cbet", "action_reasoning", "アクション理解", "BTNがプリフロップでレイズしBBがコール。フロップでBBチェック→BTNベット。このBTNのベットは？", [("cbet", "コンティニュエーションベット"), ("donk", "ドンクベット"), ("probe", "プローブベット"), ("squeeze", "スクイーズ")], "cbet", "前ストリートのアグレッサーが次ストリートでもベットしているためCbetです。"),
        _q("action-probe", "action_reasoning", "アクション理解", "BTNがプリフロップレイズ、BBコール。フロップはBBチェック→BTNチェック。ターンでBBが先にベット。このターンベットは？", [("probe", "プローブベット"), ("cbet", "コンティニュエーションベット"), ("squeeze", "スクイーズ"), ("cold4", "コールド4ベット")], "probe", "アグレッサーがチェックバックした次のストリートにOOP側が先に打つ典型的なprobeです。"),
        _q("action-donk", "action_reasoning", "アクション理解", "BTNがプリフロップレイズ、BBがコール。フロップでBBがBTNの行動前にベット。このBBのベットは？", [("donk", "ドンクベット"), ("cbet", "コンティニュエーションベット"), ("probe", "プローブベット"), ("float", "フロート")], "donk", "前ストリートのアグレッサーではないOOP側から先にベットしているためドンクベットです。"),
        _q("action-threebet", "action_reasoning", "アクション理解", "プリフロップでCOがオープンレイズし、BTNがさらにレイズしました。BTNのレイズは一般に何と呼ぶ？", [("threebet", "3ベット"), ("twobet", "2ベット"), ("fourbet", "4ベット"), ("probe", "プローブ")], "threebet", "ブラインドを1ベット、オープンを2ベットと数える慣習から次のリレイズは3ベットです。"),
        _q("action-checkraise", "action_reasoning", "アクション理解", "フロップでOOPのあなたがチェック。相手がベットし、あなたが同じストリートでレイズ。このラインは？", [("checkraise", "チェックレイズ"), ("donk", "ドンクベット"), ("probe", "プローブベット"), ("squeeze", "スクイーズ")], "checkraise", "先にチェックした後、相手のベットへレイズしているためチェックレイズです。"),
        _q("action-cold4", "action_reasoning", "アクション理解", "COがオープン、BTNが3ベット。まだポットに参加していないSBがさらにリレイズしました。SBのアクションは？", [("cold4", "コールド4ベット"), ("squeeze", "スクイーズ"), ("donk", "ドンク"), ("float", "フロート")], "cold4", "自分がそれまで参加せず、3ベットに対して直接4ベットするためコールド4ベットです。"),
        _q("action-float", "action_reasoning", "アクション理解", "IPでフロップのCbetを比較的弱いハンドでコールし、相手が後のストリートで弱さを見せたらポット獲得を狙うラインは？", [("float", "フロート"), ("donk", "ドンク"), ("squeeze", "スクイーズ"), ("limp", "リンプ")], "float", "後のストリートでポット獲得を狙う軽いフロップコールはフロートです。"),
        _q("action-limp-reraise", "action_reasoning", "アクション理解", "UTGがリンプ。BTNがレイズし、UTGがさらにリレイズしました。UTGのラインは？", [("limpreraise", "リンプ・リレイズ"), ("coldcall", "コールドコール"), ("probe", "プローブ"), ("donk", "ドンク")], "limpreraise", "最初にリンプした本人が後からレイズに対してリレイズしています。"),
        _q("action-delayed-cbet", "action_reasoning", "アクション理解", "プリフロップレイザーがフロップをチェックバックし、相手がターンもチェックした後にターンでベット。このベットは一般に？", [("delayed", "ディレイドCbet"), ("donk", "ドンクベット"), ("squeeze", "スクイーズ"), ("cold4", "コールド4ベット")], "delayed", "フロップでCbetせず、次のストリートで行うCbetをディレイドCbetと呼びます。"),
        _q("action-checkback", "action_reasoning", "アクション理解", "IPプレイヤーが相手のチェック後に自分もチェックしてストリートを終えるアクションは？", [("checkback", "チェックバック"), ("checkraise", "チェックレイズ"), ("donk", "ドンク"), ("squeeze", "スクイーズ")], "checkback", "IP側が相手のチェックに続いてチェックするのがチェックバックです。"),
        _q("action-isolate", "action_reasoning", "アクション理解", "複数のリンプに対してレイズし、主にリンプしたプレイヤーとの少人数ポットを狙うレイズは？", [("isolate", "アイソレーションレイズ"), ("probe", "プローブ"), ("float", "フロート"), ("donk", "ドンク")], "isolate", "リンプしたプレイヤーを主な相手にする目的のレイズをアイソレーションレイズと呼びます。"),
        _q("action-overcall", "action_reasoning", "アクション理解", "1人がベットし、別のプレイヤーがコールした後、さらに別のプレイヤーがコール。この最後のコールは？", [("overcall", "オーバーコール"), ("cold4", "コールド4ベット"), ("squeeze", "スクイーズ"), ("checkraise", "チェックレイズ")], "overcall", "すでに1人以上のコーラーがいるベットへ追加でコールすることをオーバーコールと呼びます。"),
        _q("action-openlimp", "action_reasoning", "アクション理解", "プリフロップでまだ誰も参加していない状態から、最初のプレイヤーがBB額だけコールして参加。このアクションは？", [("openlimp", "オープンリンプ"), ("coldcall", "コールドコール"), ("overcall", "オーバーコール"), ("probe", "プローブ")], "openlimp", "誰も参加していないポットへ最初にリンプするためオープンリンプです。"),
        _q("action-backraise", "action_reasoning", "アクション理解", "プリフロップで最初はコールしたプレイヤーが、後ろからスクイーズされた後に再びアクションが戻ってリレイズ。このラインは？", [("backraise", "バックレイズ"), ("donk", "ドンク"), ("probe", "プローブ"), ("float", "フロート")], "backraise", "最初にコールしたプレイヤーが後続のレイズに対して再度レイズするのがバックレイズです。"),
    ]


def _mdf_questions() -> list[dict[str, Any]]:
    rows = [
        (100, 50, 67), (100, 100, 50), (100, 200, 33), (150, 50, 75),
        (120, 80, 60), (80, 40, 67), (200, 100, 67), (200, 200, 50),
        (300, 100, 75), (50, 100, 33), (120, 30, 80), (80, 120, 40),
        (200, 300, 40), (75, 25, 75), (150, 100, 60),
    ]
    return [
        _q(
            f"mdf-{pot}-{bet}", "mdf", "MDF",
            f"ポット{pot}に相手が{bet}をベット。単純なMDF = Pot / (Pot + Bet) で計算すると約何%？",
            _broad_pct(correct), str(correct),
            f"{pot} / ({pot} + {bet}) ≈ {correct}%です。",
        ) for pot, bet, correct in rows
    ]


def _spr_questions() -> list[dict[str, Any]]:
    rows = [
        (1200, 3600, "3", ["1", "3", "6", "9"]), (1000, 2000, "2", ["1", "2", "5", "10"]),
        (1500, 4500, "3", ["1.5", "3", "6", "9"]), (2000, 5000, "2.5", ["1", "2.5", "5", "10"]),
        (800, 2400, "3", ["1", "3", "6", "8"]), (1200, 1800, "1.5", ["0.5", "1.5", "3", "6"]),
        (1000, 4000, "4", ["1", "2", "4", "8"]), (2000, 2000, "1", ["0.5", "1", "2", "4"]),
        (500, 3000, "6", ["1.5", "3", "6", "12"]), (1600, 4000, "2.5", ["1", "2.5", "5", "8"]),
        (900, 1800, "2", ["0.5", "2", "4", "9"]), (2500, 10000, "4", ["1", "2", "4", "10"]),
        (600, 900, "1.5", ["0.5", "1.5", "3", "6"]), (1250, 6250, "5", ["1", "2.5", "5", "10"]),
        (2000, 6000, "3", ["1", "3", "6", "12"]),
    ]
    return [
        _q(
            f"spr-{stack}-{pot}", "spr", "SPR",
            f"ストリート開始時のポットが{pot:,}、エフェクティブスタックが{stack:,}。SPRはいくつ？",
            [(v, v) for v in options], correct,
            f"{stack:,} / {pot:,} = {correct}です。",
        ) for pot, stack, correct, options in rows
    ]


def _outs_questions() -> list[dict[str, Any]]:
    rows = [(4, 9), (5, 11), (6, 13), (7, 15), (8, 17), (9, 20), (10, 22), (12, 26), (14, 30), (15, 33), (16, 35), (18, 39), (20, 43)]
    return [
        _q(
            f"outs-{outs}", "outs", "確率・アウツ",
            f"ターンでリバー1枚だけを残し、確実に勝ちにつながるクリーンアウトが{outs}枚。未知カード46枚として、リバーで引く確率は約何%？",
            _broad_pct(correct), str(correct),
            f"{outs} / 46 ≈ {correct}%です。",
        ) for outs, correct in rows
    ]


POOLS: dict[str, list[dict[str, Any]]] = {
    "pot_odds": _pot_odds_questions(),
    "bluff_math": _bluff_questions(),
    "equity_decision": _equity_questions(),
    "vocabulary": _vocabulary_questions(),
    "combos": _combo_questions(),
    "tournament": _tournament_questions(),
    "action_reasoning": _action_questions(),
    "mdf": _mdf_questions(),
    "spr": _spr_questions(),
    "outs": _outs_questions(),
}

CATEGORY_ORDER = tuple(POOLS.keys())
assert len(CATEGORY_ORDER) == DAILY_QUIZ_SIZE
assert all(len(pool) >= MIN_VARIANTS_PER_CATEGORY for pool in POOLS.values())
_all_keys = [q["key"] for pool in POOLS.values() for q in pool]
_all_prompts = [q["prompt"] for pool in POOLS.values() for q in pool]
assert len(_all_keys) == len(set(_all_keys))
assert len(_all_prompts) == len(set(_all_prompts))
TOTAL_QUESTION_BANK = len(_all_keys)


def today_jst() -> str:
    return datetime.now(JST).date().isoformat()


def build_daily_questions(day: str) -> list[dict[str, Any]]:
    parsed = date.fromisoformat(day)
    ordinal = parsed.toordinal()
    questions: list[dict[str, Any]] = []
    for slot, category in enumerate(CATEGORY_ORDER, 1):
        pool = POOLS[category]
        index = (ordinal + slot * 3) % len(pool)
        item = copy.deepcopy(pool[index])
        seed = hashlib.sha256(f"{QUIZ_SET_VERSION}:{day}:{item['key']}".encode()).digest()[0]
        rotate = seed % len(item["choices"])
        item["choices"] = item["choices"][rotate:] + item["choices"][:rotate]
        item["slot"] = slot
        item["definition_id"] = f"dq-{day.replace('-', '')}-{slot:02d}-{item['key']}"
        questions.append(item)
    return questions


def _attempt_id(user_id: int, definition_id: str) -> str:
    digest = hashlib.sha256(f"{user_id}:{definition_id}".encode()).hexdigest()[:28]
    return f"dqa-{digest}"


def _public_question(question: dict[str, Any], attempt_id: str, progress: dict[str, int], day: str) -> dict[str, Any]:
    return {
        "id": attempt_id,
        "date": day,
        "slot": int(question["slot"]),
        "type": "single_select",
        "category": question["category"],
        "category_label": question["category_label"],
        "prompt": question["prompt"],
        "choices": question["choices"],
        "reward": DAILY_QUIZ_REWARD,
        "progress": progress,
        "done": False,
        "bank_size": TOTAL_QUESTION_BANK,
    }


def _progress(con, user_id: int, day: str) -> dict[str, int]:
    row = con.execute(
        "SELECT COUNT(*) AS answered, "
        "COALESCE(SUM(CASE WHEN is_correct=1 THEN 1 ELSE 0 END),0) AS correct, "
        "COALESCE(SUM(reward_awarded),0) AS earned "
        "FROM daily_quiz_attempts WHERE user_id=? AND quiz_date=? AND answer IS NOT NULL",
        (user_id, day),
    ).fetchone()
    answered = int(row["answered"] or 0)
    return {
        "answered": answered,
        "correct": int(row["correct"] or 0),
        "earned": int(row["earned"] or 0),
        "total": DAILY_QUIZ_SIZE,
        "remaining": max(0, DAILY_QUIZ_SIZE - answered),
        "max_daily_reward": DAILY_QUIZ_SIZE * DAILY_QUIZ_REWARD,
    }


def _ensure_schema(db) -> None:
    uid_type = "BIGINT" if getattr(db, "IS_POSTGRES", False) else "INTEGER"
    ddl = (
        "CREATE TABLE IF NOT EXISTS daily_quiz_attempts("
        "id TEXT PRIMARY KEY,"
        f"user_id {uid_type} NOT NULL REFERENCES users(id),"
        "quiz_date TEXT NOT NULL,"
        "slot INTEGER NOT NULL,"
        "question_key TEXT NOT NULL,"
        "correct_answer TEXT NOT NULL,"
        "choices_json TEXT NOT NULL,"
        "answer TEXT,"
        "is_correct INTEGER,"
        "reward_awarded INTEGER NOT NULL DEFAULT 0,"
        "created_at TEXT NOT NULL,"
        "answered_at TEXT,"
        "UNIQUE(user_id,quiz_date,slot),"
        "UNIQUE(user_id,quiz_date,question_key))"
    )
    with db.connect() as con:
        con.execute(ddl)
        con.execute("CREATE INDEX IF NOT EXISTS idx_daily_quiz_user_date ON daily_quiz_attempts(user_id,quiz_date)")


def install(app, server, db) -> None:
    if getattr(app.state, "jj_daily_quiz_v2_installed", False):
        return
    _ensure_schema(db)
    retired = {"/api/quiz/question", "/api/quiz/answer"}
    app.router.routes[:] = [route for route in app.router.routes if getattr(route, "path", None) not in retired]

    @app.get("/api/quiz/question", include_in_schema=False)
    def daily_quiz_question(user=Depends(server.current_user)):
        day = today_jst()
        questions = build_daily_questions(day)
        by_slot = {int(q["slot"]): q for q in questions}
        user_id = int(user["id"])
        with db.connect() as con:
            progress = _progress(con, user_id, day)
            if progress["answered"] >= DAILY_QUIZ_SIZE:
                return {"done": True, "date": day, "reward": DAILY_QUIZ_REWARD, "progress": progress, "bank_size": TOTAL_QUESTION_BANK}
            rows = con.execute(
                "SELECT slot,answer FROM daily_quiz_attempts WHERE user_id=? AND quiz_date=? ORDER BY slot",
                (user_id, day),
            ).fetchall()
            answered_slots = {int(row["slot"]) for row in rows if row["answer"] is not None}
            next_slot = next(slot for slot in range(1, DAILY_QUIZ_SIZE + 1) if slot not in answered_slots)
            q = by_slot[next_slot]
            attempt_id = _attempt_id(user_id, q["definition_id"])
            values = [str(choice["value"]) for choice in q["choices"]]
            con.execute(
                "INSERT INTO daily_quiz_attempts(id,user_id,quiz_date,slot,question_key,correct_answer,choices_json,answer,is_correct,reward_awarded,created_at,answered_at) "
                "VALUES (?,?,?,?,?,?,?,NULL,NULL,0,?,NULL) ON CONFLICT(user_id,quiz_date,slot) DO NOTHING",
                (attempt_id, user_id, day, next_slot, q["key"], q["correct"], json.dumps(values, separators=(",", ":")), db.utcnow()),
            )
            row = con.execute(
                "SELECT id,question_key,answer FROM daily_quiz_attempts WHERE user_id=? AND quiz_date=? AND slot=?",
                (user_id, day, next_slot),
            ).fetchone()
            if not row or str(row["id"]) != attempt_id or str(row["question_key"]) != q["key"]:
                raise HTTPException(409, "本日のクイズ構成が更新されました。画面を再読み込みしてください")
        return _public_question(q, attempt_id, progress, day)

    @app.post("/api/quiz/answer", include_in_schema=False)
    def daily_quiz_answer(payload: DailyQuizAnswerIn, user=Depends(server.current_user)):
        day = today_jst()
        user_id = int(user["id"])
        questions = build_daily_questions(day)
        by_key = {q["key"]: q for q in questions}
        now = db.utcnow()
        with db.connect() as con:
            row = con.execute(
                "SELECT id,quiz_date,slot,question_key,correct_answer,choices_json,answer,reward_awarded FROM daily_quiz_attempts WHERE id=? AND user_id=?",
                (payload.question_id, user_id),
            ).fetchone()
            if not row:
                raise HTTPException(404, "この問題はまだ開始されていません")
            if str(row["quiz_date"]) != day:
                raise HTTPException(409, "日付が変わりました。今日のクイズを再読み込みしてください")
            q = by_key.get(str(row["question_key"]))
            if q is None or int(q["slot"]) != int(row["slot"]):
                raise HTTPException(409, "本日のクイズ構成が更新されました。画面を再読み込みしてください")
            allowed = {str(choice["value"]) for choice in q["choices"]}
            answer = str(payload.answer)
            if answer not in allowed:
                raise HTTPException(400, "選択肢にない回答です")
            if row["answer"] is not None:
                progress = _progress(con, user_id, day)
                correct_answer = str(row["correct_answer"])
                return {
                    "ok": True, "already_answered": True,
                    "correct": str(row["answer"]) == correct_answer,
                    "correct_answer": correct_answer,
                    "correct_label": next(c["label"] for c in q["choices"] if str(c["value"]) == correct_answer),
                    "explanation": q["explanation"], "awarded": 0, "progress": progress,
                }
            correct = answer == str(row["correct_answer"])
            cur = con.execute(
                "UPDATE daily_quiz_attempts SET answer=?,is_correct=?,answered_at=? WHERE id=? AND user_id=? AND quiz_date=? AND answer IS NULL",
                (answer, 1 if correct else 0, now, payload.question_id, user_id, day),
            )
            if int(getattr(cur, "rowcount", 0) or 0) != 1:
                progress = _progress(con, user_id, day)
                return {"ok": True, "already_answered": True, "correct": False, "awarded": 0, "progress": progress}
            txid = f"quiz-v2-{user_id}-{day}-{int(q['slot']):02d}"
            ledger = con.execute(
                "INSERT INTO point_ledger(id,user_id,amount,kind,reason,effective_at,created_by,created_at,reversal_of) VALUES (?,?,?,?,?,?,?,?,NULL) ON CONFLICT(id) DO NOTHING",
                (txid, user_id, DAILY_QUIZ_REWARD, "quiz_reward", f"デイリーポーカークイズ {day} #{q['slot']}", now, user_id, now),
            )
            awarded = DAILY_QUIZ_REWARD if int(getattr(ledger, "rowcount", 0) or 0) == 1 else 0
            con.execute("UPDATE daily_quiz_attempts SET reward_awarded=? WHERE id=? AND user_id=?", (awarded, payload.question_id, user_id))
            progress = _progress(con, user_id, day)
        return {
            "ok": True, "already_answered": False, "correct": correct,
            "correct_answer": q["correct"],
            "correct_label": next(c["label"] for c in q["choices"] if str(c["value"]) == q["correct"]),
            "explanation": q["explanation"], "awarded": awarded, "progress": progress,
        }

    app.state.jj_daily_quiz_v2_installed = True

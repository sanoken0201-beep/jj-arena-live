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
QUIZ_SET_VERSION = "2026-09-v2"


class DailyQuizAnswerIn(BaseModel):
    question_id: str = Field(min_length=8, max_length=120)
    answer: str = Field(min_length=1, max_length=80)


def _q(key: str, category: str, category_label: str, prompt: str, choices: list[tuple[str, str]], correct: str, explanation: str) -> dict[str, Any]:
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


POOLS: dict[str, list[dict[str, Any]]] = {
    "pot_odds": [
        _q("pot-100-75", "pot_odds", "ポットオッズ", "ポット100に相手が75をベット。あなたは75をコールすればショーダウンで終了するとします。コールに必要な最低勝率は約何%？", _pct([30, 50, 70, 80]), "30", "コール後の最終ポットは250。75 / 250 = 30%です。"),
        _q("pot-100-50", "pot_odds", "ポットオッズ", "ポット100に相手が50をベット。追加のベットはないものとします。コールに必要な最低勝率は？", _pct([25, 40, 60, 75]), "25", "50を払って最終ポット200を争うので、50 / 200 = 25%です。"),
        _q("pot-100-100", "pot_odds", "ポットオッズ", "ポット100に相手が100をベット。オールインで追加アクションはありません。コールに必要な最低勝率は約何%？", _pct([33, 50, 67, 80]), "33", "100を払って最終ポット300を争うので、100 / 300 ≈ 33%です。"),
        _q("pot-150-50", "pot_odds", "ポットオッズ", "ポット150に相手が50をベット。コール後はショーダウンです。必要な最低勝率は？", _pct([20, 40, 60, 80]), "20", "50を払って最終ポット250を争うので、50 / 250 = 20%です。"),
        _q("pot-100-25", "pot_odds", "ポットオッズ", "ポット100に相手が25をベット。コール後はショーダウンです。必要な最低勝率は約何%？", _pct([17, 33, 50, 83]), "17", "25を払って最終ポット150を争うので、25 / 150 ≈ 16.7%です。"),
        _q("pot-120-80", "pot_odds", "ポットオッズ", "ポット120に相手が80をベット。コール後はショーダウンです。必要な最低勝率は約何%？", _pct([29, 50, 71, 80]), "29", "80を払って最終ポット280を争うので、80 / 280 ≈ 28.6%です。"),
    ],
    "bluff_math": [
        _q("bluff-100-50", "bluff_math", "ブラフ損益分岐", "リバーでポット100に50を純粋なブラフとしてベットします。コールされたら必ず負けるとすると、必要な最低フォールド率は約何%？", _pct([33, 50, 67, 80]), "33", "50をリスクして100を獲得するので、50 / (100 + 50) ≈ 33%のフォールドが必要です。"),
        _q("bluff-100-100", "bluff_math", "ブラフ損益分岐", "リバーでポット100に100を純粋なブラフとしてベット。最低どの程度フォールドされれば損益分岐？", _pct([25, 50, 67, 75]), "50", "100をリスクして100を獲得するので、100 / 200 = 50%です。"),
        _q("bluff-100-200", "bluff_math", "ブラフ損益分岐", "リバーでポット100に200のオーバーベットブラフ。コールされたら必ず負けます。必要な最低フォールド率は約何%？", _pct([33, 50, 67, 80]), "67", "200をリスクして100を獲得するので、200 / 300 ≈ 66.7%です。"),
        _q("bluff-150-50", "bluff_math", "ブラフ損益分岐", "リバーでポット150に50を純粋なブラフとしてベット。必要な最低フォールド率は？", _pct([25, 50, 75, 80]), "25", "50をリスクして150を獲得するので、50 / 200 = 25%です。"),
        _q("bluff-80-120", "bluff_math", "ブラフ損益分岐", "リバーでポット80に120を純粋なブラフとしてベット。必要な最低フォールド率は？", _pct([20, 40, 60, 80]), "60", "120をリスクして80を獲得するので、120 / 200 = 60%です。"),
        _q("bluff-200-50", "bluff_math", "ブラフ損益分岐", "リバーでポット200に50を純粋なブラフとしてベット。必要な最低フォールド率は？", _pct([20, 40, 60, 80]), "20", "50をリスクして200を獲得するので、50 / 250 = 20%です。"),
    ],
    "equity_decision": [
        _q("decision-30-35", "equity_decision", "意思決定", "相手のオールインに対するコール必要勝率が30%。あなたの推定勝率は35%です。レーキ・ICM・将来アクションを無視したチップEVだけなら？", [("call", "コール"), ("fold", "フォールド"), ("equal", "どちらも同じEV"), ("unknown", "情報不足")], "call", "35%は必要勝率30%を上回るため、チップEVではコールがプラスです。"),
        _q("decision-30-24", "equity_decision", "意思決定", "相手のオールインに対するコール必要勝率が30%。推定勝率は24%。レーキ・ICMを無視したチップEVだけなら？", [("call", "コール"), ("fold", "フォールド"), ("equal", "どちらも同じEV"), ("unknown", "情報不足")], "fold", "24%は必要勝率30%を下回るため、チップEVではフォールドです。"),
        _q("decision-33-40", "equity_decision", "意思決定", "必要勝率33%のオールインコールで、推定勝率40%。レーキ・ICMなしなら最も適切なのは？", [("call", "コール"), ("fold", "フォールド"), ("equal", "どちらも同じEV"), ("unknown", "情報不足")], "call", "40%は33%を上回るため、コールの期待値がフォールドを上回ります。"),
        _q("decision-33-28", "equity_decision", "意思決定", "必要勝率33%のオールインコールで、推定勝率28%。レーキ・ICMなしなら？", [("call", "コール"), ("fold", "フォールド"), ("equal", "どちらも同じEV"), ("unknown", "情報不足")], "fold", "28%は必要勝率33%を下回ります。"),
        _q("decision-25-25", "equity_decision", "意思決定", "必要勝率25%のオールインコールで、推定勝率もちょうど25%。レーキ・ICM・タイを無視すると？", [("call", "コールが明確に得"), ("fold", "フォールドが明確に得"), ("equal", "損益分岐で同じEV"), ("unknown", "情報不足")], "equal", "推定勝率と必要勝率が一致しているので損益分岐です。"),
        _q("decision-20-18", "equity_decision", "意思決定", "必要勝率20%のオールインコールで、推定勝率18%。レーキ・ICMなしなら？", [("call", "コール"), ("fold", "フォールド"), ("equal", "どちらも同じEV"), ("unknown", "情報不足")], "fold", "18%は必要勝率20%を下回るためフォールドです。"),
    ],
    "vocabulary": [
        _q("term-squeeze", "vocabulary", "ポーカー語彙", "プリフロップで、1人がオープンレイズし、別の1人以上がコールした後にさらにリレイズするプレイは？", [("squeeze", "スクイーズ"), ("probe", "プローブベット"), ("float", "フロート"), ("donk", "ドンクベット")], "squeeze", "オープンレイズとコーラーの両方へ圧力をかけるリレイズをスクイーズと呼びます。"),
        _q("term-blocker", "vocabulary", "ポーカー語彙", "自分が特定のカードを持つことで、相手がある強いハンドを持てる組み合わせ数が減る効果は？", [("blocker", "ブロッカー"), ("rake", "レーキ"), ("overlay", "オーバーレイ"), ("variance", "バリアンス")], "blocker", "自分のカードが相手の候補コンボを物理的に減らす効果がブロッカーです。"),
        _q("term-capped", "vocabulary", "ポーカー語彙", "アクションの経過から、レンジ上限に非常に強いハンドがほとんど含まれない状態は？", [("capped", "キャップされたレンジ"), ("polar", "ポラライズレンジ"), ("merged", "マージドレンジ"), ("uncapped", "アンキャップドレンジ")], "capped", "非常に強いハンドを持ちにくく、レンジの上限が制限された状態をcappedと呼びます。"),
        _q("term-polar", "vocabulary", "ポーカー語彙", "非常に強いバリューハンドとブラフを中心に構成され、中間の強さが少ないベットレンジは？", [("polar", "ポラライズ"), ("linear", "リニア"), ("capped", "キャップ"), ("condensed", "コンデンス")], "polar", "強いバリューとブラフの両端を中心にした構造がポラライズです。"),
        _q("term-merged", "vocabulary", "ポーカー語彙", "強いハンドから中程度のバリューハンドまで連続的に含めるレイズレンジを表す語として最も近いものは？", [("merged", "マージド"), ("polar", "ポラライズ"), ("capped", "キャップ"), ("air", "エアー")], "merged", "強さが連続したバリュー寄りのレンジはマージド／リニアな構造です。"),
        _q("term-spr", "vocabulary", "ポーカー語彙", "SPRが表す比率は？", [("spr", "エフェクティブスタック ÷ ポット"), ("mdf", "ポット ÷ ベット"), ("equity", "勝率 ÷ オッズ"), ("rake", "レーキ ÷ ポット")], "spr", "SPRはStack-to-Pot Ratioで、通常はストリート開始時のエフェクティブスタックをポットで割ります。"),
        _q("term-mdf", "vocabulary", "ポーカー語彙", "MDFの意味として最も適切なのは？", [("mdf", "相手の自動利益ブラフを防ぐ基準となる最低ディフェンス頻度"), ("spr", "スタックとポットの比率"), ("icm", "賞金をチップへ変換する固定倍率"), ("ev", "勝率そのもの")], "mdf", "MDFはMinimum Defense Frequencyです。実戦の最適防御頻度と常に同じとは限りません。"),
        _q("term-icm", "vocabulary", "ポーカー語彙", "ICMが扱うものとして最も適切なのは？", [("icm", "トーナメントのスタック分布と賞金構造から各スタックの金銭価値を近似するモデル"), ("spr", "ポットに対するスタック比率"), ("mdf", "最低ディフェンス頻度"), ("equity", "ハンドのショーダウン勝率")], "icm", "ICMはIndependent Chip Modelで、トーナメントチップの金銭価値を非線形に近似します。"),
        _q("term-nut-advantage", "vocabulary", "ポーカー語彙", "一方のレンジにナッツ級の非常に強いハンドが相対的に多い状態は？", [("nut", "ナッツアドバンテージ"), ("range", "レンジアドバンテージ"), ("blocker", "ブロッカー"), ("overlay", "オーバーレイ")], "nut", "レンジ上部の最強クラスの組み合わせを多く持てる側にはナッツアドバンテージがあります。"),
        _q("term-range-advantage", "vocabulary", "ポーカー語彙", "レンジ全体の平均的なエクイティが相手より高い状態を表す語として最も近いものは？", [("range", "レンジアドバンテージ"), ("nut", "ナッツアドバンテージ"), ("squeeze", "スクイーズ"), ("block", "ブロックベット")], "range", "レンジ全体で平均的に優位な側をレンジアドバンテージがあると表現します。"),
        _q("term-donk", "vocabulary", "ポーカー語彙", "前ストリートのアグレッサーではないOOPプレイヤーが、次ストリートでそのアグレッサーより先にベットするプレイは？", [("donk", "ドンクベット"), ("cbet", "コンティニュエーションベット"), ("squeeze", "スクイーズ"), ("coldcall", "コールドコール")], "donk", "前ストリートのアグレッサーに対してOOPから先に打つベットをドンクベットと呼びます。"),
        _q("term-overbet", "vocabulary", "ポーカー語彙", "オーバーベットの一般的な意味は？", [("overbet", "現在のポット額を上回るサイズのベット"), ("allin", "必ずオールインになるベット"), ("min", "最小レイズ"), ("threebet", "プリフロップ3ベット")], "overbet", "ポット額より大きいベットサイズをオーバーベットと呼びます。"),
    ],
    "combos": [
        _q("combo-pair", "combos", "コンボ計算", "ホールデムで、特定のポケットペア（例: 88）はプリフロップで何コンボある？", [("4", "4コンボ"), ("6", "6コンボ"), ("12", "12コンボ"), ("16", "16コンボ")], "6", "同じランク4枚から2枚を選ぶので C(4,2)=6コンボです。"),
        _q("combo-suited", "combos", "コンボ計算", "特定のスーテッド非ペアハンド（例: A5s）は何コンボある？", [("4", "4コンボ"), ("6", "6コンボ"), ("12", "12コンボ"), ("16", "16コンボ")], "4", "4つのスートそれぞれに1通りあるため4コンボです。"),
        _q("combo-offsuit", "combos", "コンボ計算", "特定のオフスート非ペアハンド（例: KQo）は何コンボある？", [("4", "4コンボ"), ("6", "6コンボ"), ("12", "12コンボ"), ("16", "16コンボ")], "12", "全16コンボから4つのスーテッドを除き、12コンボです。"),
        _q("combo-ak", "combos", "コンボ計算", "カードが1枚も見えていないとき、AK（suitedとoffsuitの両方）は合計何コンボ？", [("4", "4コンボ"), ("9", "9コンボ"), ("12", "12コンボ"), ("16", "16コンボ")], "16", "Aは4枚、Kも4枚なので4×4=16コンボです。"),
        _q("combo-aa-block", "combos", "コンボ計算", "あなたがAを1枚持っています。相手がAAを持てる残りコンボ数は？", [("1", "1コンボ"), ("3", "3コンボ"), ("6", "6コンボ"), ("12", "12コンボ")], "3", "残りAは3枚。その3枚から2枚を選ぶので C(3,2)=3コンボです。"),
        _q("combo-ak-block", "combos", "コンボ計算", "あなたがAを1枚とKを1枚持っています。相手がAKを持てる残りコンボ数は？", [("4", "4コンボ"), ("6", "6コンボ"), ("9", "9コンボ"), ("12", "12コンボ")], "9", "残りAが3枚、残りKが3枚なので3×3=9コンボです。"),
    ],
    "tournament": [
        _q("icm-risk-premium", "tournament", "トーナメント思考", "ICM上のリスクプレミアムが正のオールイン判断では、通常、コール側に必要な勝率は純粋なchipEV基準と比べてどうなる？", [("higher", "高くなる"), ("same", "同じ"), ("lower", "低くなる"), ("zero", "0%になる")], "higher", "敗退リスクの金銭的コストがあるため、一般にコールにはchipEVより高いエクイティが必要です。"),
        _q("icm-linear", "tournament", "トーナメント思考", "ICMについて正しい説明は？", [("nonlinear", "チップの金銭価値は非線形で、2倍のチップが必ず2倍の賞金EVになるわけではない"), ("linear", "チップは常に1枚あたり同じ金銭価値"), ("cards", "ホールカードだけから賞金EVを計算する"), ("rake", "レーキ率を決めるモデル")], "nonlinear", "ICMでは追加チップの限界価値が一定ではありません。"),
        _q("icm-input", "tournament", "トーナメント思考", "標準的なICM計算で中心となる入力はどれ？", [("stacks", "各プレイヤーのスタックと賞金構造"), ("cards", "各プレイヤーのホールカード"), ("tells", "ライブテル"), ("rake", "キャッシュゲームのレーキ")], "stacks", "ICMはスタック分布とpayoutを使って賞金EVを近似します。"),
        _q("bubble-factor", "tournament", "トーナメント思考", "バブルファクターが1より大きい状況の意味として最も近いものは？", [("asymmetry", "同量のチップを失う金銭的痛みが、得る利益より大きい"), ("double", "勝てば必ず賞金EVが2倍"), ("norisk", "敗退リスクが存在しない"), ("rake", "レーキが1%以上ある")], "asymmetry", "バブルファクターは、失うチップと得るチップの賞金EVが非対称になる圧力を表します。"),
        _q("satellite", "tournament", "トーナメント思考", "同額のシートを獲得するサテライトのバブル付近で、すでに十分大きなスタックを持つ場合に追加チップの価値が低下しやすい主因は？", [("seat", "1位でもギリギリ通過でも得るシート価値が同じだから"), ("rake", "レーキが突然増えるから"), ("blind", "ブラインドが停止するから"), ("cards", "強いカードが配られにくくなるから")], "seat", "同一価値のシートを争う形式では、通過に十分なスタックを超えた追加チップの限界価値が小さくなります。"),
        _q("icm-when", "tournament", "トーナメント思考", "ICMの影響が特に大きくなりやすい局面は？", [("payout", "バブルやファイナルテーブルなど賞金ジャンプが近い局面"), ("firsthand", "大会最初のハンドなら常に最大"), ("cash", "通常のキャッシュゲーム"), ("practice", "チップに賞金価値のない練習卓")], "payout", "残り人数と賞金差が意思決定に直結する局面ほどICMの影響が大きくなります。"),
    ],
    "action_reasoning": [
        _q("action-squeeze", "action_reasoning", "アクション理解", "UTGがオープン、HJがコール、その後BTNが大きくリレイズ。このBTNのアクションを最も正確に表す語は？", [("squeeze", "スクイーズ"), ("probe", "プローブ"), ("donk", "ドンク"), ("float", "フロート")], "squeeze", "レイザーとコーラーがいる状態へのリレイズなのでスクイーズです。"),
        _q("action-cbet", "action_reasoning", "アクション理解", "BTNがプリフロップでレイズしBBがコール。フロップでBBがチェックしBTNがベット。このBTNのベットは？", [("cbet", "コンティニュエーションベット"), ("donk", "ドンクベット"), ("probe", "プローブベット"), ("squeeze", "スクイーズ")], "cbet", "前ストリートのアグレッサーが次ストリートでもベットしているためCbetです。"),
        _q("action-probe", "action_reasoning", "アクション理解", "BTNがプリフロップレイズ、BBがコール。フロップはBBチェック→BTNチェック。ターンでBBが先にベット。このターンベットは？", [("probe", "プローブベット"), ("cbet", "コンティニュエーションベット"), ("squeeze", "スクイーズ"), ("cold4", "コールド4ベット")], "probe", "前ストリートでアグレッサーがチェックバックした後、OOPが次ストリートで先に打つ典型的なprobeです。"),
        _q("action-donk", "action_reasoning", "アクション理解", "BTNがプリフロップレイズ、BBがコール。フロップでBBがBTNの行動前にベット。このBBのベットは？", [("donk", "ドンクベット"), ("cbet", "コンティニュエーションベット"), ("probe", "プローブベット"), ("float", "フロート")], "donk", "前ストリートのアグレッサーではないOOP側から先にベットしているためドンクベットです。"),
        _q("action-threebet", "action_reasoning", "アクション理解", "プリフロップでCOがオープンレイズし、BTNがさらにレイズしました。BTNのレイズは一般に何と呼ぶ？", [("threebet", "3ベット"), ("twobet", "2ベット"), ("fourbet", "4ベット"), ("probe", "プローブ")], "threebet", "ブラインドを1ベット、オープンレイズを2ベットと数える慣習から、次のリレイズは3ベットです。"),
        _q("action-checkraise", "action_reasoning", "アクション理解", "フロップでOOPのあなたがチェック。相手がベットし、あなたが同じストリートでレイズしました。このラインは？", [("checkraise", "チェックレイズ"), ("donk", "ドンクベット"), ("probe", "プローブベット"), ("squeeze", "スクイーズ")], "checkraise", "先にチェックした後、相手のベットに対してレイズしているためチェックレイズです。"),
    ],
    "mdf": [
        _q("mdf-100-50", "mdf", "MDF", "ポット100に相手が50をベット。単純なMDF = Pot / (Pot + Bet) で計算すると約何%？", _pct([25, 50, 67, 80]), "67", "100 / 150 ≈ 66.7%です。"),
        _q("mdf-100-100", "mdf", "MDF", "ポット100に相手が100をベット。単純なMDFは？", _pct([25, 50, 67, 80]), "50", "100 / 200 = 50%です。"),
        _q("mdf-100-200", "mdf", "MDF", "ポット100に相手が200をベット。単純なMDFは約何%？", _pct([20, 33, 50, 80]), "33", "100 / 300 ≈ 33.3%です。"),
        _q("mdf-150-50", "mdf", "MDF", "ポット150に相手が50をベット。単純なMDFは？", _pct([25, 50, 75, 90]), "75", "150 / 200 = 75%です。"),
        _q("mdf-120-80", "mdf", "MDF", "ポット120に相手が80をベット。単純なMDFは？", _pct([20, 40, 60, 80]), "60", "120 / 200 = 60%です。"),
        _q("mdf-80-40", "mdf", "MDF", "ポット80に相手が40をベット。単純なMDFは約何%？", _pct([25, 50, 67, 80]), "67", "80 / 120 ≈ 66.7%です。"),
    ],
    "spr": [
        _q("spr-3600-1200", "spr", "SPR", "ストリート開始時のポットが1,200、エフェクティブスタックが3,600。SPRはいくつ？", [("1", "1"), ("3", "3"), ("6", "6"), ("9", "9")], "3", "3,600 / 1,200 = 3です。"),
        _q("spr-2000-1000", "spr", "SPR", "ポット1,000、エフェクティブスタック2,000。SPRは？", [("1", "1"), ("2", "2"), ("5", "5"), ("10", "10")], "2", "2,000 / 1,000 = 2です。"),
        _q("spr-4500-1500", "spr", "SPR", "ポット1,500、エフェクティブスタック4,500。SPRは？", [("1.5", "1.5"), ("3", "3"), ("6", "6"), ("9", "9")], "3", "4,500 / 1,500 = 3です。"),
        _q("spr-5000-2000", "spr", "SPR", "ポット2,000、エフェクティブスタック5,000。SPRは？", [("1", "1"), ("2.5", "2.5"), ("5", "5"), ("10", "10")], "2.5", "5,000 / 2,000 = 2.5です。"),
        _q("spr-2400-800", "spr", "SPR", "ポット800、エフェクティブスタック2,400。SPRは？", [("1", "1"), ("3", "3"), ("6", "6"), ("8", "8")], "3", "2,400 / 800 = 3です。"),
        _q("spr-1800-1200", "spr", "SPR", "ポット1,200、エフェクティブスタック1,800。SPRは？", [("0.5", "0.5"), ("1.5", "1.5"), ("3", "3"), ("6", "6")], "1.5", "1,800 / 1,200 = 1.5です。"),
    ],
    "outs": [
        _q("outs-9", "outs", "確率・アウツ", "ターンで、リバー1枚だけを残し、確実に勝ちにつながるクリーンアウトが9枚あります。既知カード6枚なので未知カードは46枚。ヒット率は約何%？", _pct([10, 20, 40, 80]), "20", "9 / 46 ≈ 19.6%なので約20%です。"),
        _q("outs-8", "outs", "確率・アウツ", "ターンでクリーンアウト8枚、未知カード46枚。リバーで引く確率は約何%？", _pct([9, 17, 35, 83]), "17", "8 / 46 ≈ 17.4%です。"),
        _q("outs-4", "outs", "確率・アウツ", "ターンでクリーンアウト4枚、未知カード46枚。リバーで引く確率は約何%？", _pct([9, 25, 50, 91]), "9", "4 / 46 ≈ 8.7%です。"),
        _q("outs-12", "outs", "確率・アウツ", "ターンでクリーンアウト12枚、未知カード46枚。リバーで引く確率は約何%？", _pct([13, 26, 52, 74]), "26", "12 / 46 ≈ 26.1%です。"),
        _q("outs-15", "outs", "確率・アウツ", "ターンでクリーンアウト15枚、未知カード46枚。リバーで引く確率は約何%？", _pct([16, 33, 65, 84]), "33", "15 / 46 ≈ 32.6%です。"),
        _q("outs-6", "outs", "確率・アウツ", "ターンでクリーンアウト6枚、未知カード46枚。リバーで引く確率は約何%？", _pct([7, 13, 39, 87]), "13", "6 / 46 ≈ 13.0%です。"),
    ],
}


CATEGORY_ORDER = tuple(POOLS.keys())
assert len(CATEGORY_ORDER) == DAILY_QUIZ_SIZE
assert all(len(pool) >= 6 for pool in POOLS.values())


def today_jst() -> str:
    return datetime.now(JST).date().isoformat()


def build_daily_questions(day: str) -> list[dict[str, Any]]:
    parsed = date.fromisoformat(day)
    ordinal = parsed.toordinal()
    questions: list[dict[str, Any]] = []
    prompts: set[str] = set()
    for slot, category in enumerate(CATEGORY_ORDER, 1):
        pool = POOLS[category]
        # Advancing the ordinal guarantees that every category moves to a
        # different variant on the next calendar day (all pools have >1 item).
        index = (ordinal + slot * 3) % len(pool)
        item = copy.deepcopy(pool[index])
        seed = hashlib.sha256(f"{QUIZ_SET_VERSION}:{day}:{item['key']}".encode()).digest()[0]
        rotate = seed % len(item["choices"])
        item["choices"] = item["choices"][rotate:] + item["choices"][:rotate]
        item["slot"] = slot
        item["id"] = f"dq-{day.replace('-', '')}-{slot:02d}-{item['key']}"
        if item["prompt"] in prompts:
            raise RuntimeError("daily quiz contains duplicate prompt")
        prompts.add(item["prompt"])
        questions.append(item)
    return questions


def _public_question(question: dict[str, Any], progress: dict[str, int], day: str) -> dict[str, Any]:
    return {
        "id": question["id"],
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
    app.state.jj_daily_quiz_v2_installed = True
    _ensure_schema(db)

    # Remove v1.18.6's unlimited random quiz endpoints, keeping its historical
    # table intact for auditability. The v2 routes below become authoritative.
    retired = {"/api/quiz/question", "/api/quiz/answer"}
    app.router.routes[:] = [route for route in app.router.routes if getattr(route, "path", None) not in retired]

    @app.get("/api/quiz/question", include_in_schema=False)
    def daily_quiz_question(user=Depends(server.current_user)):
        day = today_jst()
        questions = build_daily_questions(day)
        by_slot = {int(q["slot"]): q for q in questions}
        with db.connect() as con:
            progress = _progress(con, int(user["id"]), day)
            if progress["answered"] >= DAILY_QUIZ_SIZE:
                return {"done": True, "date": day, "reward": DAILY_QUIZ_REWARD, "progress": progress}

            rows = con.execute(
                "SELECT slot,answer FROM daily_quiz_attempts WHERE user_id=? AND quiz_date=? ORDER BY slot",
                (user["id"], day),
            ).fetchall()
            answered_slots = {int(row["slot"]) for row in rows if row["answer"] is not None}
            next_slot = next(slot for slot in range(1, DAILY_QUIZ_SIZE + 1) if slot not in answered_slots)
            q = by_slot[next_slot]
            values = [str(choice["value"]) for choice in q["choices"]]
            con.execute(
                "INSERT INTO daily_quiz_attempts(id,user_id,quiz_date,slot,question_key,correct_answer,choices_json,answer,is_correct,reward_awarded,created_at,answered_at) "
                "VALUES (?,?,?,?,?,?,?,NULL,NULL,0,?,NULL) "
                "ON CONFLICT(user_id,quiz_date,slot) DO NOTHING",
                (q["id"], user["id"], day, next_slot, q["key"], q["correct"], json.dumps(values, separators=(",", ":")), db.utcnow()),
            )
            row = con.execute(
                "SELECT id,question_key,answer FROM daily_quiz_attempts WHERE user_id=? AND quiz_date=? AND slot=?",
                (user["id"], day, next_slot),
            ).fetchone()
            # If a deploy changes the question-set code during the day, never
            # silently overwrite an already-created daily attempt.
            if not row or str(row["id"]) != q["id"] or str(row["question_key"]) != q["key"]:
                raise HTTPException(409, "本日のクイズ構成が更新されました。画面を再読み込みしてください")
        return _public_question(q, progress, day)

    @app.post("/api/quiz/answer", include_in_schema=False)
    def daily_quiz_answer(payload: DailyQuizAnswerIn, user=Depends(server.current_user)):
        day = today_jst()
        questions = {q["id"]: q for q in build_daily_questions(day)}
        q = questions.get(payload.question_id)
        if q is None:
            raise HTTPException(409, "日付が変わったか問題が更新されました。今日のクイズを再読み込みしてください")
        allowed = {str(choice["value"]) for choice in q["choices"]}
        answer = str(payload.answer)
        if answer not in allowed:
            raise HTTPException(400, "選択肢にない回答です")

        now = db.utcnow()
        with db.connect() as con:
            row = con.execute(
                "SELECT id,correct_answer,answer,reward_awarded FROM daily_quiz_attempts WHERE id=? AND user_id=? AND quiz_date=?",
                (payload.question_id, user["id"], day),
            ).fetchone()
            if not row:
                raise HTTPException(404, "この問題はまだ開始されていません")
            if row["answer"] is not None:
                progress = _progress(con, int(user["id"]), day)
                return {
                    "ok": True,
                    "already_answered": True,
                    "correct": str(row["answer"]) == str(row["correct_answer"]),
                    "correct_answer": str(row["correct_answer"]),
                    "correct_label": next(c["label"] for c in q["choices"] if str(c["value"]) == str(row["correct_answer"])),
                    "explanation": q["explanation"],
                    "awarded": 0,
                    "progress": progress,
                }

            correct = answer == str(row["correct_answer"])
            cur = con.execute(
                "UPDATE daily_quiz_attempts SET answer=?,is_correct=?,answered_at=? "
                "WHERE id=? AND user_id=? AND quiz_date=? AND answer IS NULL",
                (answer, 1 if correct else 0, now, payload.question_id, user["id"], day),
            )
            if int(getattr(cur, "rowcount", 0) or 0) != 1:
                progress = _progress(con, int(user["id"]), day)
                return {"ok": True, "already_answered": True, "correct": False, "awarded": 0, "progress": progress}

            # Globally unique ledger id + ON CONFLICT makes a double request
            # unable to create a second reward even under concurrency.
            txid = f"quiz-v2-{int(user['id'])}-{day}-{int(q['slot']):02d}"
            ledger = con.execute(
                "INSERT INTO point_ledger(id,user_id,amount,kind,reason,effective_at,created_by,created_at,reversal_of) "
                "VALUES (?,?,?,?,?,?,?,?,NULL) ON CONFLICT(id) DO NOTHING",
                (txid, user["id"], DAILY_QUIZ_REWARD, "quiz_reward", f"デイリーポーカークイズ {day} #{q['slot']}", now, user["id"], now),
            )
            awarded = DAILY_QUIZ_REWARD if int(getattr(ledger, "rowcount", 0) or 0) == 1 else 0
            con.execute(
                "UPDATE daily_quiz_attempts SET reward_awarded=? WHERE id=? AND user_id=?",
                (awarded, payload.question_id, user["id"]),
            )
            progress = _progress(con, int(user["id"]), day)

        return {
            "ok": True,
            "already_answered": False,
            "correct": correct,
            "correct_answer": q["correct"],
            "correct_label": next(c["label"] for c in q["choices"] if str(c["value"]) == q["correct"]),
            "explanation": q["explanation"],
            "awarded": awarded,
            "progress": progress,
        }

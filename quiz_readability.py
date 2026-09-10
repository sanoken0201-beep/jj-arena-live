from __future__ import annotations

import copy
import re
from typing import Any

# Daily Quiz v1.22 readability policy:
# difficulty should come from the poker decision, not from decoding jargon.
PLAIN_CATEGORY_LABELS = {
    "pot_odds": "コールに必要な勝率",
    "equity": "勝つ見込み",
    "mdf": "ブラフへの守り方",
    "spr": "残りチップとポット",
    "combo": "カードの組み合わせ",
    "vocabulary": "ポーカー用語",
    "icm": "トーナメントの賞金判断",
    "bet_sizing": "ベット額の考え方",
    "range": "相手の手札候補",
    "hand_reasoning": "ハンドの考え方",
}

# Longest/specific phrases first. These replacements are intentionally descriptive
# rather than dictionary-like: the learner should be able to understand the stem
# without already knowing the technical term.
_REPLACEMENTS: list[tuple[str, str]] = [
    ("レーキ・ICM・タイを無視したchipEV", "手数料・賞金差・引き分けを考えず、チップの増減だけで見た長期的な平均損益"),
    ("ナッツブロッカー", "相手の最強クラスの手札を減らすカード"),
    ("逆インプライドオッズ", "役が完成しても、さらに強い役に大きく負ける危険"),
    ("インプライドオッズ", "今後さらに取れるチップまで含めた見込み"),
    ("フォールドエクイティ", "相手を降ろしてその場で勝てる分"),
    ("エクイティ実現率", "勝つ見込みを実際の利益につなげられる割合"),
    ("レンジエクイティ", "相手の手札候補全体に対する平均的な勝つ見込み"),
    ("生エクイティ", "最後までカードを開いた場合の平均的なポットの取り分"),
    ("ショーダウン価値", "チェックして最後まで進んだ場合に勝てる価値"),
    ("ブラフキャッチャー", "強い手には負けるがブラフには勝つ手"),
    ("リスクプレミアム", "敗退や賞金差のため、チップだけで考えるより慎重さが必要になる度合い"),
    ("エフェクティブスタック", "対戦相手との間で実際に賭けられる残りチップ"),
    ("実効スタック", "対戦相手との間で実際に賭けられる残りチップ"),
    ("ショーダウン", "最後までカードを開いて勝敗を決めること"),
    ("相手レンジ", "相手が持ちうる手札の候補"),
    ("到達レンジ", "そのアクションまで残っている手札候補"),
    ("チェックレンジ", "チェックする手札候補"),
    ("コールレンジ", "コールする手札候補"),
    ("続行レンジ", "続ける手札候補"),
    ("レンジ", "持ちうる手札の候補"),
    ("クリーンアウト", "引けばほぼ確実に逆転できる残りカード"),
    ("アウト数", "逆転に使える残りカードの枚数"),
    ("オーバーカード", "ボードより高いランクの手札"),
    ("ヘッズアップ", "1対1"),
    ("マルチウェイ", "3人以上"),
    ("アグレッサー", "前の場面で最後にベットまたはレイズした人"),
    ("スーテッド", "同じスートの"),
    ("オフスート", "異なるスートの"),
    ("セミブラフ", "今は弱いが後で強くなる可能性もあるブラフ"),
    ("キッカー", "同じ役同士の強さを決める補助カード"),
    ("フォールドEV", "降りた場合の長期的な平均損益"),
    ("賞金EV", "平均して得られる賞金"),
    ("chipEV", "チップの増減だけで見た長期的な平均損益"),
    ("+EV", "長期的に利益が出る"),
    ("エクイティ", "勝つ見込み"),
    ("レーキ", "手数料"),
    ("EV", "長期的な平均損益"),
]


def _ascii_token(token: str) -> re.Pattern[str]:
    # Python's Unicode \b does not see a boundary between ASCII letters and
    # Japanese characters because both are classified as word characters.
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])")


_ABBREVIATIONS: list[tuple[re.Pattern[str], str]] = [
    (_ascii_token("MDF"), "相手の純粋なブラフを簡単に利益にさせないための最低継続率（MDF）"),
    (_ascii_token("SPR"), "実際に賭け合える残りチップ ÷ 現在のポット（SPR）"),
    (_ascii_token("ICM"), "残りスタックと賞金配分からチップの賞金価値を考えるモデル（ICM）"),
    (_ascii_token("OOP"), "相手より先に行動する側（OOP）"),
    (_ascii_token("IP"), "相手より後に行動する側（IP）"),
    (_ascii_token("PKO"), "相手を飛ばすと賞金が得られる形式（PKO）"),
    (_ascii_token("FT"), "ファイナルテーブル（FT）"),
]

# In vocabulary questions the named term itself is what is being tested. Replacing
# the target term can reveal the answer, so only normalize surrounding language.
_VOCAB_SAFE_REPLACEMENTS = [
    ("レンジ上限", "持ちうる手札の強さの上限"),
    ("ナッツ級", "その場で最強クラス"),
    ("エクイティ", "勝つ見込み"),
    ("OOP側", "相手より先に行動する側"),
    ("前ストリート", "前の場面"),
    ("次ストリート", "次の場面"),
    ("アグレッサー", "最後にベットまたはレイズした人"),
    ("ホールカード", "自分だけに配られる2枚"),
]

# Some stems are better rewritten as complete situations than mechanically expanded.
_PROMPT_OVERRIDES = {
    "mdf-notodds": "ポットと同じ額をベットされた場合、『相手の純粋なブラフを簡単に利益にさせないための最低継続率』は50%ですが、コール自体に必要な勝率は約33%です。なぜ数字が違うのでしょうか？",
}

# A few vocabulary stems were circular or relied on another specialist term. Give
# them a readable situation while keeping the answer as the poker term.
_VOCAB_PROMPTS = {
    "term-capped": "これまでの行動から、その人が最強クラスの手札をほとんど持っていないと考えられる状態を何と呼びますか？",
    "term-polar": "とても強い手とブラフが中心で、中くらいの強さの手が少ないベットの組み立てを何と呼びますか？",
    "term-linear": "強い手から順番に、ある強さまで連続してレイズに使う組み立てを何と呼びますか？",
    "term-spr": "『実際に賭け合える残りチップ ÷ 現在のポット』を表す略語はどれですか？",
    "term-mdf": "『相手の純粋なブラフを簡単に利益にさせないため、最低限どれくらいコールまたはレイズで続けるか』を表す略語はどれですか？",
    "term-icm": "トーナメントで、各プレイヤーの残りチップと賞金配分から『チップの賞金としての価値』を考えるモデルはどれですか？",
    "term-nut-advantage": "最強クラスの手札を、相手より多く持てる側の有利さを何と呼びますか？",
    "term-range-advantage": "持ちうる手札全体で比べたとき、平均的に相手より強い側の有利さを何と呼びますか？",
    "term-donk": "前の場面で最後にベットまたはレイズした相手に対し、次の場面で先にベットするプレイを何と呼びますか？",
}

_GLOSSARY = {
    "ポットオッズ": "コール額に対して、最低どれくらい勝てばよいかを見る考え方",
    "ブラフ": "弱い手でも、相手を降ろして勝つことを狙うベットやレイズ",
    "バリュー": "強い手で、より弱い手からコールをもらって利益を増やす狙い",
    "3ベット": "プリフロップで、最初のレイズに対してさらにレイズすること",
    "オールイン": "残りチップをすべて賭けること",
    "ドロー": "あと1枚などで強い役が完成する可能性がある手",
    "ブロッカー": "自分のカードによって、相手が特定の手札を持てる組み合わせが減ること",
}


def _plain_text(text: str, *, vocabulary: bool = False) -> str:
    out = str(text or "")
    replacements = _VOCAB_SAFE_REPLACEMENTS if vocabulary else _REPLACEMENTS
    for old, new in replacements:
        out = out.replace(old, new)
    if not vocabulary:
        for pattern, replacement in _ABBREVIATIONS:
            out = pattern.sub(replacement, out)
    # Small editorial fixes that remove machine-translation-like phrasing.
    out = out.replace("最も適切なのは？", "最も適切なのはどれですか？")
    out = out.replace("十分？", "十分ですか？")
    out = out.replace("使える？", "そのまま使えますか？")
    out = out.replace("あり得る？", "あり得ますか？")
    out = out.replace("変わり得る？", "変わることはありますか？")
    return out


def _glossary_for(prompt: str, choices: list[dict[str, Any]], *, vocabulary: bool) -> list[dict[str, str]]:
    if vocabulary:
        # Defining answer options would give away a vocabulary question.
        haystack = prompt
    else:
        haystack = prompt + " " + " ".join(str(c.get("label") or "") for c in choices)
    found = []
    for term, meaning in _GLOSSARY.items():
        if term in haystack:
            found.append({"term": term, "meaning": meaning})
    return found[:4]


def make_readable(question: dict[str, Any]) -> dict[str, Any]:
    q = copy.deepcopy(question)
    category = str(q.get("category") or "")
    vocabulary = category == "vocabulary"
    key = str(q.get("key") or "")
    if key in _PROMPT_OVERRIDES:
        q["prompt"] = _PROMPT_OVERRIDES[key]
    elif vocabulary and key in _VOCAB_PROMPTS:
        q["prompt"] = _VOCAB_PROMPTS[key]
    else:
        q["prompt"] = _plain_text(str(q.get("prompt") or ""), vocabulary=vocabulary)
    q["explanation"] = _plain_text(str(q.get("explanation") or ""), vocabulary=False)
    if not vocabulary:
        q["choices"] = [
            {**choice, "label": _plain_text(str(choice.get("label") or ""), vocabulary=False)}
            for choice in q.get("choices") or []
        ]
    q["category_label"] = PLAIN_CATEGORY_LABELS.get(category, str(q.get("category_label") or "ポーカー"))
    q["glossary"] = _glossary_for(q["prompt"], list(q.get("choices") or []), vocabulary=vocabulary)
    return q


def _strip_explained_abbreviations(text: str) -> str:
    approved = (
        "（MDF）", "（SPR）", "（ICM）", "（OOP）", "（IP）", "（PKO）", "（FT）",
    )
    out = text
    for value in approved:
        out = out.replace(value, "")
    return out


def audit_questions(pools: dict[str, list[dict[str, Any]]]) -> list[str]:
    errors: list[str] = []
    raw_abbreviations = re.compile(r"(?:chipEV|MDF|SPR|ICM|OOP|IP|PKO|FT)")
    hard_phrases = (
        "生エクイティ", "エクイティ実現率", "フォールドエクイティ",
        "インプライドオッズ", "ナッツブロッカー", "ブラフキャッチャー",
        "レーキ", "chipEV",
    )
    seen_prompts: set[str] = set()
    for category, pool in pools.items():
        for original in pool:
            q = make_readable(original)
            key = str(q.get("key") or "?")
            prompt = str(q.get("prompt") or "").strip()
            if not prompt:
                errors.append(f"{key}: empty prompt")
            if prompt in seen_prompts:
                errors.append(f"{key}: duplicate readable prompt")
            seen_prompts.add(prompt)
            if category != "vocabulary":
                if raw_abbreviations.search(_strip_explained_abbreviations(prompt)):
                    errors.append(f"{key}: unexplained abbreviation remains")
                for phrase in hard_phrases:
                    if phrase in prompt:
                        errors.append(f"{key}: unexplained jargon remains: {phrase}")
                labels = [str(c.get("label") or "").strip() for c in q.get("choices") or []]
                if len(labels) != len(set(labels)):
                    errors.append(f"{key}: readable choice labels collapsed into duplicates")
            if len(prompt) > 250:
                errors.append(f"{key}: prompt too long ({len(prompt)})")
            if q.get("category_label") != PLAIN_CATEGORY_LABELS.get(category):
                errors.append(f"{key}: category label not plain")
    return errors

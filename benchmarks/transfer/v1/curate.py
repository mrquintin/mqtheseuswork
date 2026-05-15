"""Generator for the Cross-Domain Transfer Study v1 held-out eval sets.

This script *produces* the frozen JSONL files under ``eval_sets/`` —
``chemistry.jsonl``, ``finance.jsonl``, ``law.jsonl``. The output is
committed; this script exists so the generation is reproducible and
reviewable, not so it runs at study time.

The eval sets are the *target-domain* (D') side of the transfer study.
The *source-domain* (D) side is the frozen QH v1 dataset
(``benchmarks/quintin_hypothesis/v1/dataset.jsonl``) — that is the
method's established track record. These target sets are the neighboring
domains the method has *no* track record in.

Design discipline — deliberately identical to the QH v1 curator
(``benchmarks/quintin_hypothesis/v1/curate.py``):

  * Templates parameterize numeric values and named entities.
  * The coherent and contradicting continuations are *near-identical*
    in lexical surface — they differ only by the flipped assertion, so
    the geometry signal cannot be cheated by a vocabulary mismatch.
  * The orthogonal continuation embeds at least one parameter value so
    orthogonal items do not collapse to a single string.

This matters: the transfer study only means something if the target
sets carry the *same kind* of geometric signal as the source domain.
If the target items were built differently, "the method does not
transfer" would be confounded with "the target set has no signal for
anyone". By mirroring the QH construction, the only thing that varies
across the D -> D' comparison is the *domain vocabulary*.

Once this script has been run for the study, the eval sets are FROZEN.
Their sha256 is pinned in ``pairs.yaml`` and re-running the study
verifies the hash. Do not re-curate a target set to chase a result.

Usage:
    python benchmarks/transfer/v1/curate.py
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Iterable

HERE = Path(__file__).resolve().parent
EVAL_DIR = HERE / "eval_sets"
LICENSE_TAG = "firm-internal-public"
SOURCE_TAG = "firm-authored:transfer-eval-v1"


# ---------------------------------------------------------------------------
# Chemistry templates — the natural-science neighbor of physics.

DISSOLVE_PARAMS = [
    {"mass": m, "salt": salt, "place": place}
    for m in [2, 5, 10, 15, 20]
    for salt in ["sodium chloride", "potassium nitrate", "copper sulfate"]
    for place in ["the Harz", "Cornwall", "the Urals"]
]


def chem_dissolve(p):
    return (
        f"A {p['mass']} gram sample of {p['salt']} is stirred into pure water at room temperature.",
        f"After stirring, the {p['mass']} gram sample of {p['salt']} fully dissolves into the water.",
        f"After stirring, the {p['mass']} gram sample of {p['salt']} fully fails to dissolve into the water.",
        f"The {p['mass']} gram sample of {p['salt']} was acquired from a mineral dealer near {p['place']}.",
    )


PH_PARAMS = [
    {"conc": c, "acid": acid, "city": city}
    for c in ["0.1", "0.5", "1.0", "2.0"]
    for acid in ["hydrochloric acid", "nitric acid", "sulfuric acid"]
    for city in ["Leipzig", "Lyon", "Turin"]
]


def chem_ph(p):
    return (
        f"A {p['conc']} molar aqueous solution of {p['acid']}, a strong acid, is prepared.",
        f"The {p['conc']} molar {p['acid']} solution has a pH well below 7.",
        f"The {p['conc']} molar {p['acid']} solution has a pH well above 7.",
        f"The {p['conc']} molar {p['acid']} solution was bottled at a chemical supplier near {p['city']}.",
    )


GAS_PARAMS = [
    {"p0": p0, "sn": f"VS-{n:04d}"}
    for p0 in [100, 150, 200, 250, 300]
    for n in range(1, 4)
]


def chem_gas(p):
    return (
        f"A fixed mass of ideal gas at {p['p0']} kilopascals is heated in a sealed rigid vessel.",
        f"In the sealed rigid vessel the gas heated from {p['p0']} kilopascals rises in pressure.",
        f"In the sealed rigid vessel the gas heated from {p['p0']} kilopascals falls in pressure.",
        f"The sealed rigid vessel holding gas at {p['p0']} kilopascals is stamped serial {p['sn']}.",
    )


EXOTHERM_PARAMS = [
    {"fuel": fuel, "kj": kj, "lab": lab}
    for fuel in ["methane", "ethanol", "propane", "octane"]
    for kj in [120, 250, 480]
    for lab in ["the Faraday", "the Lavoisier"]
]


def chem_exotherm(p):
    return (
        f"Burning {p['fuel']} in a calorimeter is exothermic, releasing {p['kj']} kilojoules of heat.",
        f"Burning {p['fuel']} raises the calorimeter temperature as {p['kj']} kilojoules are released.",
        f"Burning {p['fuel']} lowers the calorimeter temperature as {p['kj']} kilojoules are released.",
        f"The {p['fuel']} burned to release {p['kj']} kilojoules was weighed out by the {p['lab']} group.",
    )


CATALYST_PARAMS = [
    {"cat": cat, "rxn": rxn, "shelf": shelf}
    for cat in ["platinum", "nickel", "iron oxide"]
    for rxn in ["ammonia synthesis", "ester hydrolysis", "hydrogenation"]
    for shelf in ["B2", "C4", "D1"]
]


def chem_catalyst(p):
    return (
        f"A {p['cat']} catalyst is introduced into the slow {p['rxn']} reaction.",
        f"The {p['cat']} catalyst leaves the {p['rxn']} reaction faster and itself unconsumed.",
        f"The {p['cat']} catalyst leaves the {p['rxn']} reaction slower and itself fully consumed.",
        f"The {p['cat']} catalyst for the {p['rxn']} reaction was stored on shelf {p['shelf']}.",
    )


HALFLIFE_PARAMS = [
    {"iso": iso, "hl": hl, "batch": f"R-{n:03d}"}
    for iso, hl in [
        ("carbon-14", 5730),
        ("cobalt-60", 5),
        ("strontium-90", 29),
        ("iodine-131", 8),
    ]
    for n in range(1, 5)
]


def chem_halflife(p):
    return (
        f"A sample of the isotope {p['iso']} has a half-life of {p['hl']} years.",
        f"After {p['hl']} years roughly half of the original {p['iso']} nuclei remain undecayed.",
        f"After {p['hl']} years roughly none of the original {p['iso']} nuclei remain undecayed.",
        f"The {p['iso']} sample with a {p['hl']} year half-life is recorded under batch {p['batch']}.",
    )


CHEMISTRY_TEMPLATES = [
    (chem_dissolve, DISSOLVE_PARAMS),
    (chem_ph, PH_PARAMS),
    (chem_gas, GAS_PARAMS),
    (chem_exotherm, EXOTHERM_PARAMS),
    (chem_catalyst, CATALYST_PARAMS),
    (chem_halflife, HALFLIFE_PARAMS),
]


# ---------------------------------------------------------------------------
# Finance templates — the quantitative neighbor of economics.

BOND_PARAMS = [
    {"coupon": cp, "bps": bps, "city": city}
    for cp in [2, 3, 4, 5]
    for bps in [50, 100, 200]
    for city in ["Frankfurt", "Singapore", "Toronto"]
]


def fin_bond(p):
    return (
        f"A bond paying a fixed {p['coupon']} percent coupon is outstanding when market rates jump {p['bps']} basis points.",
        f"After the {p['bps']} basis point jump the fixed {p['coupon']} percent bond's price falls.",
        f"After the {p['bps']} basis point jump the fixed {p['coupon']} percent bond's price rises.",
        f"The fixed {p['coupon']} percent bond is registered with a custodian in {p['city']}.",
    )


DIVERSIFY_PARAMS = [
    {"n": n, "asset": asset, "desk": desk}
    for n in [12, 25, 40]
    for asset in ["equity", "credit", "commodity"]
    for desk in ["the Geneva", "the Boston"]
]


def fin_diversify(p):
    return (
        f"An investor spreads capital across {p['n']} weakly correlated {p['asset']} positions.",
        f"Spreading across {p['n']} weakly correlated {p['asset']} positions lowers the portfolio's return variance.",
        f"Spreading across {p['n']} weakly correlated {p['asset']} positions raises the portfolio's return variance.",
        f"The {p['n']} {p['asset']} positions are reconciled each night by {p['desk']} desk.",
    )


COMPOUND_PARAMS = [
    {"rate": r, "years": y}
    for r in [2, 4, 6, 8]
    for y in [5, 10, 20]
]


def fin_compound(p):
    return (
        f"A deposit earns a fixed {p['rate']} percent compounded annually for {p['years']} years.",
        f"Over {p['years']} years the {p['rate']} percent compounded deposit grows above its principal.",
        f"Over {p['years']} years the {p['rate']} percent compounded deposit shrinks below its principal.",
        f"The {p['rate']} percent deposit held for {p['years']} years was opened at a high-street branch.",
    )


RISK_PARAMS = [
    {"premium": pm, "asset": asset, "fund": fund}
    for pm in [10, 25, 50]
    for asset in ["pension", "endowment", "insurance"]
    for fund in ["a sovereign", "a municipal"]
]


def fin_risk(p):
    return (
        f"Two {p['asset']} portfolios share an expected return but one carries {p['premium']} percent more volatility.",
        f"A risk-averse investor prefers the {p['asset']} portfolio without the {p['premium']} percent extra volatility.",
        f"A risk-averse investor prefers the {p['asset']} portfolio with the {p['premium']} percent extra volatility.",
        f"Both {p['asset']} portfolios differing by {p['premium']} percent volatility are audited by {p['fund']} fund.",
    )


INFLATION_PARAMS = [
    {"infl": i, "rate": r, "country": c}
    for i, r in [(6, 2), (8, 3), (10, 4), (5, 1)]
    for c in ["the eurozone", "Japan", "Canada"]
]


def fin_inflation(p):
    return (
        f"Annual inflation runs at {p['infl']} percent while a savings account pays {p['rate']} percent.",
        f"With {p['infl']} percent inflation against {p['rate']} percent interest, the savings lose real purchasing power.",
        f"With {p['infl']} percent inflation against {p['rate']} percent interest, the savings gain real purchasing power.",
        f"The savings account paying {p['rate']} percent against {p['infl']} percent inflation is denominated for {p['country']}.",
    )


LEVERAGE_PARAMS = [
    {"ratio": r, "venue": venue}
    for r in [2, 3, 5, 10]
    for venue in ["the Chicago", "the London", "the Tokyo"]
]


def fin_leverage(p):
    return (
        f"A trader funds a position at {p['ratio']}-to-1 leverage with borrowed money.",
        f"At {p['ratio']}-to-1 leverage the trader's gains and losses are both amplified.",
        f"At {p['ratio']}-to-1 leverage the trader's gains and losses are both dampened.",
        f"The {p['ratio']}-to-1 leveraged position is cleared through {p['venue']} venue.",
    )


FINANCE_TEMPLATES = [
    (fin_bond, BOND_PARAMS),
    (fin_diversify, DIVERSIFY_PARAMS),
    (fin_compound, COMPOUND_PARAMS),
    (fin_risk, RISK_PARAMS),
    (fin_inflation, INFLATION_PARAMS),
    (fin_leverage, LEVERAGE_PARAMS),
]


# ---------------------------------------------------------------------------
# Law templates — the normative-reasoning neighbor of ethics.

CONTRACT_PARAMS = [
    {"a": a, "b": b, "room": room}
    for a, b in [("Alvarez", "Bishop"), ("Chen", "Dubois"), ("Eriksson", "Farah")]
    for room in ["the Oak Room", "Chamber 3", "the annex"]
]


def law_contract(p):
    return (
        f"{p['a']} and {p['b']} exchange a clear offer, an acceptance, and consideration.",
        f"On these facts {p['a']} and {p['b']} have formed a binding contract.",
        f"On these facts {p['a']} and {p['b']} have formed no binding contract.",
        f"{p['a']} and {p['b']} held their meeting in {p['room']}.",
    )


BURDEN_PARAMS = [
    {"offence": o, "city": city}
    for o in ["aggravated theft", "criminal fraud", "arson", "perjury"]
    for city in ["Bristol", "Adelaide", "Halifax"]
]


def law_burden(p):
    return (
        f"A defendant stands trial for {p['offence']} in a criminal court.",
        f"For the {p['offence']} charge the prosecution must prove guilt beyond a reasonable doubt.",
        f"For the {p['offence']} charge the defendant must prove innocence beyond a reasonable doubt.",
        f"The {p['offence']} trial is held at a courthouse in {p['city']}.",
    )


LIMITATION_PARAMS = [
    {"years": y, "claim": claim, "clerk": clerk}
    for y in [2, 4, 7]
    for claim in ["breach-of-contract", "personal-injury", "property-damage"]
    for clerk in ["Okafor", "Lindqvist"]
]


def law_limitation(p):
    return (
        f"A {p['claim']} claim is filed {p['years']} years after the statutory limitation period expired.",
        f"Filed {p['years']} years past the limitation period, the {p['claim']} claim is time-barred.",
        f"Filed {p['years']} years past the limitation period, the {p['claim']} claim is still timely.",
        f"The {p['claim']} claim filed {p['years']} years late was stamped by a clerk named {p['clerk']}.",
    )


PRECEDENT_PARAMS = [
    {"point": pt, "volume": f"vol. {n}"}
    for pt in [
        "the test for foreseeability",
        "the standard for unconscionability",
        "the limits of fair use",
    ]
    for n in [214, 318, 442, 507]
]


def law_precedent(p):
    return (
        f"A higher court settles {p['point']} in a binding precedent.",
        f"Lower courts in the jurisdiction are bound to follow the precedent on {p['point']}.",
        f"Lower courts in the jurisdiction are free to ignore the precedent on {p['point']}.",
        f"The precedent on {p['point']} is reported in bound {p['volume']}.",
    )


MENSREA_PARAMS = [
    {"offence": o, "reader": reader}
    for o in ["embezzlement", "criminal trespass", "tax evasion", "receiving stolen goods"]
    for reader in ["a law student", "a visiting judge", "the clerk"]
]


def law_mensrea(p):
    return (
        f"A criminal statute defines {p['offence']} as requiring a guilty mind.",
        f"Convicting someone of {p['offence']} requires proving the guilty mind, not just the act.",
        f"Convicting someone of {p['offence']} requires proving only the act, not the guilty mind.",
        f"The statute defining {p['offence']} was annotated in pencil by {p['reader']}.",
    )


JEOPARDY_PARAMS = [
    {"defendant": d, "offence": o}
    for d in ["Mr. Halloran", "Ms. Petrova", "the accused"]
    for o in ["burglary", "assault", "wire fraud", "smuggling"]
]


def law_jeopardy(p):
    return (
        f"{p['defendant']} is acquitted of {p['offence']} after a full trial on the merits.",
        f"Having been acquitted of {p['offence']}, {p['defendant']} cannot be retried for the same offence.",
        f"Having been acquitted of {p['offence']}, {p['defendant']} must be retried for the same offence.",
        f"{p['defendant']}'s acquittal on {p['offence']} was read to a nearly empty public gallery.",
    )


LAW_TEMPLATES = [
    (law_contract, CONTRACT_PARAMS),
    (law_burden, BURDEN_PARAMS),
    (law_limitation, LIMITATION_PARAMS),
    (law_precedent, PRECEDENT_PARAMS),
    (law_mensrea, MENSREA_PARAMS),
    (law_jeopardy, JEOPARDY_PARAMS),
]


# ---------------------------------------------------------------------------
# Expansion + dedup — identical machinery to the QH v1 curator.

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _ngram_set(text: str, n: int = 5) -> set[tuple[str, ...]]:
    tokens = _TOKEN_RE.findall(text.lower())
    if len(tokens) < n:
        return {tuple(tokens)} if tokens else set()
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))


def _emit_items(domain: str, templates) -> Iterable[dict]:
    for fn, params_list in templates:
        for params_dict in params_list:
            premise, coh, contra, ortho = fn(params_dict)
            for label, continuation in (
                ("coherent", coh),
                ("contradicting", contra),
                ("orthogonal", ortho),
            ):
                yield {
                    "premise": premise,
                    "candidate_continuation": continuation,
                    "label": label,
                    "domain": domain,
                    "source": SOURCE_TAG,
                    "license": LICENSE_TAG,
                }


def _hash_embed(text: str, dim: int = 192) -> list[float]:
    import math

    v = [0.0] * dim
    for tok in _TOKEN_RE.findall(text.lower()):
        h = int.from_bytes(
            hashlib.blake2b(f"qh-v1:{tok}".encode("utf-8"), digest_size=8).digest(),
            "big",
        )
        idx = h % dim
        sign = 1.0 if (h >> 32) & 1 else -1.0
        v[idx] += sign
    n = math.sqrt(sum(x * x for x in v))
    if n > 0:
        v = [x / n for x in v]
    return v


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def deduplicate(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """Drop n-gram and embedding near-duplicates per the QH schema doc."""
    kept: list[dict] = []
    dropped: list[dict] = []
    fingerprints: list[tuple[set, list[float]]] = []
    for item in items:
        text = f"{item['premise']} || {item['candidate_continuation']}"
        ngr = _ngram_set(text)
        emb = _hash_embed(text)
        is_dup = False
        for prev_ngr, prev_emb in fingerprints:
            if _jaccard(ngr, prev_ngr) >= 0.85:
                is_dup = True
                break
            if _cosine(emb, prev_emb) >= 0.985:
                is_dup = True
                break
        if is_dup:
            dropped.append(item)
        else:
            kept.append(item)
            fingerprints.append((ngr, emb))
    return kept, dropped


def assign_ids(items: list[dict], domain: str) -> list[dict]:
    out = []
    for n, item in enumerate(items):
        item = dict(item)
        item["id"] = f"transfer-v1-{domain}-{n:05d}"
        out.append(item)
    return out


def _write_domain(domain: str, templates) -> int:
    raw = list(_emit_items(domain, templates))
    kept, dropped = deduplicate(raw)
    kept = assign_ids(kept, domain)
    out_path = EVAL_DIR / f"{domain}.jsonl"
    with out_path.open("w", encoding="utf-8") as fh:
        for item in kept:
            ordered = {
                "id": item["id"],
                "premise": item["premise"],
                "candidate_continuation": item["candidate_continuation"],
                "label": item["label"],
                "domain": item["domain"],
                "source": item["source"],
                "license": item["license"],
            }
            fh.write(json.dumps(ordered, ensure_ascii=False) + "\n")
    by_label: dict[str, int] = {}
    for item in kept:
        by_label[item["label"]] = by_label.get(item["label"], 0) + 1
    print(
        f"{domain:10s}: emitted {len(raw)} raw, dropped {len(dropped)} dup, "
        f"kept {len(kept)} -> {out_path.name}  by_label={by_label}"
    )
    return len(kept)


def main() -> None:
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    total += _write_domain("chemistry", CHEMISTRY_TEMPLATES)
    total += _write_domain("finance", FINANCE_TEMPLATES)
    total += _write_domain("law", LAW_TEMPLATES)
    print(f"total: {total} held-out items across 3 target domains")


if __name__ == "__main__":
    main()

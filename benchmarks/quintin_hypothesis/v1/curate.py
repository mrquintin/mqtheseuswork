"""Generator for the QH Benchmark v1 seed dataset.

This script *produces* ``dataset.jsonl`` and ``dataset_card.md`` in
this directory. The output is committed; this script exists so the
generation is reproducible and reviewable, not so it runs at
benchmark time.

Items are firm-authored under ``firm-internal-public`` license:
free reuse, no warranty. Templates parameterize numeric values and
named entities to produce variation while keeping the gold label
unambiguous. Each label-completion threads the parameter values back
into the continuation so coherent / contradicting / orthogonal items
share lexical surface — the geometry signal cannot be cheated by a
trivial vocabulary mismatch.

Re-running the script must be deterministic: a fixed seed and a
fixed iteration order over templates and parameters.

Usage:
    python benchmarks/quintin_hypothesis/v1/curate.py
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Iterable

HERE = Path(__file__).resolve().parent
LICENSE_TAG = "firm-internal-public"
SOURCE_TAG = "firm-authored:templated-v1"

# ---------------------------------------------------------------------------
# Template definitions.
#
# Each template maps a parameter dict to (premise, coherent,
# contradicting, orthogonal). Orthogonal continuations are designed to
# embed at least one parameter value so that orthogonal items do not
# all collapse to identical strings.

PHYSICS_PARAMS: list[dict] = [
    {"m": m, "t": t, "place": place}
    for m in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 20]
    for t in [1, 2, 3]
    for place in ["the Pyrenees", "Cumbria", "the Vosges", "Snowdonia"]
]


def physics_freefall(p):
    v = round(9.8 * p["t"], 2)
    return (
        f"A stone of mass {p['m']} kg is dropped from rest in a vacuum near Earth's surface.",
        f"After {p['t']} seconds the stone is moving at approximately {v} m/s downward.",
        f"After {p['t']} seconds the {p['m']} kg stone is still at rest.",
        f"The {p['m']} kg stone was originally quarried near {p['place']}.",
    )


WATER_PARAMS = [
    {"hot": hot, "drink": drink}
    for hot in [105, 110, 115, 120, 125, 130, 140, 150, 160, 175, 195, 215]
    for drink in ["green tea", "black tea", "oolong", "rooibos", "yerba mate"]
]


def physics_water(p):
    return (
        "Pure water at standard atmospheric pressure boils at 100 degrees Celsius.",
        f"Heating pure water above 100°C at sea level — say to {p['hot']}°C — converts it to steam.",
        f"At sea level, pure water remains stably liquid at {p['hot']}°C.",
        f"Boiled water at roughly {p['hot']}°C is sometimes used to brew {p['drink']}.",
    )


FORCE_PARAMS = [
    {"m": m, "a": a, "color": color}
    for m in [1, 2, 3, 4, 5, 6, 8, 10, 12]
    for a in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0]
    for color in ["matte black", "navy", "ochre"]
]


def physics_force(p):
    f = round(p["m"] * p["a"], 2)
    return (
        f"An object of mass {p['m']} kg accelerates at {p['a']} m/s^2 under a single applied force.",
        f"The applied force on the {p['m']} kg object is approximately {f} newtons.",
        f"The applied force on the {p['m']} kg object is exactly zero newtons.",
        f"The {p['m']} kg object is painted {p['color']}.",
    )


LIGHT_PARAMS = [
    {"t": t, "coast": coast}
    for t in [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15]
    for coast in ["the Cornish coast", "the Brittany coast", "the Galician coast"]
]


def physics_light(p):
    d = int(round(299792.458 * p["t"]))
    return (
        "Light in a vacuum travels at approximately 299,792,458 metres per second.",
        f"A radio signal in vacuum covers about {d:,} kilometres in {p['t']} seconds.",
        f"A radio signal in vacuum requires {p['t']} hours to cover one kilometre.",
        f"Lighthouses near {p['coast']} use rotating optics to project beams.",
    )


SPRING_PARAMS = [
    {"k": k, "x": x, "finish": finish}
    for k in [50, 100, 150, 200, 250, 300, 400, 500, 800]
    for x in [0.05, 0.10, 0.15, 0.20, 0.30, 0.40]
    for finish in ["zinc", "nickel", "cadmium-yellow"]
]


def physics_spring(p):
    f = round(p["k"] * p["x"], 2)
    return (
        f"A linear spring with stiffness {p['k']} N/m is stretched {p['x']} metres from rest.",
        f"The restoring force on the {p['k']} N/m spring is approximately {f} newtons.",
        f"At a stretch of {p['x']} metres the {p['k']} N/m spring exerts no restoring force.",
        f"Coil springs of this {p['k']} N/m class are typically plated with {p['finish']}.",
    )


PENDULUM_PARAMS = [
    {"L": L, "alloy": alloy}
    for L in [0.10, 0.25, 0.40, 0.50, 0.75, 1.00, 1.25, 1.50, 2.00, 2.50, 3.00, 4.00]
    for alloy in ["brass", "phosphor bronze", "leaded steel"]
]


def physics_pendulum(p):
    T = round(2 * 3.14159265 * (p["L"] / 9.8) ** 0.5, 2)
    return (
        f"A simple pendulum of length {p['L']} metres swings under standard gravity.",
        f"Its small-amplitude period is approximately {T} seconds.",
        f"Its small-amplitude period at length {p['L']} m is exactly one second regardless of length.",
        f"The {p['L']} m pendulum's bob is cast in {p['alloy']}.",
    )


SOUND_PARAMS = [
    {"tC": tC, "t": t, "city": city}
    for tC in [-10, 0, 5, 10, 15, 20, 25, 30, 35]
    for t in [1, 2, 3, 5]
    for city in ["Vienna", "Leipzig", "Lyon", "Porto"]
]


def physics_sound(p):
    c = round(331.3 + 0.6 * p["tC"], 1)
    d = int(round(c * p["t"], 0))
    return (
        f"Sound in dry air at {p['tC']}°C travels at approximately {c} m/s.",
        f"A clap heard {p['t']} seconds after the flash places the source roughly {d} m away.",
        f"At {p['tC']}°C the clap reaches the observer instantaneously regardless of distance.",
        f"Concert halls in {p['city']} are tuned for diffuse reverberation.",
    )


OHM_PARAMS = [
    {"V": V, "R": R, "bands": bands}
    for V in [1.5, 3.0, 5.0, 6.0, 9.0, 12.0, 24.0, 48.0]
    for R in [10, 22, 47, 100, 220, 470, 1000, 2200, 4700]
    for bands in ["four", "five"]
]


def physics_ohm(p):
    I = round(p["V"] / p["R"], 4)
    return (
        f"A direct-current source applies {p['V']} volts across a {p['R']} ohm resistor.",
        f"By Ohm's law the current through the {p['R']} ohm resistor is approximately {I} amperes.",
        f"By Ohm's law no current flows through the {p['R']} ohm resistor under {p['V']} V.",
        f"The {p['R']} ohm resistor body is colour-coded with {p['bands']} bands.",
    )


GAS_PARAMS = [
    {"sn": f"AX-{n:04d}", "p0": p0, "factor": factor}
    for n in range(1, 16)
    for p0 in [100, 150, 200, 250, 300]
    for factor in [2, 3, 4]
]


def physics_gas(p):
    new_p = p["p0"] * p["factor"]
    return (
        f"An ideal gas at constant temperature is compressed to one-{p['factor']} of its initial volume from {p['p0']} kPa.",
        f"By Boyle's law the gas pressure rises to approximately {new_p} kPa.",
        f"By Boyle's law the gas pressure remains at {p['p0']} kPa.",
        f"The gas cylinder bears serial number {p['sn']}.",
    )


COULOMB_PARAMS = [
    {"factor": factor, "law_year": ly}
    for factor in [2, 3, 4, 5, 10]
    for ly in [1785, 1788, 1790]
]


def physics_coulomb(p):
    return (
        f"Two like point charges interact under Coulomb's inverse-square law.",
        f"Multiplying the distance between two like charges by {p['factor']} reduces the force by a factor of {p['factor']**2}.",
        f"Multiplying the distance between two like charges by {p['factor']} leaves the force unchanged.",
        f"Coulomb's law was first published around {p['law_year']}.",
    )


PHOTON_PARAMS = [
    {"f1": f1, "f2": f2, "field": field}
    for f1, f2 in [
        (1.0e15, 1.0e14),
        (7.5e14, 4.3e14),
        (1.2e15, 5.5e14),
        (2.0e15, 6.0e14),
        (3.0e15, 5.0e14),
    ]
    for field in [
        "microbiology",
        "forensic",
        "mineralogy",
        "horticultural",
        "semiconductor inspection",
    ]
]


def physics_photon(p):
    return (
        f"A photon's energy is proportional to its frequency.",
        f"A photon at {p['f1']:.1e} Hz carries more energy than one at {p['f2']:.1e} Hz.",
        f"A photon at {p['f1']:.1e} Hz carries less energy than one at {p['f2']:.1e} Hz.",
        f"Lamps emitting near {p['f1']:.1e} Hz are common in {p['field']} laboratories.",
    )


PHYSICS_TEMPLATES = [
    (physics_freefall, PHYSICS_PARAMS),
    (physics_water, WATER_PARAMS),
    (physics_force, FORCE_PARAMS),
    (physics_light, LIGHT_PARAMS),
    (physics_spring, SPRING_PARAMS),
    (physics_pendulum, PENDULUM_PARAMS),
    (physics_sound, SOUND_PARAMS),
    (physics_ohm, OHM_PARAMS),
    (physics_gas, GAS_PARAMS),
    (physics_coulomb, COULOMB_PARAMS),
    (physics_photon, PHOTON_PARAMS),
]


# Economics ----------------------------------------------------------------

DEMAND_PARAMS = [
    {"good": good, "delta": delta, "tb": tb}
    for good in ["bread", "petrol", "tablets", "domestic flights", "sneakers", "smartphones", "winter coats", "olive oil"]
    for delta in [5, 10, 15, 20, 30]
    for tb in ["introductory textbooks", "policy briefs"]
]


def econ_demand(p):
    return (
        f"Holding everything else constant, the demand curve for {p['good']} slopes downward.",
        f"If the price of {p['good']} rises by {p['delta']} percent, the quantity demanded tends to fall.",
        f"If the price of {p['good']} rises by {p['delta']} percent, the quantity demanded tends to rise as well.",
        f"Demand curves for {p['good']} are typically drawn alongside supply curves in {p['tb']}.",
    )


RATE_PARAMS = [
    {"bps": bps, "city": city}
    for bps in [25, 50, 75, 100, 150, 200, 300]
    for city in ["Frankfurt", "London", "Tokyo", "Ottawa", "Stockholm", "Sydney"]
]


def econ_rates(p):
    return (
        f"A central bank raises its policy rate by {p['bps']} basis points to combat above-target inflation.",
        f"Mortgage rates and other lending rates tend to rise after the {p['bps']} bp hike.",
        f"Mortgage rates and other lending rates tend to fall after the {p['bps']} bp hike.",
        f"Such announcements are often delivered at {p['city']} press conferences.",
    )


COMP_PARAMS = [
    {"good": good, "unit": unit}
    for good in ["wheat", "cement", "smelted aluminium", "polyester yarn"]
    for unit in ["bushels", "tonnes", "kilowatt-hours", "litres", "metres"]
]


def econ_competitive(p):
    return (
        f"A perfectly competitive {p['good']} producer chooses output where price equals marginal cost.",
        f"If the price of {p['good']} exceeds marginal cost at the current output, the producer can profitably raise output.",
        f"If the price of {p['good']} exceeds marginal cost at the current output, the producer should cut output.",
        f"In such diagrams, output is typically measured in {p['unit']}.",
    )


TARIFF_PARAMS = [
    {"rate": rate, "good": good, "doc": doc}
    for rate in [5, 10, 15, 20, 25, 35]
    for good in ["steel", "rice", "automobiles", "solar panels", "soybeans", "textiles"]
    for doc in ["national tariff schedules", "WTO bound rate filings"]
]


def econ_tariff(p):
    return (
        f"An import tariff of {p['rate']} percent on {p['good']} raises its domestic price.",
        f"Domestic {p['good']} producers tend to gain at the expense of consumers.",
        f"Domestic {p['good']} producers are made strictly worse off by the {p['rate']} percent tariff.",
        f"Tariff rates of this kind are codified in {p['doc']}.",
    )


SURPLUS_PARAMS = [
    {"surplus": s, "currency": c}
    for s in ["a 1 percent of GDP", "a 2 percent of GDP", "a modest", "a sustained 3 percent of GDP"]
    for c in ["euros", "yen", "pounds sterling", "Swiss francs", "Australian dollars", "won"]
]


def econ_surplus(p):
    return (
        f"A government runs {p['surplus']} primary surplus when its non-interest spending falls short of tax revenue.",
        f"All else equal, {p['surplus']} primary surplus reduces the debt-to-GDP ratio over time.",
        f"All else equal, {p['surplus']} primary surplus increases the debt-to-GDP ratio over time.",
        f"Fiscal accounts of this kind are reported in {p['currency']}.",
    )


CEILING_PARAMS = [
    {"good": good, "gap": gap}
    for good in ["bread", "petrol", "rental housing", "milk", "sugar", "subsidised electricity"]
    for gap in [10, 20, 30, 40, 50]
]


def econ_ceiling(p):
    return (
        f"A binding price ceiling on {p['good']} sits about {p['gap']} percent below the equilibrium price.",
        f"Quantity demanded for {p['good']} exceeds quantity supplied, creating a shortage.",
        f"Quantity supplied of {p['good']} exceeds quantity demanded, creating a surplus.",
        f"Such ceilings have historically targeted {p['good']} markets in wartime.",
    )


PIGOU_PARAMS = [
    {"externality": e, "uni": uni}
    for e in ["air pollution", "noise pollution", "groundwater pollution", "carbon emissions", "river siltation"]
    for uni in ["Cambridge", "the LSE", "Oxford"]
]


def econ_pigou(p):
    return (
        f"{p['externality'].capitalize()} is a negative externality whose private cost lies below its social cost.",
        f"A Pigouvian tax aligned with the marginal external damage from {p['externality']} can move output toward the social optimum.",
        f"A Pigouvian tax aligned with the marginal external damage from {p['externality']} strictly worsens efficiency.",
        f"Pigou developed the framework while at {p['uni']}.",
    )


INELASTIC_PARAMS = [
    {"asset": asset, "shift": shift}
    for asset in ["antique paintings", "historic land parcels", "vintage stamps", "rare manuscripts", "limited Bordeaux vintages"]
    for shift in [10, 20, 30, 40]
]


def econ_inelastic(p):
    return (
        f"The supply of {p['asset']} is, on the relevant horizon, perfectly inelastic.",
        f"A {p['shift']} percent rise in demand raises the price of {p['asset']} but leaves quantity supplied unchanged.",
        f"A {p['shift']} percent rise in demand raises the quantity of {p['asset']} supplied while leaving the price unchanged.",
        f"Such inelastic supply is sometimes used to model markets for {p['asset']}.",
    )


COMP_ADV_PARAMS = [
    {"a": a, "b": b}
    for a, b in [
        ("England", "Portugal"),
        ("Spain", "Morocco"),
        ("Sweden", "Denmark"),
        ("Brazil", "Argentina"),
        ("Vietnam", "Thailand"),
        ("Canada", "Mexico"),
    ]
]


def econ_comp_adv(p):
    return (
        f"{p['a']} and {p['b']} differ in their opportunity costs of producing wheat and cloth.",
        f"Each of {p['a']} and {p['b']} can gain from specializing in the good with lower opportunity cost and trading.",
        f"Both {p['a']} and {p['b']} are made strictly worse off by specializing along comparative advantage and trading.",
        f"Ricardo set out this argument in his treatise published in 1817.",
    )


MONO_PARAMS = [
    {"sector": sector, "juris": juris}
    for sector in [
        "freight rail",
        "submarine cable transit",
        "airport ground handling",
        "high-voltage transmission",
        "major-port pilotage",
    ]
    for juris in ["the EU", "the United Kingdom", "Canada", "Australia", "Japan", "the United States"]
]


def econ_monopoly(p):
    return (
        f"A monopolist in {p['sector']} sets price above marginal cost.",
        f"Output in {p['sector']} is below the competitive level, generating deadweight loss.",
        f"Output in {p['sector']} equals the competitive level, eliminating deadweight loss.",
        f"Antitrust authorities in {p['juris']} review such arrangements under merger guidelines.",
    )


FULL_EMPL_PARAMS = [
    {"agency": a, "year": y}
    for a in [
        "the national statistics office",
        "the central bank's research desk",
        "the independent fiscal council",
        "the budget office",
    ]
    for y in [2018, 2019, 2020, 2021, 2022]
]


def econ_full_empl(p):
    return (
        f"In {p['year']} an economy is at full employment with cyclical unemployment near zero.",
        f"Further fiscal stimulus from {p['year']} primarily raises the price level rather than real output.",
        f"Further fiscal stimulus from {p['year']} primarily raises real output without affecting the price level.",
        f"Estimates of the natural rate are published quarterly by {p['agency']}.",
    )


MUTILITY_PARAMS = [
    {"good": good, "school": school}
    for good in ["bread", "ice cream", "espresso shots", "subway rides", "data plans"]
    for school in ["Austrian", "Lausanne", "Cambridge", "marginalist"]
]


def econ_mutility(p):
    return (
        f"A consumer's marginal utility from each successive serving of {p['good']} tends to decline.",
        f"Holding income fixed, the consumer is willing to pay less for additional {p['good']}.",
        f"Holding income fixed, the consumer is willing to pay strictly more for additional {p['good']}.",
        f"Cardinal utility was central to debates among {p['school']} economists.",
    )


ECONOMICS_TEMPLATES = [
    (econ_demand, DEMAND_PARAMS),
    (econ_rates, RATE_PARAMS),
    (econ_competitive, COMP_PARAMS),
    (econ_tariff, TARIFF_PARAMS),
    (econ_surplus, SURPLUS_PARAMS),
    (econ_ceiling, CEILING_PARAMS),
    (econ_pigou, PIGOU_PARAMS),
    (econ_inelastic, INELASTIC_PARAMS),
    (econ_comp_adv, COMP_ADV_PARAMS),
    (econ_monopoly, MONO_PARAMS),
    (econ_full_empl, FULL_EMPL_PARAMS),
    (econ_mutility, MUTILITY_PARAMS),
]


# Ethics -------------------------------------------------------------------

DEONT_PARAMS = [
    {"agent": agent, "context": ctx}
    for agent in ["Anna", "Brendan", "Constance", "Dimitri", "Esme", "Felix", "Greta", "Henrik"]
    for ctx in [
        "shielding a refugee from a pursuer",
        "concealing a friend from an angry mob",
        "hiding a witness from a hitman",
    ]
]


def ethics_deont(p):
    return (
        f"Under a strict deontological view, {p['agent']} must not lie even to prevent foreseeable harm.",
        f"{p['agent']}, refusing to lie when {p['context']}, is acting consistently with strict deontology.",
        f"{p['agent']}, refusing to lie when {p['context']}, is violating strict deontology.",
        f"Kant lectured on related themes at the University of Königsberg, where {p['agent']}'s case would be a textbook example.",
    )


CONSEQ_PARAMS = [
    {"policy": policy}
    for policy in [
        "a universal childhood vaccination scheme",
        "a citywide cycle-network expansion",
        "a school-feeding programme",
        "a smoke-free workplace law",
        "a rural broadband subsidy",
        "a public-library expansion",
        "a flood-defence upgrade",
    ]
]


def ethics_conseq(p):
    return (
        f"A consequentialist evaluates {p['policy']} by the value of its outcomes.",
        f"If {p['policy']} produces strictly better outcomes for everyone, the consequentialist endorses it.",
        f"If {p['policy']} produces strictly better outcomes for everyone, the consequentialist rejects it.",
        f"Mill articulated his version of this view while serving in the East India Company; {p['policy']} is a modern echo of his examples.",
    )


VIRTUE_PARAMS = [
    {"trait": trait, "act": act}
    for trait in ["generous", "courageous", "honest", "patient", "just", "temperate"]
    for act in [
        "donating to a struggling neighbour",
        "speaking up at a tense meeting",
        "returning a found wallet",
        "tutoring a colleague's child",
        "covering a stranger's fare",
    ]
]


def ethics_virtue(p):
    return (
        f"Virtue ethics treats character traits, such as being {p['trait']}, as the primary unit of moral evaluation.",
        f"An act of {p['act']} flowing from a {p['trait']} disposition is morally praiseworthy on this view.",
        f"An act of {p['act']} flowing from a {p['trait']} disposition is morally blameworthy on this view.",
        f"Aristotle developed his account of {p['trait']} character in dialogue with earlier Greek traditions.",
    )


RIGHTS_PARAMS = [
    {"agent": a, "n": n}
    for a in ["a surgeon", "a triage officer", "a transplant coordinator", "an emergency physician"]
    for n in [3, 5, 7, 10]
]


def ethics_rights(p):
    return (
        f"A rights-based view holds that some interests are protected from being traded against others.",
        f"It is impermissible for {p['agent']} to kill an innocent person to harvest organs for {p['n']} strangers.",
        f"It is required for {p['agent']} to kill an innocent person to harvest organs for {p['n']} strangers.",
        f"Such doctrines are sometimes codified in national bills of rights, which constrain {p['agent']}'s discretion.",
    )


PROMISE_PARAMS = [
    {"agent": a, "favour": f}
    for a in ["Mira", "Owen", "Priya", "Quentin", "Rosa", "Said", "Tomas"]
    for f in [
        "showing up to a friend's recital",
        "watering a neighbour's plants",
        "covering a colleague's shift",
        "returning a borrowed book",
        "delivering a sealed letter",
    ]
]


def ethics_promise(p):
    return (
        f"Promising creates a moral reason for {p['agent']} to keep their word, absent overriding considerations.",
        f"{p['agent']}'s breaking a promise about {p['favour']} for personal convenience requires a justification beyond preference.",
        f"{p['agent']}'s breaking a promise about {p['favour']} for personal convenience requires no justification at all.",
        f"Discussions of promising relevant to {p['agent']}'s case appear in legal codes dating to Roman antiquity.",
    )


UTIL_PARAMS = [
    {"action_a": a, "action_b": b}
    for a, b in [
        ("a small lottery payout to one beneficiary", "a tiny payout to many beneficiaries"),
        ("a large grant to one charity", "small grants to several charities"),
        ("a single big medical intervention", "many small medical interventions"),
        ("a one-off subsidy to one farmer", "a fragmented subsidy to many farmers"),
    ]
]


def ethics_util(p):
    return (
        f"An act utilitarian computes the right action by summing welfare effects across affected parties.",
        f"If {p['action_a']} and {p['action_b']} produce identical aggregate welfare, the act utilitarian treats them as morally equivalent.",
        f"If {p['action_a']} and {p['action_b']} produce identical aggregate welfare, the act utilitarian treats them as morally distinguishable on aggregate grounds alone.",
        f"Bentham's manuscripts on this calculus, including discussions analogous to {p['action_a']}, are archived at University College London.",
    )


DOUBLE_PARAMS = [
    {"action": action, "topic": topic}
    for action in [
        "administering high-dose pain relief at end of life",
        "destroying a munitions factory adjoining a hospital",
        "issuing a defensive strike on a hostile force",
        "refusing a risky transplant for an incurable patient",
    ]
    for topic in ["just war", "end-of-life", "self-defence", "research"]
]


def ethics_double(p):
    return (
        f"The doctrine of double effect distinguishes intended from foreseen consequences for actions like {p['action']}.",
        f"Causing harm as a foreseen but unintended side effect of {p['action']} can be permissible on this doctrine.",
        f"Causing harm as a foreseen but unintended side effect of {p['action']} is strictly impermissible on this doctrine.",
        f"The doctrine has been applied in {p['topic']} ethics debates connected to {p['action']}.",
    )


REL_PARAMS = [
    {"practice": practice, "decade": decade}
    for practice in [
        "a coming-of-age ritual",
        "an arranged-marriage custom",
        "a pre-modern dietary taboo",
        "a traditional mourning rite",
    ]
    for decade in ["the 1930s", "the 1950s", "the 1970s", "the 1990s", "the 2010s"]
]


def ethics_rel(p):
    return (
        f"Moral relativism holds that moral truth varies across cultures, including with respect to {p['practice']}.",
        f"On this view, an outsider's blanket condemnation of {p['practice']} rests on shaky ground.",
        f"On this view, an outsider's blanket condemnation of {p['practice']} is straightforwardly correct.",
        f"Cross-cultural ethnography in {p['decade']} popularised debates about {p['practice']}.",
    )


CONTRACT_PARAMS = [
    {"princ": princ, "interlocutor": i}
    for princ in [
        "imposing decade-long isolation on one prisoner for tiny benefits to many",
        "denying a single patient lifesaving care to fund minor improvements for many",
        "subjecting one worker to severe risk for marginal gains for many",
    ]
    for i in ["Rawlsian liberalism", "utilitarian ethics", "Kantian ethics"]
]


def ethics_contract(p):
    return (
        f"A contractualist holds that principles are justified if no one could reasonably reject them.",
        f"A principle of {p['princ']} would face a reasonable rejection on contractualist grounds.",
        f"A principle of {p['princ']} cannot be reasonably rejected on contractualist grounds.",
        f"Scanlon develops this view in dialogue with {p['interlocutor']}.",
    )


NEGUTIL_PARAMS = [
    {"suffer": s, "happy": h}
    for s in [
        "preventing severe chronic pain in one patient",
        "averting acute famine for one community",
        "defusing a torture risk for one detainee",
    ]
    for h in [
        "creating a comparable joy for many tourists",
        "creating a comparable thrill for many gamers",
        "creating a comparable delight for many concertgoers",
    ]
]


def ethics_negutil(p):
    return (
        f"Strict negative utilitarianism prioritises the reduction of suffering over the promotion of happiness.",
        f"Faced with a choice between {p['suffer']} and {p['happy']} of equal magnitude, this view prefers the former.",
        f"Faced with a choice between {p['suffer']} and {p['happy']} of equal magnitude, this view prefers the latter.",
        f"The view has been criticised in essays on {p['suffer']} published by Oxford University Press.",
    )


AGENT_PARAMS = [
    {"parent": pn, "child": cn, "year": y}
    for pn in ["Naomi", "Pavel", "Quentin", "Reyhan", "Sven"]
    for cn in ["Ari", "Benji", "Cleo", "Dario"]
    for y in [1984, 1986, 1988]
]


def ethics_agent(p):
    return (
        f"An agent-relative reason applies specifically to the agent who has it.",
        f"{p['parent']}'s special obligations to their child {p['child']} are paradigmatic examples of agent-relative reasons.",
        f"{p['parent']}'s special obligations to their child {p['child']} are paradigmatic examples of agent-neutral reasons.",
        f"Parfit explored these distinctions in writings published in {p['year']}.",
    )


LUCK_PARAMS = [
    {"a": a, "b": b}
    for a, b in [
        ("Ines", "Jonas"),
        ("Karim", "Lara"),
        ("Mei", "Niko"),
        ("Olive", "Park"),
    ]
]


def ethics_luck(p):
    return (
        f"Moral luck refers to cases where factors outside an agent's control affect moral assessment.",
        f"Two drivers, {p['a']} and {p['b']}, identical in attentiveness but differing in whether a child runs into the road, face different moral verdicts on this view.",
        f"Two drivers, {p['a']} and {p['b']}, identical in attentiveness but differing in whether a child runs into the road, face identical moral verdicts on every account.",
        f"Williams and Nagel framed this debate in essays from the late 1970s, often illustrated by drivers like {p['a']} and {p['b']}.",
    )


ETHICS_TEMPLATES = [
    (ethics_deont, DEONT_PARAMS),
    (ethics_conseq, CONSEQ_PARAMS),
    (ethics_virtue, VIRTUE_PARAMS),
    (ethics_rights, RIGHTS_PARAMS),
    (ethics_promise, PROMISE_PARAMS),
    (ethics_util, UTIL_PARAMS),
    (ethics_double, DOUBLE_PARAMS),
    (ethics_rel, REL_PARAMS),
    (ethics_contract, CONTRACT_PARAMS),
    (ethics_negutil, NEGUTIL_PARAMS),
    (ethics_agent, AGENT_PARAMS),
    (ethics_luck, LUCK_PARAMS),
]


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
    """Drop n-gram and embedding near-duplicates per the schema doc."""
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


def assign_ids(items: list[dict]) -> list[dict]:
    by_domain: dict[str, int] = {}
    out = []
    for item in items:
        d = item["domain"]
        n = by_domain.get(d, 0)
        item = dict(item)
        item["id"] = f"qh-v1-{d}-{n:06d}"
        by_domain[d] = n + 1
        out.append(item)
    return out


def main() -> None:
    raw: list[dict] = []
    raw.extend(_emit_items("physics", PHYSICS_TEMPLATES))
    raw.extend(_emit_items("economics", ECONOMICS_TEMPLATES))
    raw.extend(_emit_items("ethics", ETHICS_TEMPLATES))

    kept, dropped = deduplicate(raw)
    kept = assign_ids(kept)

    out_path = HERE / "dataset.jsonl"
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

    by_domain: dict[str, int] = {}
    by_label: dict[str, int] = {}
    for item in kept:
        by_domain[item["domain"]] = by_domain.get(item["domain"], 0) + 1
        by_label[item["label"]] = by_label.get(item["label"], 0) + 1

    print(f"emitted {len(raw)} raw items")
    print(f"dropped {len(dropped)} duplicates")
    print(f"kept    {len(kept)} items")
    print(f"by domain: {by_domain}")
    print(f"by label:  {by_label}")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()

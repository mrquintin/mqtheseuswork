# Theseus: The Methodological Reorientation

## The Thesis

Theseus is not about what is true. Theseus is about **how to determine what is true**.

This is the difference between a map and a compass. Maps become outdated the moment the terrain shifts. A compass works everywhere, forever, because it operates on a deeper principle — it doesn't tell you where you are, it tells you how to orient yourself relative to an invariant.

The existing Theseus research already lives on the methodological side:

- The **Embedding Geometry Conjecture** doesn't say *what* is contradictory. It says *how contradiction manifests geometrically* — a method for detecting it.
- The **Coherence Engine** doesn't say *which* arguments are good. It says *how to measure* argument quality — a method for evaluating it.
- The **Reverse Marxism Reflection** doesn't say *which* ideology is correct. It says *how to mechanically generate the strongest counter-position* — a method for stress-testing any claim.
- The **Quintin Hypothesis** itself is a methodological claim: noncontradiction is a measurable geometric property that correlates with real-world outcomes. It's a claim about the *reliability of a method*, not about any particular truth.

The reorientation makes this explicit and systematic. Every project Theseus builds should be an answer to the question: **"What is a reliable method for arriving at justified belief, and how do we make that method executable?"**

---

## The Seven Projects

Each project below is a distinct software system that operationalizes a specific truth-finding method. Together, they form an integrated epistemological toolkit — a machine for generating justified beliefs.

---

### Project 1: ALETHEIA — The Method Extraction Engine

**What it does:** Extracts not just *claims* from discourse but the *reasoning methods* used to arrive at those claims. Where Noosphere extracts "we believe X," Aletheia extracts "we arrived at X by method M" — and then evaluates whether M is a reliable method.

**Why it matters:** Two people can hold the same belief for entirely different reasons. One arrived at it through rigorous first-principles analysis; the other through confirmation bias. The belief is the same but the epistemological status is completely different. Aletheia captures this distinction.

**Core components:**
1. **Method Taxonomy** — A formal classification of reasoning methods: deduction, induction, abduction, analogy, appeal to authority, empirical observation, thought experiment, reductio ad absurdum, Bayesian updating, etc.
2. **Method Extractor** — Given a transcript or text, identifies which reasoning method is being used at each step. "He's using analogical reasoning here." "This is an inductive generalization from three cases."
3. **Method Evaluator** — Rates the reliability of each method *as applied*. Deduction from true premises is maximally reliable. Inductive generalization from three cases to a universal claim is weak. Analogy depends on the structural similarity of the domains.
4. **Method Graph** — A knowledge graph where nodes are methods (not claims) and edges represent relationships: "method A presupposes method B," "method A is stronger than method B in domain D," "method A fails in conditions C."

**Architecture:**
```
Transcript / Text
       │
       ▼
┌─────────────────────┐
│  ARGUMENT PARSER     │  Extract argument structure (premises → conclusion)
│  (Toulmin model)     │  using Claude with structured output
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  METHOD CLASSIFIER   │  For each inference step, classify the reasoning method
│  (fine-tuned model)  │  Taxonomy: deduction, induction, abduction, analogy, etc.
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  RELIABILITY SCORER  │  Rate each method's reliability given its application context
│  (rule-based + LLM)  │  Valid deduction from verified premises → 0.95
│                       │  Induction from 3 cases → 0.3
│                       │  Analogy between structurally similar domains → 0.6
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  METHOD GRAPH        │  Store methods, their relationships, and reliability scores
│  (NetworkX + JSON)   │  Query: "What methods does the firm use most reliably?"
└─────────────────────┘
```

---

### Project 2: THE DIALECTICAL CRUCIBLE — Automated Adversarial Testing

**What it does:** Given any proposition, mechanically generates the *strongest possible counter-argument* using the Reverse Marxism reflection technique, then evaluates both sides by *methodological quality* — not by which conclusion you prefer, but by which side reasons better.

**Why it matters:** The Reverse Marxism research proved that the strongest case for X is structurally isomorphic to the strongest case against X, reflected across the axis of contention. The Dialectical Crucible operationalizes this: it doesn't tell you which side is right, it tells you which side has better methodology.

**Core components:**
1. **Thesis Formalizer** — Takes a natural language claim and formalizes it: identifies the key concept axis, the direction of the argument, and the supporting premises.
2. **Antithesis Generator** — Reflects the thesis across its concept axis using Householder reflection in embedding space. Finds the nearest real-world arguments to the reflected embeddings.
3. **Synthesis Evaluator** — Evaluates both thesis and antithesis using the 6-layer Coherence Engine. Which side is more internally consistent? Which side has more load-bearing axioms? Where do they share common ground?
4. **Dialectical Report** — Produces a structured report: "The thesis scores 0.78 on coherence; the antithesis scores 0.72. The thesis is strongest in its empirical grounding (Layer 4) but weakest in its formal consistency (Layer 1) — there is a hidden contradiction between premises 3 and 7."

**This is Hegelian dialectics made computational.** Thesis, antithesis, and a synthesis that emerges not from compromise but from methodological superiority.

---

### Project 3: THE CALIBRATION ENGINE — Epistemic Feedback Loop

**What it does:** Tracks the firm's predictions against outcomes, computes Brier scores and calibration curves, identifies systematic biases, and provides feedback to improve the firm's truth-finding methodology over time.

**Why it matters:** A methodology's value is ultimately empirical — does it produce accurate beliefs? The Calibration Engine closes the loop: it measures whether the firm's methods actually work, and where they fail.

**Core components:**
1. **Prediction Registry** — Every time the firm makes a prediction (in a podcast, investment memo, or analysis), it gets registered with: the claim, the confidence level (0-1), the date, the method used, and the expected resolution date.
2. **Outcome Tracker** — Tracks whether predictions resolve as true or false. Handles partial resolutions and ambiguous outcomes.
3. **Brier Score Computer** — Computes Brier scores (and decomposition into calibration, resolution, and uncertainty components) across all predictions.
4. **Calibration Curve** — Plots predicted probability vs. actual frequency. Perfect calibration = diagonal line. Overconfidence = curve below diagonal. Identifies the firm's systematic biases.
5. **Method Attribution** — Cross-references with Aletheia: which reasoning methods produce the best-calibrated predictions? "Predictions grounded in empirical data have Brier score 0.12; predictions from analogical reasoning have Brier score 0.31."
6. **Feedback Reports** — Monthly reports: "Your methodology is well-calibrated for economic predictions (Brier 0.15) but overconfident on technology forecasts (Brier 0.38). The overconfidence correlates with reliance on analogical reasoning — consider using more empirical grounding in tech analysis."

---

### Project 4: THE AXIOM EXCAVATOR — Hidden Assumption Mining

**What it does:** Given any argument, decomposes it into its hidden axioms, tests each axiom for coherence with the rest, identifies which axioms are load-bearing (removing them collapses the argument) and which are ornamental (removing them changes nothing).

**Why it matters:** Every argument rests on assumptions. Most assumptions are invisible. The most dangerous intellectual failure is not *drawing the wrong conclusion* — it's *reasoning validly from a false premise you didn't know was there*. The Axiom Excavator makes the invisible visible.

**Core components:**
1. **Premise Extraction** — Uses argument mining to extract explicit premises from text.
2. **Implicit Assumption Detector** — Uses Claude to identify unstated assumptions. "This argument assumes that market prices reflect all available information. This assumption is not stated but is required for the conclusion to follow."
3. **Dependency Graph** — Maps which conclusions depend on which premises. Directed acyclic graph of logical dependencies.
4. **Load-Bearing Analysis** — For each axiom, computes: "If this axiom were false, which conclusions would be invalidated?" Axioms that invalidate many conclusions are load-bearing. This uses the Coherence Engine's argumentation layer (Layer 2) — remove the axiom and see how the grounded extension changes.
5. **Stress Test** — For each load-bearing axiom, asks: "How certain are we that this axiom is true? What evidence supports it? What would falsify it?" Produces a vulnerability map of the argument.
6. **Sensitivity Report** — "Your investment thesis rests on 3 load-bearing axioms. Axiom 2 (that regulatory barriers will persist for 5+ years) is supported only by historical precedent, not structural analysis. If this axiom fails, conclusions 4, 7, and 9 all collapse."

---

### Project 5: THE VERISIMILITUDE ENGINE — Theory-Proximity Metrics

**What it does:** Implements formal truthlikeness metrics (Oddie, Niiniluoto, Schurz) to measure not whether a theory is *true or false* but *how close it is to the truth*. Enables comparison of competing theories by proximity to truth, not binary correctness.

**Why it matters:** Almost no theory is perfectly true. Almost no theory is completely false. What matters is the *degree* to which a theory approximates truth — its verisimilitude. A theory that gets 80% of the picture right is more valuable than one that gets 50%, even though both are technically "wrong." The Verisimilitude Engine makes this measurable.

**Core components:**
1. **Theory Formalizer** — Converts a natural-language theory into a set of atomic propositions with truth-value assignments.
2. **Truth-State Estimator** — For propositions where the truth is known (from empirical data, resolved predictions, etc.), establishes the ground truth. For unresolved propositions, uses the Calibration Engine's confidence estimates.
3. **Oddie Distance** — Computes the average distance between the theory's truth-value assignments and the actual truth values, weighted by proposition importance.
4. **Niiniluoto Similarity** — Computes Niiniluoto's min-sum measure: how similar is the theory to the nearest complete true description?
5. **Comparative Analysis** — Given two competing theories about the same domain, computes which one is closer to the truth (higher verisimilitude). "Theory A has verisimilitude 0.73; Theory B has 0.61. Theory A is closer to the truth, primarily because it correctly accounts for the role of interest rates (propositions 4-7) while Theory B does not."
6. **Improvement Vector** — Identifies which propositions, if corrected, would most improve the theory's verisimilitude. "Revising your assumption about regulatory capture (proposition 12) would increase verisimilitude from 0.73 to 0.81."

---

### Project 6: THE EPISTEMIC PROCESS AUDITOR — Reasoning Quality Assurance

**What it does:** Evaluates not whether a conclusion is *correct*, but whether the *process* used to reach it was *sound*. This is methodology auditing — checking whether the firm followed its own best practices for truth-finding.

**Why it matters:** Good methodology can occasionally produce wrong conclusions (bad luck). Bad methodology can occasionally produce right conclusions (good luck). Over the long run, methodology is everything. The Auditor ensures the firm's methodology stays rigorous even when the conclusions happen to be right.

**Core components:**
1. **Process Checklist Generator** — For each type of analysis (investment thesis, market prediction, research assessment), generates a methodological checklist. "Did you: (a) identify your axioms? (b) check for internal contradiction? (c) generate the strongest counter-argument? (d) ground empirical claims in data? (e) specify a falsification condition?"
2. **Audit Scorer** — Scores each analysis on methodological compliance. "This investment memo scores 7/10: strong empirical grounding, good counter-argument consideration, but no falsification condition specified and one hidden assumption identified."
3. **Pattern Detector** — Identifies recurring methodological weaknesses. "Across the last 20 analyses, the firm consistently fails to specify falsification conditions (compliance: 15%) and tends to over-rely on analogical reasoning (used in 78% of analyses but produces the worst calibration scores)."
4. **Improvement Recommendations** — "Based on the Calibration Engine data and the Aletheia method graph, the firm should: (1) Always specify what would change its mind, (2) Replace analogical reasoning with empirical base-rate analysis where possible, (3) Run the Dialectical Crucible on every investment thesis before finalizing."

---

### Project 7: THE BELIEF REVISION SYSTEM — Formal Rational Updating

**What it does:** Implements AGM belief revision theory as a working system. Tracks the firm's belief set, formally computes how beliefs *should* change given new evidence, and compares "should update" against "actually updated" to measure rational discipline.

**Why it matters:** Rational belief revision has formal rules (AGM theory, Bayesian updating). Humans systematically violate these rules — we anchor on prior beliefs, dismiss disconfirming evidence, and update asymmetrically. The Belief Revision System makes the rational ideal explicit and measures deviation from it.

**Core components:**
1. **Belief Set Manager** — Maintains the firm's current belief set as a formally structured collection. Each belief has: a proposition, a confidence level, supporting evidence, and an entrenchment ranking (how resistant it is to revision).
2. **Evidence Integrator** — When new evidence arrives, formally computes the required update using AGM contraction/revision operations and Bayesian conditioning.
3. **Rational Update Calculator** — Given the firm's belief set and new evidence, computes: "The rational response to this evidence is to revise belief X from confidence 0.8 to 0.6 and contract belief Y entirely."
4. **Actual Update Tracker** — Tracks what the firm *actually* does in response to new evidence (from podcast analysis via Noosphere).
5. **Rationality Score** — Compares the rational update with the actual update. "Rationality score: 0.72. The firm correctly revised 3 of 4 beliefs but failed to contract belief Y despite strong disconfirming evidence."
6. **Entrenchment Analysis** — Identifies beliefs that are *too* entrenched — beliefs the firm should have revised given the evidence but didn't. "Belief X has been contradicted by evidence in episodes 12, 17, and 23, but has never been revised. Entrenchment may be irrational."

---

## Integration Architecture

The seven projects are not independent. They form an integrated epistemic infrastructure:

```
                    ┌──────────────────────────┐
                    │    NOOSPHERE             │
                    │    (Transcript Ingestion)  │
                    └──────────┬───────────────┘
                               │
                    ┌──────────┴───────────────┐
                    │      ALETHEIA            │
                    │  (Method Extraction)      │
                    └──────────┬───────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
    ┌─────────┴──────┐ ┌──────┴───────┐ ┌──────┴──────────┐
    │   DIALECTICAL  │ │    AXIOM     │ │    BELIEF       │
    │   CRUCIBLE     │ │  EXCAVATOR   │ │   REVISION      │
    │(Adversarial    │ │(Hidden       │ │  SYSTEM         │
    │ Testing)       │ │ Assumptions) │ │(Rational        │
    └────────┬───────┘ └──────┬───────┘ │ Updating)       │
             │                │         └──────┬──────────┘
             └────────┬───────┘                │
                      │                        │
           ┌──────────┴───────────┐            │
           │  VERISIMILITUDE      │            │
           │  ENGINE              │◄───────────┘
           │  (Truth-Proximity)   │
           └──────────┬───────────┘
                      │
           ┌──────────┴───────────┐
           │  CALIBRATION ENGINE  │
           │  (Feedback Loop)     │
           └──────────┬───────────┘
                      │
           ┌──────────┴───────────┐
           │  EPISTEMIC PROCESS   │
           │  AUDITOR             │
           │  (Quality Assurance) │
           └──────────────────────┘
```

**Data flows:**
- Noosphere ingests raw discourse → Aletheia extracts methods → feeds Axiom Excavator and Dialectical Crucible
- Dialectical Crucible stress-tests claims → feeds Verisimilitude Engine
- Calibration Engine tracks outcomes → feeds back to Epistemic Process Auditor
- Belief Revision System compares rational vs. actual updates → feeds Auditor
- Auditor produces recommendations → improve all upstream methods

---

## LLM Build Prompts

The following prompts are designed to be given to Claude (or another capable LLM) to build each project's core software. Each prompt is self-contained and produces a working Python module.

---

### PROMPT 1: Build Aletheia — The Method Extraction Engine

```
You are building "Aletheia," a Python system that extracts reasoning methods from natural language text and evaluates their reliability.

CONTEXT: This is part of Theseus, an intellectual capital firm focused on truth-finding methodology. Aletheia answers: "What reasoning method was used to arrive at this claim, and how reliable is that method?"

BUILD THE FOLLOWING:

1. A file `aletheia/taxonomy.py` containing:
   - An enum `ReasoningMethod` with values: DEDUCTION, INDUCTION, ABDUCTION, ANALOGY, EMPIRICAL_OBSERVATION, THOUGHT_EXPERIMENT, REDUCTIO, BAYESIAN_UPDATE, APPEAL_TO_AUTHORITY, APPEAL_TO_PRECEDENT, COUNTERFACTUAL, DIALECTICAL, FIRST_PRINCIPLES, STATISTICAL_INFERENCE, CAUSAL_INFERENCE
   - A dataclass `MethodApplication` with fields: method (ReasoningMethod), description (str), premises (list[str]), conclusion (str), reliability_score (float 0-1), confidence (float 0-1), context (str)
   - A dict `METHOD_RELIABILITY_PRIORS` mapping each method to its base reliability score (deduction from true premises: 0.95, induction from <5 cases: 0.25, etc.)
   - A dict `METHOD_DESCRIPTIONS` with rigorous epistemological descriptions of each method

2. A file `aletheia/extractor.py` containing:
   - Class `ArgumentParser` that takes text and uses Claude API to extract argument structure in Toulmin format: (data, warrant, backing, qualifier, rebuttal, claim)
   - Class `MethodClassifier` that takes an argument structure and classifies which reasoning method is being used. Uses Claude with a detailed taxonomy prompt that includes examples of each method. Returns MethodApplication objects.
   - Class `ReliabilityScorer` that adjusts the base reliability score based on application context:
     * Deduction: Check if premises are verified → adjust score
     * Induction: Count the number of cases → more cases = higher reliability
     * Analogy: Assess structural similarity between source and target domains → more similar = higher reliability
     * Empirical: Check if observation is reproducible, controlled → adjust
     * Each adjustment is documented with reasoning

3. A file `aletheia/graph.py` containing:
   - Class `MethodGraph` using NetworkX that stores methods as nodes and relationships (PRESUPPOSES, STRONGER_THAN, FAILS_IN, COMPLEMENTS) as edges
   - Methods to query: most reliable methods for a given domain, methods the firm uses most frequently, methods with best calibration scores
   - Persistence to JSON

4. A file `aletheia/analyzer.py` containing:
   - Class `MethodAnalyzer` that takes a full text, runs it through ArgumentParser → MethodClassifier → ReliabilityScorer, and produces a complete methodological analysis
   - Output: list of MethodApplication objects, aggregate reliability score, identification of the weakest methodological link, recommendations for improvement

Use: anthropic SDK for Claude, pydantic for data models, networkx for graphs, numpy for computations.
All code must be production-quality: type hints, docstrings, logging, error handling.
No mock implementations — every function must actually work.
```

---

### PROMPT 2: Build The Dialectical Crucible

```
You are building "The Dialectical Crucible," a Python system that implements Hegelian dialectics computationally — generating the strongest possible counter-argument to any thesis and evaluating both sides by methodological quality.

CONTEXT: This is part of Theseus, a firm that has validated the "Embedding Geometry Conjecture" — logical contradiction manifests as sparse difference vectors in embedding space. They have also developed "Reverse Marxism" — a technique using Householder reflection (v' = v - 2(v·â)â) to generate ideological counter-positions by reflecting text embeddings across concept axes.

BUILD THE FOLLOWING:

1. A file `crucible/thesis.py` containing:
   - Class `ThesisAnalyzer` that takes a natural language claim and:
     * Identifies the key concept axis (what the argument is fundamentally about)
     * Extracts the direction of the argument (for/against what)
     * Identifies supporting premises
     * Uses Claude to formalize the thesis into: (core_claim, concept_axis_terms, supporting_premises, domain)
   - Class `ConceptAxis` that builds embedding-space axes from term lists:
     * `build(positive_terms, negative_terms=None)` → normalized axis vector
     * Pre-built axes: "class", "liberty", "equality", "efficiency", "tradition", "progress", "individual", "collective", "empirical", "theoretical"

2. A file `crucible/antithesis.py` containing:
   - Class `AntithesisGenerator` that:
     * Takes a formalized thesis and its embeddings
     * Reflects all thesis embeddings across the concept axis using Householder reflection
     * Finds the nearest real-world arguments to the reflected embeddings from a reference corpus
     * Uses Claude to synthesize a coherent antithesis from the nearest matches
     * The antithesis preserves the STRUCTURE of the thesis while inverting its ORIENTATION
   - Must handle multiple concept axes (reflect across "liberty" produces a different antithesis than reflecting across "efficiency")

3. A file `crucible/synthesis.py` containing:
   - Class `DialecticalEvaluator` that:
     * Takes thesis and antithesis
     * Scores both using a coherence engine (implement simplified version with: embedding coherence, compression coherence, and LLM judge)
     * Identifies points of genuine agreement (propositions both sides accept)
     * Identifies the core disagreement (the irreducible point of contention)
     * Evaluates which side has BETTER METHODOLOGY (not which conclusion is right):
       - Which side has more verified premises?
       - Which side has fewer internal contradictions?
       - Which side specifies clearer falsification conditions?
       - Which side's evidence is more reproducible?
     * Produces a synthesis: "The thesis is methodologically stronger in X; the antithesis is methodologically stronger in Y; the core unresolved question is Z"

4. A file `crucible/report.py` containing:
   - Class `DialecticalReport` that generates a structured report:
     * Thesis summary and coherence score
     * Antithesis summary and coherence score
     * Methodological comparison table
     * Points of agreement
     * Core disagreement
     * Synthesis recommendation
     * Rendered as both JSON and formatted markdown

Use: sentence-transformers for embeddings (all-mpnet-base-v2), numpy for reflection, anthropic SDK for Claude, pydantic for models.
All code must be production-quality.
```

---

### PROMPT 3: Build The Calibration Engine

```
You are building "The Calibration Engine," a Python system that tracks predictions against outcomes, computes accuracy metrics, and identifies systematic biases in reasoning methodology.

CONTEXT: This is part of Theseus, a firm focused on truth-finding methodology. The Calibration Engine is the empirical feedback loop that measures whether the firm's methods actually produce accurate beliefs.

BUILD THE FOLLOWING:

1. A file `calibration/models.py` containing Pydantic models:
   - `Prediction`: id, claim (str), confidence (float 0-1), date_made, expected_resolution_date, method_used (str), domain (str), reasoning (str), source_episode (optional str)
   - `Outcome`: prediction_id, resolved (bool), resolution_date, outcome_value (bool), evidence (str), ambiguity_score (float 0-1, how clear the resolution is)
   - `CalibrationBin`: confidence_range (tuple), predicted_probability (float), observed_frequency (float), count (int)
   - `BrierDecomposition`: calibration (float), resolution (float), uncertainty (float), total_brier (float)
   - `MethodCalibration`: method_name, brier_score, prediction_count, calibration_curve (list of CalibrationBin)

2. A file `calibration/registry.py` containing:
   - Class `PredictionRegistry` that:
     * Stores predictions in a JSON file
     * Registers new predictions: `register(claim, confidence, method_used, domain, ...)`
     * Records outcomes: `resolve(prediction_id, outcome_value, evidence)`
     * Queries: by domain, by method, by date range, by confidence level, resolved/unresolved
     * Auto-extracts predictions from podcast transcripts using Claude (given a transcript, finds statements that are implicitly or explicitly predictive and registers them with inferred confidence levels)

3. A file `calibration/metrics.py` containing:
   - `brier_score(predictions, outcomes)` → float (0 = perfect, 1 = worst)
   - `brier_decomposition(predictions, outcomes)` → BrierDecomposition (calibration + resolution + uncertainty)
   - `calibration_curve(predictions, outcomes, n_bins=10)` → list[CalibrationBin]
   - `log_score(predictions, outcomes)` → float
   - `overconfidence_index(calibration_curve)` → float (positive = overconfident, negative = underconfident)
   - `domain_breakdown(predictions, outcomes)` → dict[str, BrierDecomposition]
   - `method_breakdown(predictions, outcomes)` → dict[str, MethodCalibration]

4. A file `calibration/analyzer.py` containing:
   - Class `CalibrationAnalyzer` that:
     * Takes the full prediction registry
     * Computes all metrics
     * Identifies systematic biases: "The firm is overconfident in tech predictions and underconfident in macro predictions"
     * Cross-references with reasoning methods: "Predictions using empirical grounding have Brier 0.12; predictions from analogy have Brier 0.31"
     * Generates improvement recommendations
     * Tracks calibration improvement over time (is the firm getting better?)
   - Class `FeedbackReport` that produces monthly/quarterly reports with all metrics, visualizations (matplotlib), and actionable recommendations

5. A file `calibration/extractor.py` containing:
   - Class `PredictionExtractor` that:
     * Takes podcast transcript text
     * Uses Claude to identify predictive statements (explicit and implicit)
     * For each prediction, estimates the speaker's confidence level
     * Returns list of Prediction objects ready for registration

Use: numpy, scipy for statistics, matplotlib for plotting, pydantic for models, anthropic SDK for extraction.
All code must be production-quality with proper statistical rigor in the implementations.
```

---

### PROMPT 4: Build The Axiom Excavator

```
You are building "The Axiom Excavator," a Python system that decomposes arguments into their hidden assumptions, identifies which assumptions are load-bearing, and produces vulnerability maps.

CONTEXT: Part of Theseus, a firm focused on truth-finding methodology. The Axiom Excavator answers: "What are you assuming without knowing it, and what happens if those assumptions are wrong?"

BUILD THE FOLLOWING:

1. A file `excavator/models.py` containing:
   - `Axiom`: id, text (str), is_explicit (bool), is_load_bearing (bool), certainty (float 0-1), evidence (list[str]), falsification_condition (str), conclusions_dependent (list[str])
   - `DependencyEdge`: axiom_id, conclusion_id, necessity ("necessary" | "sufficient" | "supporting"), strength (float)
   - `VulnerabilityReport`: argument_summary, axiom_count, load_bearing_count, most_vulnerable_axiom, overall_robustness (float 0-1), recommendations (list[str])

2. A file `excavator/extractor.py` containing:
   - Class `PremiseExtractor` that uses Claude to extract all explicit premises from text
   - Class `ImplicitAssumptionDetector` that uses Claude with a specialized prompt to identify UNSTATED assumptions. The prompt should instruct Claude to:
     * For each inference step, ask "What must be true for this step to be valid?"
     * Identify domain-specific assumptions (economic assumptions, physical assumptions, social assumptions)
     * Identify methodological assumptions ("This assumes induction is reliable in this domain")
     * Identify framing assumptions ("This assumes the relevant comparison class is X, not Y")
     * Return each assumption with: the text, which inference step requires it, and an initial certainty estimate

3. A file `excavator/dependency.py` containing:
   - Class `DependencyGraphBuilder` that:
     * Takes axioms (explicit + implicit) and conclusions
     * Uses Claude to determine which conclusions depend on which axioms
     * Builds a directed acyclic graph (NetworkX) of logical dependencies
     * Handles transitive dependencies (if C depends on B depends on A, then C depends on A)
   - Class `LoadBearingAnalyzer` that:
     * For each axiom, computes: if this axiom were removed, which conclusions would be invalidated?
     * An axiom is "load-bearing" if removing it invalidates >30% of conclusions
     * Computes "axiom centrality" using betweenness centrality on the dependency graph
     * Computes "axiom fragility" — how certain are we that this axiom is true? Fragile load-bearing axioms are the most dangerous.

4. A file `excavator/stress_test.py` containing:
   - Class `AxiomStressTester` that:
     * For each load-bearing axiom, uses Claude to:
       - Identify what evidence supports this axiom
       - Identify what would falsify this axiom
       - Rate the axiom's certainty given available evidence
       - Generate the strongest argument AGAINST this axiom
     * Computes overall argument robustness: weighted average of load-bearing axiom certainties
   - Class `SensitivityReport` that formats the full analysis into a vulnerability map

Use: networkx for dependency graphs, pydantic for models, anthropic SDK for extraction, numpy for computations.
All code must be production-quality.
```

---

### PROMPT 5: Build The Verisimilitude Engine

```
You are building "The Verisimilitude Engine," a Python system that implements formal truthlikeness metrics to measure how close a theory is to the truth. This is the first-ever production implementation of Oddie/Niiniluoto verisimilitude theory as working software.

CONTEXT: Part of Theseus, a firm focused on truth-finding methodology. The Verisimilitude Engine answers: "How close is this theory to being fully true, and what changes would bring it closer?"

BUILD THE FOLLOWING:

1. A file `verisimilitude/models.py` containing:
   - `Proposition`: id, text (str), truth_value (Optional[bool]), confidence (float 0-1), domain (str)
   - `Theory`: id, name (str), propositions (list[Proposition]), domain (str)
   - `TruthState`: propositions mapped to their actual truth values (where known)
   - `VerisimilitudeScore`: theory_id, oddie_score (float 0-1), niiniluoto_score (float 0-1), component_scores (dict), improvement_vector (list of (proposition_id, current_value, recommended_value, expected_improvement))

2. A file `verisimilitude/formalizer.py` containing:
   - Class `TheoryFormalizer` that:
     * Takes a natural language theory/thesis and uses Claude to decompose it into atomic propositions
     * Each proposition must be a binary (true/false) claim
     * Complex claims are decomposed: "Markets are efficient" → ["Market prices reflect public information", "Market prices reflect private information", "No investor can consistently outperform the market"]
     * Returns a Theory object

3. A file `verisimilitude/metrics.py` containing:
   - Class `OddieDistance` implementing Oddie's average distance measure:
     * distance(theory, truth_state) = (1/n) * Σ |t(pᵢ) - τ(pᵢ)| where t = theory's assignment, τ = actual truth
     * verisimilitude = 1 - distance (higher = closer to truth)
     * Handles unknown truth values by using confidence as weight
   - Class `NiiniluotoSimilarity` implementing Niiniluoto's min-sum measure:
     * For each possible complete truth state consistent with the theory, compute the distance to the actual truth state
     * verisimilitude = 1 - min(distances) (how close the theory's BEST interpretation is to truth)
   - Class `WeightedVerisimilitude` that weights propositions by importance:
     * More central propositions (those that other propositions depend on) get higher weight
     * Uses the dependency structure from the Axiom Excavator if available
   - All metrics must handle partial truth states (some propositions' truth values are unknown)

4. A file `verisimilitude/comparator.py` containing:
   - Class `TheoryComparator` that:
     * Takes two competing theories about the same domain
     * Formalizes both into proposition sets
     * Computes verisimilitude for both
     * Identifies where they agree (shared true propositions)
     * Identifies where they disagree (conflicting propositions)
     * Determines which is closer to truth and WHY (which propositions make the difference)
   - Class `ImprovementAdvisor` that:
     * For a given theory, identifies which propositions, if corrected, would most improve verisimilitude
     * Uses sensitivity analysis: flip each uncertain proposition and recompute
     * Returns ranked list of "highest-impact corrections"

Use: numpy for distance computations, itertools for combinatorics, pydantic for models, anthropic SDK for formalization.
Include rigorous docstrings explaining the formal epistemological theory behind each metric.
```

---

### PROMPT 6: Build The Epistemic Process Auditor

```
You are building "The Epistemic Process Auditor," a Python system that evaluates reasoning PROCESSES for methodological soundness, independent of whether the conclusions are correct.

CONTEXT: Part of Theseus, a firm focused on truth-finding methodology. The Auditor answers: "Was the method used to arrive at this conclusion sound, regardless of whether the conclusion turned out to be right?"

BUILD THE FOLLOWING:

1. A file `auditor/checklist.py` containing:
   - Class `MethodologicalChecklist` with domain-specific checklists:
     * INVESTMENT_THESIS: [axioms_identified, contradictions_checked, counter_argument_generated, falsification_specified, empirical_grounding, base_rate_considered, second_order_effects, time_horizon_specified]
     * MARKET_PREDICTION: [base_rate_anchored, reference_class_identified, inside_view_vs_outside_view, confidence_calibrated, track_record_considered]
     * RESEARCH_ASSESSMENT: [methodology_evaluated, sample_size_adequate, confounders_addressed, replication_status, effect_size_meaningful, publication_bias_considered]
     * GENERAL_ANALYSIS: [premises_explicit, logic_valid, assumptions_identified, counterevidence_considered, confidence_proportional_to_evidence]
   - Each checklist item has: name, description, weight (importance), evaluation_prompt (what to ask Claude to check)

2. A file `auditor/scorer.py` containing:
   - Class `ProcessScorer` that:
     * Takes an analysis text and a checklist type
     * For each checklist item, uses Claude to evaluate whether the analysis satisfies it
     * Returns a score per item (0 = not met, 0.5 = partially met, 1 = fully met) with explanation
     * Computes weighted aggregate score
     * Identifies the weakest methodological link

3. A file `auditor/patterns.py` containing:
   - Class `PatternDetector` that:
     * Analyzes scores across multiple analyses over time
     * Identifies recurring methodological weaknesses: "Across 20 analyses, falsification conditions are specified only 15% of the time"
     * Identifies improving and deteriorating practices
     * Correlates methodological compliance with prediction accuracy (from Calibration Engine)
     * Detects cognitive biases from patterns: "The firm's confidence exceeds evidence strength by an average of 0.15 points, consistent with overconfidence bias"

4. A file `auditor/report.py` containing:
   - Class `AuditReport` that generates:
     * Per-analysis audit: score, item-by-item evaluation, recommendations
     * Periodic review: patterns, trends, correlations with accuracy
     * Improvement plan: ranked list of methodological improvements with expected impact on prediction accuracy
     * Formats as both JSON and rich markdown

Use: pydantic for models, anthropic SDK for evaluation, numpy for statistics, matplotlib for trend visualization.
The system should be designed so it can be run automatically on every new analysis or podcast transcript.
```

---

### PROMPT 7: Build The Belief Revision System

```
You are building "The Belief Revision System," a Python implementation of AGM belief revision theory — the first production system that formally computes how beliefs should rationally change given new evidence.

CONTEXT: Part of Theseus, a firm focused on truth-finding methodology. The Belief Revision System answers: "Given this new evidence, how SHOULD our beliefs change — and how did they ACTUALLY change?"

BUILD THE FOLLOWING:

1. A file `revision/models.py` containing:
   - `Belief`: id, proposition (str), confidence (float 0-1), entrenchment (float 0-1, how resistant to revision), evidence (list[str]), first_held (date), last_updated (date), source_episodes (list[str])
   - `BeliefSet`: beliefs (list[Belief]), consistency_score (float), last_checked (datetime)
   - `Evidence`: id, content (str), source (str), date (date), strength (float 0-1), relevant_beliefs (list[str])
   - `RevisionOperation`: type ("expansion" | "revision" | "contraction"), belief_id, old_confidence, new_confidence, reason (str), evidence_id
   - `RationalityScore`: period (str), operations_expected (list[RevisionOperation]), operations_actual (list[RevisionOperation]), alignment_score (float 0-1), failures (list[str])

2. A file `revision/belief_set.py` containing:
   - Class `BeliefSetManager` that:
     * Maintains the firm's current belief set
     * Adds beliefs (expansion): add a new belief consistent with existing set
     * Revises beliefs (revision): update confidence given contradicting evidence, using AGM revision postulates
     * Contracts beliefs (contraction): remove a belief from the set, choosing what to give up using entrenchment ordering
     * Checks consistency: uses NLI (via Claude) to detect contradictions within the belief set
     * Persists to JSON with full history
   - Implements the **AGM postulates**:
     * Success: The new information is always included in the revised set
     * Inclusion: Revision doesn't add beliefs beyond what's necessary
     * Vacuity: If the new info doesn't contradict, revision = expansion
     * Consistency: The revised set is consistent if the new info is consistent
     * Extensionality: Logically equivalent inputs produce identical revisions
     * Minimal change: Revision changes as little as possible (using entrenchment ordering)

3. A file `revision/updater.py` containing:
   - Class `RationalUpdater` that:
     * Takes new evidence and the current belief set
     * Computes the RATIONAL update: which beliefs should change, by how much, and why
     * Uses Bayesian conditioning where confidence values are available
     * Uses AGM contraction for beliefs that must be abandoned
     * Returns a list of RevisionOperation objects representing the rational update
   - Class `ActualUpdateTracker` that:
     * Monitors podcast transcripts (via Noosphere) for changes in the firm's expressed beliefs
     * Detects when the firm has changed its mind about something
     * Returns actual RevisionOperation objects
   - Class `RationalityAnalyzer` that:
     * Compares rational updates with actual updates
     * Computes RationalityScore: how well did the firm approximate rational belief revision?
     * Identifies specific failures: "Evidence E should have reduced confidence in belief B from 0.8 to 0.5, but the firm still expresses confidence 0.75"
     * Identifies irrational entrenchment: beliefs that should have been revised but weren't

4. A file `revision/entrenchment.py` containing:
   - Class `EntrenchmentOrderer` that computes rational entrenchment for each belief:
     * Beliefs supported by more evidence → higher entrenchment
     * Beliefs that support many other beliefs → higher entrenchment (load-bearing)
     * Beliefs held for longer with consistent reinforcement → higher entrenchment
     * Beliefs with empirical grounding → higher entrenchment than those with only theoretical support
     * Formula: E(b) = α·evidence_count + β·centrality + γ·duration + δ·empirical_grounding
     * Entrenchment determines what gets contracted first when consistency requires giving something up

Use: pydantic for models, anthropic SDK for NLI and extraction, networkx for belief dependency structure, numpy for computations.
Implement the AGM postulates rigorously — this is the first production implementation and must be formally correct.
```

---

## Summary

These seven projects transform Theseus from a firm that *has* beliefs into a firm that *has a machine for producing and testing beliefs*. The firm's intellectual product is not "we think X is true" but "here is a formally rigorous, empirically calibrated, computationally executable method for determining whether X is true — and we can prove our method works by showing its calibration scores, coherence metrics, and prediction track record."

This is the methodological reorientation: the method IS the product.

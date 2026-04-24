# Methods & Experiments Quick Reference

## Quantifying Value with Formal Logic: Formalizing Noncontradiction as a Metric for Idea Evaluation

---

## Core Pipeline Architecture

```
Input Text (pitch, thesis, theory)
        │
        ▼
┌─────────────────────┐
│  LAYER 1: ARGUMENT  │   Transformer-based argument mining
│     EXTRACTION      │   Outputs: claims, premises, evidence, relations
└─────────┬───────────┘
          │
     ┌────┴─────┬──────────┬──────────┬──────────┐
     ▼          ▼          ▼          ▼          ▼
┌─────────┐┌─────────┐┌─────────┐┌─────────┐┌─────────┐
│ LAYER 2 ││ LAYER 3 ││ LAYER 4 ││ LAYER 5 ││ LAYER 6 │
│Consist- ││ Argumen-││Probabil-││Embedding││ Info-   │
│ency     ││ tation  ││istic    ││Geometry ││ Theory  │
│Check    ││Analysis ││Coherence││Analysis ││Measures │
└────┬────┘└────┬────┘└────┬────┘└────┬────┘└────┬────┘
     └────┬─────┴──────────┴──────────┴──────────┘
          ▼
┌─────────────────────┐
│  COMPOSITE SCORE    │   Weighted combination + LLM judge
│    Coh(Γ) ∈ [0,1]  │   Calibrated against expert judgment
└─────────────────────┘
```

---

## Layer-by-Layer Method Summary

### Layer 1: Argument Extraction

| Component | Tool/Method | Input | Output |
|-----------|-------------|-------|--------|
| Claim detection | Fine-tuned DeBERTa / GPT-4 | Raw text | List of claims |
| Premise identification | Argument mining model | Raw text | Premises linked to claims |
| Relation extraction | NLI + relation classifier | Claim-premise pairs | Support/attack labels |
| Graph construction | NetworkX / custom | Components + relations | Directed argument graph |

**Key Models:** IBM Project Debater, fine-tuned RoBERTa, GPT-4 with in-context examples

---

### Layer 2: Formal Consistency Checking

| Method | What It Checks | Complexity | Tool |
|--------|---------------|------------|------|
| SAT (CDCL) | Propositional consistency | NP-complete (fast in practice) | MiniSat, CaDiCaL |
| SMT | Theory-enriched consistency | Depends on theory | Z3, cvc5 |
| NLI pairwise | Natural language contradictions | O(n²) pairs | DeBERTa-v3-large-mnli |
| Paraconsistent analysis | Local contradiction severity | Linear in contradictions | Custom (Da Costa LFI) |

**Key Formula — Weighted Contradiction Score:**

```
WCS(Γ) = Σ_{contradictory pairs} (w(sᵢ) + w(sⱼ))/2  ÷  Σ_{all pairs} (w(sᵢ) + w(sⱼ))/2
```

**Consistency Score:** `S₁ = 1 - WCS(Γ)`

---

### Layer 3: Argumentation-Theoretic Analysis

| Semantics | Property | Uniqueness | Conservatism |
|-----------|----------|------------|--------------|
| Grounded | Least fixed point of F | Always unique | Most conservative |
| Preferred | Maximal admissible sets | May be multiple | Moderate |
| Stable | Conflict-free + attacks all outside | May not exist | Most aggressive |

**Key Formula — Argumentation Score:**

```
S₂ = |Grounded Extension| / |Total Arguments|
```

**Algorithm: Grounded Extension**

```
E = ∅
repeat:
    Defeated = {b ∈ A : ∃ a ∈ E, (a,b) ∈ R}
    Unattacked = {a ∈ A\E : ∀ b, (b,a) ∈ R → b ∈ Defeated}
    E = E ∪ Unattacked
until no change
return E
```

---

### Layer 4: Probabilistic Coherence

| Measure | Formula | Best For |
|---------|---------|----------|
| Shogenji | P(P₁∧...∧Pₙ) / (P(P₁)×...×P(Pₙ)) | Reliability assessment |
| Olsson | P(P₁∧...∧Pₙ) / P(P₁∨...∨Pₙ) | Overlap assessment |
| Fitelson | Mean support across all subsets | Comprehensive analysis |
| **Roche** (recommended) | Mean of [P(Pᵢ\|Pⱼ) - P(Pᵢ\|¬Pⱼ)] | **Best empirical performer** |

**Key Formula — Roche's Measure:**

```
C_R(Γ) = (1/C(n,2)) × Σᵢ<ⱼ [P(Pᵢ|Pⱼ) - P(Pᵢ|¬Pⱼ)]
```

**Probabilistic Score:** `S₃ = sigmoid(C_R(Γ))`

---

### Layer 5: Embedding-Geometric Analysis

| Metric | What It Measures | Range |
|--------|-----------------|-------|
| Average pairwise cosine | Semantic clustering tightness | [-1, 1] |
| Contradiction projection | Opposing directions on concept axes | Continuous |
| Cluster dispersion | Variance in embedding space | [0, ∞) |

**Key Formula — Embedding Coherence:**

```
S₄ = (2/n(n-1)) × Σᵢ<ⱼ cos(emb(sᵢ), emb(sⱼ))
```

**Concept-Axis Reflection:**

```
a_concept = (1/k) Σ emb(c⁺ᵢ) - (1/k) Σ emb(c⁻ᵢ)
reflect(v, a) = v - 2(v·â/||â||²)â
```

---

### Layer 6: Information-Theoretic Measures

| Measure | Formula | Interpretation |
|---------|---------|----------------|
| Compression coherence | 1 - K(joint) / ΣK(individual) | Higher = more coherent |
| Redundancy | 1 - H(Γ)/H_max(Γ) | Higher = more circular |
| Mutual information | H(X)+H(Y)-H(X,Y) | Higher = more connected |

**Key Formula — Compression Coherence:**

```
S₅ = 1 - K(s₁,...,sₙ) / (K(s₁) + ... + K(sₙ))
```

Approximate K using gzip/zlib compression length.

---

### Composite Score

```
Coh(Γ) = w₁·S₁ + w₂·S₂ + w₃·S₃ + w₄·S₄ + w₅·S₅ + w₆·S₆
```

Where S₆ = LLM judge ensemble score (CoT prompted, normalized).

Weights w₁...w₆ calibrated via regression against expert human coherence judgments.

---

## Proposed Experiments

### Experiment 1: Contradiction Detection Accuracy

| Parameter | Value |
|-----------|-------|
| **Objective** | Validate NLI pipeline against human annotations |
| **Data** | 200 startup pitches + product theses |
| **Annotators** | 3 domain experts per document |
| **Metric** | Precision, recall, F1 vs. human consensus |
| **Success** | F1 > 0.75 |
| **Timeline** | Months 1-3 |

### Experiment 2: Coherence Score vs. Business Outcomes

| Parameter | Value |
|-----------|-------|
| **Objective** | Test predictive validity of composite score |
| **Data** | 500 historical startups (250 succeeded, 250 failed) |
| **Method** | Score founding theses, correlate with 5-year outcome |
| **Metric** | Spearman correlation, logistic regression AUC |
| **Success** | p < 0.01 on correlation; AUC > 0.65 |
| **Timeline** | Months 12-18 |

### Experiment 3: Embedding Geometry of Contradiction

| Parameter | Value |
|-----------|-------|
| **Objective** | Test geometric contradiction signatures |
| **Data** | 10,000 balanced statement pairs (entailment/contradiction/neutral) |
| **Models** | SBERT, InstructOR, OpenAI embeddings |
| **Method** | Train classifier on geometric features only |
| **Success** | >80% accuracy from geometry alone |
| **Timeline** | Months 3-6 |

### Experiment 4: Society's Premises Extraction

| Parameter | Value |
|-----------|-------|
| **Objective** | Extract foundational societal premises from corpora |
| **Data** | UN declarations, constitutions, landmark decisions, economic texts |
| **Method** | Argument mining at scale + hierarchical clustering |
| **Validation** | Delphi panel of philosophers, economists, legal scholars |
| **Success** | >70% expert agreement on extracted premises |
| **Timeline** | Months 6-12 |

### Experiment 5: Adversarial Robustness

| Parameter | Value |
|-----------|-------|
| **Objective** | Test system against gaming attempts |
| **Method** | Expert debaters craft deceptive arguments |
| **Success** | >80% detection of hidden contradictions |
| **Timeline** | Months 18-24 |

---

## Data Collection Checklist

- [ ] Startup pitch decks (1,000+ documents from public repositories)
- [ ] Corporate strategy documents (S-1 filings, annual reports, investor letters)
- [ ] Product launch arguments (press releases, keynote transcripts)
- [ ] Societal premises corpus (constitutions, UN declarations, legal decisions)
- [ ] Expert annotations (5-dimension scoring, 3 annotators per document)
- [ ] Historical outcome data (5-year survival, revenue, market presence)

---

## Annotation Protocol

Score each argument on 5 dimensions (1-7 scale):

1. **Logical consistency** — Are there explicit contradictions?
2. **Premise-conclusion support** — Do premises actually support conclusions?
3. **Completeness** — Are there missing reasoning steps?
4. **Relevance** — Are all premises relevant to the conclusion?
5. **Overall coherence** — Holistic judgment of argument quality

Measure inter-annotator agreement with Krippendorff's alpha (target: α > 0.7).

---

## Technology Stack

| Component | Recommended Tool | Alternative |
|-----------|-----------------|-------------|
| NLI model | DeBERTa-v3-large-mnli-fever-anli | RoBERTa-large-mnli |
| Sentence embeddings | Sentence-BERT (all-MiniLM-L6-v2) | InstructOR, OpenAI |
| SAT solver | CaDiCaL | MiniSat |
| SMT solver | Z3 | cvc5 |
| Graph analysis | NetworkX | igraph |
| Bayesian networks | pgmpy | bnlearn |
| Compression | zlib/gzip (Python) | lzma |
| LLM judge | GPT-4 / Claude with CoT | Open-source alternatives |
| Argument mining | Fine-tuned transformer | GPT-4 few-shot |

---

## Key References by Domain

**Formal Logic:** Cook-Levin theorem; Godel's completeness/incompleteness; DPLL/CDCL algorithms

**Paraconsistent Logic:** Priest (LP, 1979); Da Costa (Cn systems); Anderson & Belnap (relevant logic)

**Argumentation Theory:** Dung (1995); Modgil & Prakken (ASPIC+); Cayrol & Lagasquie-Schiex (BAF)

**Coherence Measures:** Shogenji; Olsson; Fitelson; Roche/Douven-Meijs; Thagard (ECHO)

**NLI/Embeddings:** SNLI/MultiNLI/ANLI datasets; DeBERTa; Sentence-BERT; Linear Representation Hypothesis (Park et al. 2024)

**Information Theory:** Shannon entropy; Kolmogorov complexity; compression-based similarity

**Experimental Design:** Prediction markets (Hayek/Arrow); Delphi method; A/B testing frameworks

---

*This document is a quick reference companion to the full Research Framework (DOCX), the Formal Mathematical Framework (PDF), and the Beginner's Guide (DOCX).*

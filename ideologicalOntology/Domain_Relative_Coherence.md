# Domain-Relative Coherence: An Alternative to Societal-Premise Comparison

## The Problem with the Current Approach

The Coherence Engine's comparative analysis pipeline currently works like this: take a product's argumentative structure, take society's premises, measure how coherent the product is against those premises. The Quintin Hypothesis predicts that if a product is more internally coherent *and* more coherent with society's operative beliefs, it will win.

But we've documented a fundamental problem: society's own premises are incoherent. The 47-premise database scores 0.321 overall coherence with 12 cross-domain tensions and numerous systemic contradictions. We're measuring against a broken yardstick. An argument that is perfectly coherent with one societal premise (individual sovereignty) will necessarily conflict with another (collective welfare). This isn't a data quality issue — it reflects the genuine structure of liberal democratic thought, which *balances* competing values rather than resolving them.

This raises the question: is comparison against society's premises even the right test?

## The Alternative: Domain-Relative Coherence Superiority

Instead of asking "is this argument coherent with what society believes?", we ask: **"within the domain this argument operates in, is it more coherent than the existing body of thought?"**

This reframing has several immediate advantages:

**It dissolves the incoherence problem.** We no longer need society's premises to be coherent. We need the *domain's* premises to be identifiable — and domains, being narrower, are more likely to have a coherent internal structure. Market economics premises form a more coherent set than "all of Western liberal democratic thought."

**It matches how intellectual progress actually works.** Darwin didn't beat "all of philosophy." He beat the existing explanations in biology. A new product doesn't need to be more coherent than the entirety of social thought — it needs to be more coherent than the existing solutions in its space.

**It makes the Quintin Hypothesis testable at a finer grain.** Instead of one global coherence comparison, you get per-domain coherence rankings. A product could be highly coherent in its technical domain but incoherent in its ethical domain. That's a more useful signal than a single aggregate score.

**It handles cultural relativity naturally.** You don't need Hofstede dimension adjustments if you're comparing within a domain rather than against universal premises. The domain itself is culturally situated.

But it transfers the hard problem: **how do you determine the domain?**

## What Is a Domain?

This turns out to be a deeper question than it first appears. "Domain" can mean at least five different things, each with different measurement implications:

### 1. Topical Domain: What is this about?

The simplest reading. An argument about autonomous vehicles belongs to the "transportation technology" domain. You could detect this with topic modeling (BERTopic, LDA) or keyword classification.

The problem: topical similarity doesn't capture argumentative structure. Two arguments about healthcare — one libertarian, one socialist — share a topic but inhabit fundamentally different argumentative domains. They invoke different premises, use different standards of evidence, and reach different conclusions. Measuring coherence within "healthcare" would lump them together, defeating the purpose.

### 2. Epistemic Domain: What kind of knowledge claim is this?

Different domains have different standards for what counts as evidence, proof, and justified belief. Physics uses mathematical formalization and controlled experiment. Law uses precedent and statutory interpretation. Ethics uses thought experiments and reflective equilibrium. Medicine uses randomized controlled trials and meta-analysis.

This is closer to what matters for coherence. An argument that uses the right *type* of reasoning for its domain is epistemically well-situated. An argument that uses legal precedent to settle a physics question is incoherent *because it's in the wrong epistemic mode*, not because it reaches the wrong conclusion.

Detecting epistemic domain means detecting the *argument schemes* in use — the patterns of reasoning, not just the vocabulary. Douglas Walton catalogued 96 argument schemes (appeal to authority, causal reasoning, abductive inference, etc.). Different domains preferentially use different schemes. If you could profile an argument's scheme distribution, you'd have an epistemic fingerprint.

This is computationally feasible but underdeveloped. No published study has empirically validated that scheme distributions meaningfully differ across domains, though the theoretical basis is strong.

### 3. Normative Domain: What values framework does this invoke?

Many arguments — especially the kind products make — are normative. They say "this is good" or "this should happen." Normative claims presuppose a values framework: utilitarian, deontological, virtue-based, rights-based, etc.

Two arguments can share a topic and epistemic mode but inhabit different normative domains. A utilitarian argument for surveillance ("maximizes aggregate safety") and a rights-based argument against it ("violates individual privacy") are in the same topical domain but different normative ones.

For the Coherence Engine, this matters enormously. A product's normative domain determines which premises it's implicitly invoking. If you can detect the normative framework, you know which subset of societal premises to compare against — and the comparison becomes meaningful because you're comparing within a coherent normative tradition rather than against all of society.

Detection approach: normative language markers ("should," "ought," "right to," "greatest good"), combined with the premises the argument actually invokes. The existing `HeuristicPremiseExtractor` already captures some of this.

### 4. Ontological Domain: What entities does this assume exist?

Following Quine: a theory's domain is defined by what it's ontologically committed to — what entities its variables must range over. Physics is committed to particles and fields. Economics is committed to rational agents and utility functions. Law is committed to persons, rights, and obligations.

This is perhaps the deepest definition of domain. If two arguments share ontological commitments (they both assume "markets" are real entities with causal powers), they're in the same domain *regardless* of whether they agree on conclusions.

Computationally, this means ontology extraction: identifying the core entities an argument presupposes. This connects directly to the Coherence Engine's existing `OntologicalMapper`, which builds graphs of claims and their relationships. The entities in those graphs *are* the ontological commitments.

The limitation: ontology extraction from natural language is hard and ambiguous. The same entity can be described in many ways, and the distinction between "mentioning" an entity and "being ontologically committed to it" requires deep understanding.

### 5. Functional Domain: What problem is this trying to solve?

The most pragmatic definition. A product's domain is defined by what it does. Uber's domain isn't "transportation philosophy" — it's "getting from A to B efficiently." This functional framing determines the relevant comparison set: other solutions to the same problem.

This is the easiest to operationalize (just ask "what does this product do?") but the least philosophically grounded. Two products can solve the same problem using radically different argumentative frameworks. Netflix and a public library both solve "how do I watch movies?" but their operative premises are completely different.

## The Deep Insight: Domain as Emergent Property

Here's where it gets interesting. A domain might not be a pre-existing category that an argument *falls into*. It might be an emergent property of the argument's own structure.

Consider: an argument *creates* its domain by the premises it invokes, the inference patterns it uses, the entities it presupposes, and the standards of evidence it appeals to. When someone argues "autonomous vehicles should minimize total harm in unavoidable accidents," they're simultaneously operating in automotive engineering (topical), consequentialist ethics (normative), trolley-problem philosophy (epistemic), and a world containing moral agents with quantifiable welfare (ontological). The *combination* of these commitments defines a unique argumentative space.

This is reminiscent of Wittgenstein's "language games" — the idea that meaning arises from use within a bounded system of rules. Each discourse community plays its own game with its own rules. You don't understand a domain by listing its topics; you understand it by learning to play its game.

It's also related to Kuhn's paradigms: a paradigm isn't just a set of beliefs but a way of seeing the world, including what counts as a problem, what counts as a solution, and what tools are legitimate. The "domain" of Newtonian mechanics isn't "physics about forces" — it's the entire framework of assumptions, methods, and standards that practitioners share.

If domains are emergent, then measuring them requires a different approach than classification. You can't assign an argument to a pre-existing domain category. You have to *reconstruct* the domain from the argument's own structure.

## Seven Approaches to Domain Measurement

Given this analysis, here are seven approaches to measuring an argument's domain, ordered from most shallow to most deep:

### Approach 1: Topical Embedding Neighborhoods

**Method:** Embed the argument's claims using a sentence transformer (all-mpnet-base-v2). Find the nearest existing arguments in embedding space. The domain is the neighborhood.

**Strengths:** Simple, fast, leverages the Coherence Engine's existing embedding infrastructure. The comparison set emerges naturally from similarity.

**Weaknesses:** Captures vocabulary similarity, not argumentative structure. The "nearest neighbors" might include arguments that use the same words but reason completely differently.

**Implementation:** Already partially built. The `EmbeddingClusterExtractor` does agglomerative clustering of sentences — a domain detection mode could cluster *arguments* rather than sentences.

### Approach 2: BERTopic Domain Profiling

**Method:** Run BERTopic on a large corpus of arguments to discover latent topic clusters. Each cluster is a candidate domain. New arguments are assigned to topics based on embedding similarity.

**Strengths:** Discovers domains empirically rather than prescribing them. Handles novel domains that don't fit the existing 10-domain taxonomy. Scalable to large corpora.

**Weaknesses:** Topics ≠ argumentative domains. Two BERTopic clusters about "healthcare" might actually contain very different argumentative structures. Requires a large, diverse corpus of arguments to train on.

**Implementation:** Would require BERTopic integration and a training corpus. Medium effort.

### Approach 3: Argument Scheme Fingerprinting

**Method:** Classify the argument schemes used in a text (appeal to authority, causal reasoning, analogy, etc.). The distribution of schemes is an "argumentative fingerprint." Arguments with similar fingerprints belong to the same epistemic domain.

**Strengths:** Captures *how* an argument reasons, not just *what* it's about. Two healthcare arguments using different schemes would correctly be placed in different domains. This is the closest to measuring argumentative structure directly.

**Weaknesses:** Scheme detection is an unsolved NLP problem. Annotation is expensive, inter-annotator agreement is moderate, and no large-scale scheme-labeled corpus exists. Neural models can learn scheme-like patterns but don't explicitly model them.

**Implementation:** Would require building a scheme classifier, potentially fine-tuning on annotated argument data. High effort, high reward.

### Approach 4: Ontological Commitment Extraction

**Method:** Extract the core entities an argument presupposes (rights, markets, welfare, efficiency, persons, etc.). Arguments sharing ontological commitments belong to the same domain.

**Strengths:** Philosophically deep. Gets at the fundamental assumptions rather than surface features. Two arguments about completely different topics could be in the same domain if they share ontological commitments (e.g., both presuppose rational actors).

**Weaknesses:** Hard to extract computationally. The distinction between "mentioning" and "being committed to" requires deep understanding. No established NLP pipeline for this.

**Implementation:** Could leverage the existing `OntologicalMapper` to extract entity graphs, then compare graphs for structural similarity. The entities in the Coherence Engine's ontology *are* the ontological commitments. Medium-high effort.

### Approach 5: Premise Overlap Analysis

**Method:** Extract the premises of both the target argument and a corpus of reference arguments. The domain is defined by shared premises. If argument A and argument B both invoke "individual autonomy" and "informed consent," they're in the same normative domain — even if one is about healthcare and the other about data privacy.

**Strengths:** Directly uses the Coherence Engine's core capability (premise extraction). The comparison is at the level of *what's assumed*, not *what's discussed*. This naturally handles cross-topical domains (an argument about privacy and an argument about bodily autonomy share a premise domain even though they have different topics).

**Weaknesses:** Premise extraction quality limits domain detection quality. Implicit premises (never stated but assumed) are the hardest to extract and the most important for domain detection.

**Implementation:** The `EnsemblePremiseExtractor` already extracts premises from text. A domain detection mode would compare extracted premises across arguments using embedding similarity. Low-medium effort, leveraging existing infrastructure.

### Approach 6: Citation/Discourse Network Analysis

**Method:** Build a citation or reference network from a corpus. Arguments that cite the same sources, or are cited together, belong to the same intellectual domain. Cluster the network; each cluster is a domain.

**Strengths:** Empirically grounded — actual intellectual communities, not inferred ones. Well-validated in bibliometrics. Reveals domain boundaries that might not be obvious from text alone.

**Weaknesses:** Requires citation data, which most product arguments don't have. Works for academic or legal texts but not for marketing copy or product descriptions. Also, citation patterns lag behind intellectual change.

**Implementation:** Applicable to the Coherence Engine when analyzing academic or policy texts. Not applicable to product analysis. Narrow use case.

### Approach 7: Hybrid Domain Reconstruction

**Method:** Combine multiple signals — topic (what's discussed), scheme (how it's argued), premises (what's assumed), entities (what exists) — into a multi-dimensional domain representation. An argument's domain is a point in this multi-dimensional space, and the "comparison set" for coherence measurement is the neighborhood in that space.

**Strengths:** Most complete representation of domain. Handles the fact that real arguments operate across multiple domain dimensions simultaneously. Avoids the reductionism of any single approach.

**Weaknesses:** Complex to implement. Requires weighting the different signals. The dimensionality of the representation needs careful design.

**Implementation:** This is the recommended approach for the Coherence Engine. Each dimension builds on existing infrastructure:
- Topic → embedding clusters (existing)
- Premises → EnsemblePremiseExtractor (existing)
- Entities → OntologicalMapper (existing)
- Schemes → new development needed
- Normative framework → partially captured by premise extraction

## The Domain-Relative Coherence Test

If we can measure domains, the new coherence test works like this:

**Step 1: Domain Reconstruction.** Given an argument, reconstruct its domain using the hybrid approach — extract its topics, premises, entities, and reasoning patterns.

**Step 2: Comparison Set Discovery.** Find the existing body of thought that occupies the same domain region. This is the "incumbent" — the set of arguments, theories, and positions that the new argument is challenging.

**Step 3: Coherence Measurement.** Apply the Coherence Engine's multi-method coherence analysis (pairwise, graph-theoretic, spectral, compression, systemic tension) to both the new argument and the incumbent body.

**Step 4: Superiority Test.** If the new argument is more internally coherent than the incumbent body *within their shared domain*, it passes the coherence superiority test. The Quintin Hypothesis predicts that, all else equal, it will eventually prevail.

This is a fundamentally different test than "is this argument coherent with society's premises?" It's asking "is this argument a better-organized version of ideas in its space?" — which is much closer to how intellectual and market competition actually works.

## What This Changes About the Coherence Engine

If we adopt domain-relative coherence, several things change:

**The societal premises database becomes a domain map rather than a comparison baseline.** The 47 premises across 10 domains aren't the yardstick — they're the landscape. They tell us what domains look like, not what arguments should conform to.

**The comparative analysis pipeline shifts from conformity testing to superiority testing.** Instead of "how well does this product align with society?", it asks "is this product more coherent than its competition within its domain?" This is arguably a more useful business question anyway.

**Cross-domain tensions become features, not bugs.** When an argument operates at the intersection of two domains with known tensions (individual rights vs. collective welfare), the system can identify that the argument is attempting something inherently difficult — resolving a known tension — and score it accordingly. An argument that successfully resolves a cross-domain tension is more impressive than one that stays safely within a single domain.

**The Quintin Hypothesis becomes more precise.** Instead of "coherence implies truth," it becomes "within a domain, the most internally coherent position tends to prevail." This is both more testable and more defensible.

## Open Questions

**Can domains be measured well enough for this to work?** The hybrid approach is theoretically sound but requires significant new engineering. The scheme detection component alone is an open research problem.

**What if the domain is gerrymandered?** If you get to choose your domain, you can choose one where you look coherent. A creationist arguing about "intelligent design" looks coherent within the domain of design teleology but incoherent within biology. The domain reconstruction method must be robust against self-serving domain definitions — the domain must emerge from the argument's actual structure, not from the arguer's preferred framing.

**How large must the comparison set be?** If only three arguments exist in a domain, "coherence superiority" over a small set isn't very meaningful. There may be a minimum corpus size below which domain-relative comparison degenerates.

**Does coherence superiority actually predict success?** This is the empirical question at the heart of the Quintin Hypothesis. Even with better domain measurement, the hypothesis needs to be tested against real outcomes — product success, theory adoption, policy change.

**What about arguments that deliberately create new domains?** The most revolutionary ideas (Copernicus, Darwin, Einstein) don't just win within an existing domain — they redefine the domain entirely. A truly novel product might not have a meaningful comparison set because nothing like it existed before. How does the coherence superiority test handle domain creation?

## Recommended Next Steps

1. **Implement Approach 5 (Premise Overlap Analysis)** as the fastest path to domain detection, since it leverages existing infrastructure.

2. **Build a prototype domain detector** that combines embedding neighborhoods (Approach 1) with premise overlap (Approach 5) and entity extraction from the OntologicalMapper (Approach 4).

3. **Modify the comparative analysis pipeline** to support domain-relative comparison alongside the existing societal-premise comparison.

4. **Design an experiment** to test whether domain-relative coherence superiority predicts outcomes better than societal-premise comparison.

5. **Investigate argument scheme detection** as a longer-term investment in Approach 3.

---

*Research note: This document explores the conceptual foundations for domain-relative coherence testing. The approaches described draw on Wittgenstein's language games, Kuhn's paradigms, Walton's argument schemes, Quine's ontological commitments, and recent computational work in topic modeling (BERTopic), citation network analysis, and argument mining. Key references: Walton (2008) Argumentation Schemes; Kuhn (1962) Structure of Scientific Revolutions; Haas (1992) epistemic communities; Hamilton et al. (2016) diachronic embeddings; Lawrence & Reed (2020) argument mining survey.*

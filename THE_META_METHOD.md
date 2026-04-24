# The Meta-Method: Theseus as a Theory of Inquiry

## The Three Orders

The firm has moved through three levels of abstraction. Each is a genuine advance, and it's worth being precise about why.

**First order — Substantive claims.** "We believe X is true." This is where most firms, thinkers, and investors operate. The product is a claim about the world. The vulnerability is obvious: if X turns out to be false, the entire edifice collapses. A fund that bets on a thesis is only as good as the thesis.

**Second order — Methodology.** "We have a method for determining whether X is true." This is stronger. The product is not a specific claim but a procedure — a coherence engine, a contradiction detector, an adversarial generator. If X turns out to be false, the method catches it. The vulnerability here is subtler: the method itself might be unreliable. A coherence engine that mismeasures coherence is worse than useless; it's confidently wrong.

**Third order — Meta-methodology.** "We have a theory of what makes a method reliable, and we can evaluate competing methods by this theory." This is what the firm is now reaching for. The product is not a claim or a method but a *criterion for evaluating methods*. The question is no longer "which path through the maze?" or "which pathfinding algorithm?" but "what formal properties must a pathfinding algorithm possess in order to be reliable, and how do we determine this for any given maze?"

This third order is where the deepest intellectual action is.

---

## The Maze Analogy, Extended

Consider four agents trying to navigate a maze:

1. **The Dogmatist** knows the path. "Turn left, then right, then left." If the maze changes, the dogmatist walks into walls.

2. **The Methodologist** has an algorithm. "At each fork, always turn toward the exit's general direction." This works for many mazes but fails for mazes where the direct path leads to dead ends.

3. **The Meta-Methodologist** evaluates algorithms. "A* search with admissible heuristics is provably optimal for shortest-path problems in known environments. But in partially observable environments, POMDP-based planning outperforms A*. The choice of algorithm depends on the structure of the maze." This agent doesn't commit to one algorithm; it knows which algorithm to deploy under which conditions.

4. **The Theorist of Inquiry** (where Theseus is heading) asks: "What formal properties must ANY reliable pathfinding algorithm have, regardless of the maze? And what determines which properties are necessary for which class of mazes?"

The No Free Lunch theorems tell us that agent 4 cannot discover a universally optimal algorithm — no such thing exists. But NFL doesn't say all algorithms are equal *on a given problem class*. Agent 4's contribution is the **mapping**: for each class of maze (and by analogy, each class of problem the firm encounters), identify which properties a method must have to be reliable.

This mapping IS Theseus's intellectual product.

---

## Five Criteria for Evaluating Methods

Drawing on the research traditions of Lakatos, Laudan, Mayo, Solomonoff, and the NFL theorems, here are five formal properties that a reliable truth-finding method should possess. These are the criteria by which Theseus evaluates any methodology — its own or anyone else's.

### 1. Progressivity (Lakatos)

A method is progressive if it generates novel, testable predictions that go beyond what motivated the method. A method is degenerating if it only produces post-hoc explanations of what's already known.

**Test:** Given the firm's investing methodology, does it predict things that would be surprising if true — and do some of those predictions come true? Or does it only explain past successes?

**Why this matters:** Degenerating methods feel productive because they explain everything. But explanation without prediction is unfalsifiable, and unfalsifiable methods are epistemically worthless. The distinction between genuine insight and post-hoc rationalization is progressivity.

### 2. Severity (Mayo)

A method provides severe evidence for a claim only if the method would very probably have detected the claim's falsity, had the claim been false. A test that would pass any reasonable hypothesis is non-severe.

**Test:** When the firm concludes "company X has a durable moat," has the analysis been conducted in a way that *would have detected* the absence of a moat? Or was the analysis structured such that any company would have passed?

**Why this matters:** Most analysis is non-severe. People look for confirming evidence, find it (it's always there), and conclude they have support. Severity inverts this: you must show that your method would have rejected the claim under plausible alternative scenarios. This is the computational version of steelmanning.

### 3. Coherence Across Aims-Methods-Theories (Laudan)

A method is rational only if it is coherent with the aims it serves and the theoretical framework it operates within. Misalignment between aims, methods, and theories signals irrationality.

**Test:** Is the firm's methodology aligned with its aims? If the aim is "identify companies with durable competitive advantages," but the method is "compare P/E ratios to sector averages," there is a coherence failure — the method doesn't address the aim.

**Why this matters:** Laudan's reticulated model shows that methods don't stand alone. A method that's excellent for one aim may be useless for another. Meta-methodology requires checking not just "is the method good?" but "is the method good *for what we're trying to do*?"

### 4. Compressibility (Solomonoff / Kolmogorov)

The best explanation is the shortest one that generates all the observed data. A method that requires many ad hoc parameters to fit the data is worse than one that fits the data with fewer assumptions.

**Test:** Does the firm's thesis require many special assumptions ("this time is different because of factors A, B, C, D, E"), or does it follow from a small number of general principles? The more assumptions required, the less compressible the explanation, and the less likely it is to generalize.

**Why this matters:** Kolmogorov complexity is the theoretical ideal of inference. In practice, it manifests as Occam's razor — but with a formal foundation. It also connects directly to the information-theoretic layer (Layer 5) of the coherence engine: compression coherence measures exactly this.

### 5. Domain Sensitivity (NFL Theorems)

No method is universally optimal. A method's reliability is always relative to a problem class. A good meta-methodology maps methods to their domains of reliability.

**Test:** Does the firm know the *boundaries* of its methodology? Where does it work and where does it fail? Is the firm as precise about its method's failure modes as about its successes?

**Why this matters:** The most dangerous methodological failure is applying a method outside its domain of reliability. Value investing in tech stocks. Statistical models in fat-tailed environments. Analogical reasoning across structurally dissimilar domains. The meta-methodologist knows that every method has a domain, and maps those boundaries explicitly.

---

## How the Faculties Instantiate the Meta-Method

Each of Theseus's faculties is a domain — a class of maze — through which the meta-method operates. The firm's contribution is not to tell each faculty *what to conclude* or even *how to investigate*, but to establish the meta-criteria above as the standard by which all methodologies within the firm are evaluated.

### Investing
The firm doesn't invest based on a specific thesis ("AI will be transformative"). It invests based on *methodological quality* — selecting companies and founders whose reasoning methods score high on the five criteria. A founder whose thesis is progressive, severely tested, coherent with their stated aims, compressible, and domain-sensitive is a better investment than one with a "right" thesis arrived at through poor methodology.

### Media (Podcast / Blog / Essays)
The media arm doesn't communicate specific truths ("here's what we think about X"). It communicates *how to think about X* — modeling the meta-method in public. Each podcast episode is an exhibition of rigorous methodology: making axioms explicit, generating counter-arguments, specifying falsification conditions, acknowledging domain boundaries.

### Research
The research arm doesn't pursue specific findings ("prove that X is true"). It pursues *methodological advances* — new and better methods for arriving at truth, and formal characterizations of when existing methods work and when they fail. The Embedding Geometry Conjecture is a research output of this kind: it's a methodological tool (contradiction detection), not a substantive claim.

### Writing / Publishing
The publishing arm doesn't produce books of claims. It produces books of method — how to think, how to evaluate arguments, how to identify hidden assumptions, how to detect one's own biases. The target output is something like Descartes' *Discourse on Method* or Pólya's *How to Solve It*: timeless works that teach thinking itself.

### Film (if pursued)
Film is the narrative instantiation of the meta-method — stories that dramatize the *process* of inquiry, not just the *results*. The hero's journey reimagined as an epistemological journey: from certainty through doubt through rigorous inquiry to justified belief.

### Open Source
The open-source arm publishes the tools themselves — the coherence engine, the contradiction detector, the adversarial generator, the calibration system. This is the most direct instantiation of the meta-method: making the methodology executable and available for anyone to use, test, and improve.

---

## The Deepest Question

There is a natural objection to meta-methodology: it's turtles all the way down. If you need a method to evaluate methods, don't you need a meta-meta-method to evaluate your meta-method?

The answer is no, and the reason is important. The meta-method is *self-applying*. You can evaluate the meta-method using its own criteria:

1. Is the meta-method **progressive**? Does it generate novel, testable predictions about which methodologies will succeed? Yes — it predicts that methodologically rigorous firms will outperform methodologically sloppy ones, and this is testable.

2. Is the meta-method **severe**? Could it detect its own failure? Yes — if methodologically rigorous firms consistently underperform, the meta-method fails its own severity test.

3. Is the meta-method **coherent** with its aims? Yes — the aim is to identify reliable methods, and the criteria (progressivity, severity, coherence, compressibility, domain sensitivity) are each independently validated by separate intellectual traditions.

4. Is the meta-method **compressible**? Yes — five criteria, each formally defined, derivable from a single principle: *a method is reliable to the extent that it would detect its own failure*.

5. Is the meta-method **domain-sensitive**? Yes — it explicitly acknowledges (via NFL) that no method is universal, and its primary output is the mapping from domain to method.

The regress terminates because the meta-method is a fixed point: it evaluates itself and passes.

This is the deepest thing Theseus can claim: not just that it has a good method, but that it has a method that can evaluate itself and survive the evaluation.

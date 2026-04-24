"""
EXPERIMENT: Testing the Quintin Embedding Geometry Conjecture with Real Models

CONJECTURE: "A contradiction between two statements manifests as a specific
geometric configuration — vectors pointing in incompatible directions."

This experiment uses real sentence embedding models to test whether
contradiction has a detectable geometric signature in embedding space.

REQUIREMENTS:
    pip install sentence-transformers numpy scipy scikit-learn matplotlib

RUNTIME: ~5-10 minutes on CPU (downloads model on first run)
"""

import numpy as np
from sentence_transformers import SentenceTransformer
from scipy.spatial.distance import cosine
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import cross_val_score, LeaveOneOut
from sklearn.decomposition import PCA
import json
import os
from itertools import combinations

# ============================================================================
# CONFIGURATION
# ============================================================================
MODEL_NAME = "all-MiniLM-L6-v2"  # Fast, 384-dim
# Alternative: "all-mpnet-base-v2"  # Slower, 768-dim, more accurate
# Alternative: "BAAI/bge-large-en-v1.5"  # Best quality, 1024-dim

OUTPUT_DIR = "results"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ============================================================================
# TEST DATASET
# ============================================================================
# Format: (premise, hypothesis, label)
# Carefully constructed to cover: direct negation, antonym substitution,
# quantifier contradiction, and domain-specific philosophical contradictions

test_data = [
    # --- DIRECT NEGATION ---
    ("The cat is on the mat.", "The cat is not on the mat.", "contradiction"),
    ("All humans are mortal.", "Some humans are immortal.", "contradiction"),
    ("The store is open.", "The store is closed.", "contradiction"),
    ("Water boils at 100 degrees Celsius.", "Water boils at 50 degrees Celsius.", "contradiction"),
    ("The company is profitable.", "The company is losing money.", "contradiction"),
    ("She arrived early.", "She arrived late.", "contradiction"),
    ("The experiment succeeded.", "The experiment failed.", "contradiction"),
    ("Democracy promotes freedom.", "Democracy suppresses freedom.", "contradiction"),
    ("Innovation drives economic growth.", "Innovation hinders economic growth.", "contradiction"),
    ("Competition improves quality.", "Competition degrades quality.", "contradiction"),

    # --- PHILOSOPHICAL/BUSINESS CONTRADICTIONS (domain-specific) ---
    ("Free markets allocate resources efficiently.", "Free markets waste resources systematically.", "contradiction"),
    ("Entrepreneurs create value through invention.", "Entrepreneurs destroy value through invention.", "contradiction"),
    ("Small firms coordinate better than large ones.", "Large firms coordinate better than small ones.", "contradiction"),
    ("Mimicry leads to purposelessness.", "Mimicry leads to renewed purpose.", "contradiction"),
    ("Capitalism rewards coherent arguments.", "Capitalism punishes coherent arguments.", "contradiction"),
    ("Logical coherence predicts business durability.", "Logical coherence is irrelevant to business durability.", "contradiction"),
    ("Persuasion is the mechanism of value creation.", "Persuasion has nothing to do with value creation.", "contradiction"),
    ("Purpose drives long-term efficiency.", "Purpose is orthogonal to efficiency.", "contradiction"),
    ("Institutional design should be amoral.", "Institutional design must be fundamentally moral.", "contradiction"),
    ("One-person firms represent the future of work.", "One-person firms are economically unviable.", "contradiction"),

    # --- ENTAILMENTS ---
    ("The cat is on the mat.", "There is a cat somewhere.", "entailment"),
    ("All humans are mortal.", "Socrates, being human, is mortal.", "entailment"),
    ("The store is open 24 hours.", "The store is open.", "entailment"),
    ("Water boils at 100 degrees Celsius at sea level.", "Water changes state at high temperatures.", "entailment"),
    ("The company made $10 million in profit.", "The company is profitable.", "entailment"),
    ("She arrived at 7am for the 9am meeting.", "She arrived early.", "entailment"),
    ("The experiment produced the predicted results.", "The experiment succeeded.", "entailment"),
    ("Citizens vote freely in elections.", "The country has democratic processes.", "entailment"),
    ("GDP grew 5% due to new technologies.", "Innovation contributed to economic growth.", "entailment"),
    ("Firms competed to offer the best product.", "Competition influenced product development.", "entailment"),
    ("Prices dropped as supply increased.", "Market mechanisms affected pricing.", "entailment"),
    ("The founder built a product that solved a real problem.", "The entrepreneur created something of value.", "entailment"),
    ("A team of five coordinated their product launch seamlessly.", "The small group worked together effectively.", "entailment"),
    ("Every competitor copied each other's features.", "The industry showed signs of mimicry.", "entailment"),
    ("Customers chose the product with the clearest value proposition.", "The market rewarded the strongest argument.", "entailment"),
    ("The business grew by serving its customers better than competitors.", "The firm succeeded by fulfilling its purpose.", "entailment"),
    ("The argument was internally consistent and well-structured.", "The argument exhibited logical coherence.", "entailment"),
    ("Workers in the startup felt connected to the company's mission.", "The small firm had strong organizational purpose.", "entailment"),
    ("The theory made accurate predictions about market behavior.", "The theoretical framework had empirical validity.", "entailment"),
    ("Capital flowed from less productive to more productive enterprises.", "The market allocated resources toward better arguments.", "entailment"),

    # --- NEUTRAL ---
    ("The cat is on the mat.", "The mat is blue.", "neutral"),
    ("All humans are mortal.", "The population of Earth is 8 billion.", "neutral"),
    ("The store is open.", "The store sells electronics.", "neutral"),
    ("Water boils at 100 degrees Celsius.", "Water is composed of hydrogen and oxygen.", "neutral"),
    ("The company is profitable.", "The company was founded in 2010.", "neutral"),
    ("She arrived early.", "She was wearing a red dress.", "neutral"),
    ("The experiment succeeded.", "The lab is located in Boston.", "neutral"),
    ("Democracy promotes freedom.", "Athens was the birthplace of democracy.", "neutral"),
    ("Innovation drives economic growth.", "Silicon Valley is in California.", "neutral"),
    ("Competition improves quality.", "There are many industries in the world.", "neutral"),
    ("Free markets allocate resources.", "Adam Smith wrote The Wealth of Nations.", "neutral"),
    ("Entrepreneurs create value.", "Entrepreneurship has a long history.", "neutral"),
    ("Small firms coordinate well.", "There are millions of small businesses.", "neutral"),
    ("Mimicry is common in industries.", "Industries exist in every country.", "neutral"),
    ("Capitalism rewards arguments.", "Economics is studied in universities.", "neutral"),
    ("Logical coherence matters in philosophy.", "Philosophy departments exist at many universities.", "neutral"),
    ("Persuasion plays a role in markets.", "Markets have existed for thousands of years.", "neutral"),
    ("Purpose is important for organizations.", "Organizations come in many sizes.", "neutral"),
    ("Institutional design affects outcomes.", "Institutions have existed since ancient times.", "neutral"),
    ("Technology enables one-person firms.", "Technology advances rapidly.", "neutral"),
]

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def cosine_sim(a, b):
    return float(1 - cosine(a, b))

def hoyer_sparsity(v):
    n = len(v)
    l1 = np.sum(np.abs(v))
    l2 = np.sqrt(np.sum(v**2))
    if l2 == 0: return 0.0
    return float((np.sqrt(n) - l1/l2) / (np.sqrt(n) - 1))

def pair_features(p, h):
    diff = h - p
    product = p * h
    abs_diff = np.abs(diff)
    return np.concatenate([diff, product, abs_diff])

# ============================================================================
# MAIN EXPERIMENT
# ============================================================================

def run_experiment():
    print("=" * 80)
    print(f"QUINTIN CONJECTURE EXPERIMENT — Model: {MODEL_NAME}")
    print("=" * 80)

    # Load model
    print(f"\nLoading model {MODEL_NAME}...")
    model = SentenceTransformer(MODEL_NAME)
    dim = model.get_sentence_embedding_dimension()
    print(f"Embedding dimension: {dim}")

    # Encode all statements
    print("Encoding statements...")
    embeddings = {}
    for premise, hypothesis, label in test_data:
        if premise not in embeddings:
            embeddings[premise] = model.encode(premise)
        if hypothesis not in embeddings:
            embeddings[hypothesis] = model.encode(hypothesis)

    results = {}

    # ------------------------------------------------------------------
    # TEST 1: COSINE SIMILARITY DISTRIBUTIONS
    # ------------------------------------------------------------------
    print("\n" + "-" * 60)
    print("TEST 1: COSINE SIMILARITY BY RELATIONSHIP TYPE")
    print("-" * 60)

    cos_by_type = {"contradiction": [], "entailment": [], "neutral": []}
    for premise, hypothesis, label in test_data:
        sim = cosine_sim(embeddings[premise], embeddings[hypothesis])
        cos_by_type[label].append(sim)

    for label in ["entailment", "neutral", "contradiction"]:
        vals = cos_by_type[label]
        print(f"  {label:>15}: mean={np.mean(vals):.4f}, std={np.std(vals):.4f}")

    results["cosine_similarity"] = {k: {"mean": float(np.mean(v)), "std": float(np.std(v))}
                                     for k, v in cos_by_type.items()}

    # ------------------------------------------------------------------
    # TEST 2: DIFFERENCE VECTOR SPARSITY
    # ------------------------------------------------------------------
    print("\n" + "-" * 60)
    print("TEST 2: DIFFERENCE VECTOR SPARSITY (HOYER)")
    print("-" * 60)

    diff_data = {"contradiction": [], "entailment": [], "neutral": []}
    sparsity_data = {"contradiction": [], "entailment": [], "neutral": []}

    for premise, hypothesis, label in test_data:
        diff = embeddings[hypothesis] - embeddings[premise]
        diff_data[label].append(diff)
        sparsity_data[label].append(hoyer_sparsity(diff))

    for label in ["entailment", "neutral", "contradiction"]:
        vals = sparsity_data[label]
        print(f"  {label:>15} sparsity: mean={np.mean(vals):.4f}, std={np.std(vals):.4f}")

    results["sparsity"] = {k: {"mean": float(np.mean(v)), "std": float(np.std(v))}
                           for k, v in sparsity_data.items()}

    # ------------------------------------------------------------------
    # TEST 3: SELF-CONSISTENCY OF CONTRADICTION DIRECTION
    # ------------------------------------------------------------------
    print("\n" + "-" * 60)
    print("TEST 3: SELF-CONSISTENCY OF DIFFERENCE VECTORS")
    print("-" * 60)

    for label in ["contradiction", "entailment", "neutral"]:
        diffs = diff_data[label]
        self_sims = [cosine_sim(diffs[i], diffs[j])
                     for i, j in combinations(range(len(diffs)), 2)]
        print(f"  {label:>15} self-sim: mean={np.mean(self_sims):.4f}")

    # ------------------------------------------------------------------
    # TEST 4: LINEAR SEPARABILITY
    # ------------------------------------------------------------------
    print("\n" + "-" * 60)
    print("TEST 4: LINEAR SEPARABILITY (CROSS-VALIDATED)")
    print("-" * 60)

    X = []
    y = []
    label_map = {"contradiction": 0, "entailment": 1, "neutral": 2}
    for premise, hypothesis, label in test_data:
        features = pair_features(embeddings[premise], embeddings[hypothesis])
        X.append(features)
        y.append(label_map[label])

    X = np.array(X)
    y = np.array(y)

    clf = LogisticRegression(max_iter=2000, multi_class='multinomial', C=0.1)
    scores = cross_val_score(clf, X, y, cv=5, scoring='accuracy')
    print(f"  5-fold CV accuracy: {np.mean(scores):.4f} (+/- {np.std(scores):.4f})")

    clf.fit(X, y)
    y_pred = clf.predict(X)
    print(f"  Training accuracy:  {accuracy_score(y, y_pred):.4f}")
    print(f"\n  Classification Report:")
    print(classification_report(y, y_pred, target_names=["contradiction", "entailment", "neutral"],
                                indent=4))

    results["linear_separability"] = {
        "cv_accuracy_mean": float(np.mean(scores)),
        "cv_accuracy_std": float(np.std(scores)),
        "training_accuracy": float(accuracy_score(y, y_pred))
    }

    # ------------------------------------------------------------------
    # TEST 5: PCA OF DIFFERENCE VECTORS
    # ------------------------------------------------------------------
    print("-" * 60)
    print("TEST 5: PCA OF DIFFERENCE VECTORS")
    print("-" * 60)

    all_diffs = np.array([d for diffs in diff_data.values() for d in diffs])
    all_labels = ([0]*len(diff_data["contradiction"]) +
                  [1]*len(diff_data["entailment"]) +
                  [2]*len(diff_data["neutral"]))

    pca = PCA(n_components=min(20, len(all_diffs)-1))
    X_pca = pca.fit_transform(all_diffs)

    cumvar = np.cumsum(pca.explained_variance_ratio_)
    for n in [1, 3, 5, 10]:
        if n <= len(cumvar):
            print(f"  Top {n:>2} components explain: {cumvar[n-1]*100:.1f}% of variance")

    # Centroid distances in PCA space
    for name, idx in [("Contradiction", 0), ("Entailment", 1), ("Neutral", 2)]:
        mask = np.array(all_labels) == idx
        centroid = X_pca[mask].mean(axis=0)[:3]
        print(f"  {name:>15} centroid (PC1-3): [{centroid[0]:+.3f}, {centroid[1]:+.3f}, {centroid[2]:+.3f}]")

    # ------------------------------------------------------------------
    # TEST 6: DIMENSION CONCENTRATION
    # ------------------------------------------------------------------
    print("\n" + "-" * 60)
    print("TEST 6: SIGNAL CONCENTRATION (WHICH DIMENSIONS MATTER)")
    print("-" * 60)

    contra_mean = np.mean(diff_data["contradiction"], axis=0)
    entail_mean = np.mean(diff_data["entailment"], axis=0)
    dim_diffs = np.abs(contra_mean - entail_mean)
    sorted_diffs = np.sort(dim_diffs)[::-1]
    cumsum = np.cumsum(sorted_diffs) / np.sum(sorted_diffs)

    for pct in [0.5, 0.8, 0.9]:
        n = np.searchsorted(cumsum, pct) + 1
        print(f"  Dims for {pct*100:.0f}% of contra-entail signal: {n}/{dim} ({n/dim*100:.1f}%)")

    # ------------------------------------------------------------------
    # TEST 7: HARD CASES (MINIMAL PAIRS)
    # ------------------------------------------------------------------
    print("\n" + "-" * 60)
    print("TEST 7: HARD CASES — MINIMAL PAIRS")
    print("-" * 60)

    hard_pairs = [
        ("The defendant is guilty.", "The defendant is not guilty."),
        ("The policy will reduce inflation.", "The policy will not reduce inflation."),
        ("Capitalism creates inequality.", "Capitalism does not create inequality."),
        ("Free trade benefits all nations.", "Free trade does not benefit all nations."),
        ("The theory is internally coherent.", "The theory is internally incoherent."),
    ]

    print(f"  {'Premise':<42} {'Cos Sim':>8} {'Diff Sparsity':>14}")
    print("  " + "-" * 66)
    for p, c in hard_pairs:
        ep = model.encode(p)
        ec = model.encode(c)
        sim = cosine_sim(ep, ec)
        spar = hoyer_sparsity(ec - ep)
        print(f"  {p[:41]:<42} {sim:>8.4f} {spar:>14.4f}")

    # ------------------------------------------------------------------
    # SAVE RESULTS
    # ------------------------------------------------------------------
    with open(os.path.join(OUTPUT_DIR, "results.json"), "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {OUTPUT_DIR}/results.json")

    # ------------------------------------------------------------------
    # SYNTHESIS
    # ------------------------------------------------------------------
    print("\n" + "=" * 80)
    print("SYNTHESIS")
    print("=" * 80)

    contra_cos = results["cosine_similarity"]["contradiction"]["mean"]
    entail_cos = results["cosine_similarity"]["entailment"]["mean"]
    neutral_cos = results["cosine_similarity"]["neutral"]["mean"]

    print(f"""
    Cosine Similarity: Contradiction ({contra_cos:.3f}) vs Entailment ({entail_cos:.3f}) vs Neutral ({neutral_cos:.3f})

    If contra > neutral: Contradictions are CLOSER than unrelated pairs in raw space.
       -> Simple cosine distance CANNOT detect contradiction.
       -> The naive conjecture (opposite directions) is FALSE.

    Linear Separability: {results['linear_separability']['cv_accuracy_mean']:.1%} cross-validated accuracy
       -> If > 70%: The REFINED conjecture is SUPPORTED.
       -> Contradiction has a distinct geometric signature in feature space.

    Sparsity: Contradiction diffs ({results['sparsity']['contradiction']['mean']:.3f}) vs
              Entailment diffs ({results['sparsity']['entailment']['mean']:.3f})
       -> If contra > entail: The SparseCL insight holds — contradiction is SPARSE.
    """)

if __name__ == "__main__":
    run_experiment()

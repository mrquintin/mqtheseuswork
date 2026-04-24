"""
EXPERIMENT: Learning the Contradiction Direction in Embedding Space

Building on Marks & Tegmark (2023) "Geometry of Truth", this experiment
tests whether a single linear direction in embedding space separates
contradictory from non-contradictory sentence pairs.

KEY IDEA: If contradictions are geometrically structured, then there exists
a unit vector c_hat in R^d such that:
    d · c_hat > threshold  =>  contradiction
    d · c_hat < threshold  =>  not contradiction
where d = embed(B) - embed(A) is the difference vector.

This experiment:
1. Trains a linear probe to find c_hat
2. Tests generalization to unseen domains
3. Measures how many dimensions carry the contradiction signal
4. Compares cosine-only vs Hoyer-only vs combined detection
5. Tests robustness to paraphrasing and negation styles

REQUIREMENTS:
    pip install sentence-transformers numpy scipy scikit-learn matplotlib

RUNTIME: ~10 minutes on CPU
"""

import numpy as np
from sentence_transformers import SentenceTransformer
from scipy.spatial.distance import cosine
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, f1_score
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.decomposition import PCA
import json
import os
import matplotlib.pyplot as plt

# ============================================================================
# CONFIGURATION
# ============================================================================
MODEL_NAME = "all-MiniLM-L6-v2"
OUTPUT_DIR = "results_direction"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ============================================================================
# TRAINING DATASET - General domain
# ============================================================================
TRAIN_PAIRS = [
    # Contradictions
    ("The store is open today.", "The store is closed today.", "contradiction"),
    ("She passed the exam.", "She failed the exam.", "contradiction"),
    ("The project was completed on time.", "The project was delayed significantly.", "contradiction"),
    ("Revenue increased this quarter.", "Revenue declined this quarter.", "contradiction"),
    ("The team supports the proposal.", "The team opposes the proposal.", "contradiction"),
    ("Water freezes at zero degrees.", "Water remains liquid at zero degrees.", "contradiction"),
    ("The company is profitable.", "The company is losing money.", "contradiction"),
    ("He arrived early.", "He arrived late.", "contradiction"),
    ("The policy reduces inequality.", "The policy increases inequality.", "contradiction"),
    ("Demand is growing rapidly.", "Demand is shrinking rapidly.", "contradiction"),
    ("The experiment confirmed the hypothesis.", "The experiment refuted the hypothesis.", "contradiction"),
    ("Crime rates are falling.", "Crime rates are rising.", "contradiction"),
    ("The bridge is safe for traffic.", "The bridge is unsafe and structurally compromised.", "contradiction"),
    ("Inflation is under control.", "Inflation is spiraling out of control.", "contradiction"),
    ("The drug has no side effects.", "The drug causes severe side effects.", "contradiction"),

    # Entailments
    ("She won the gold medal.", "She competed in the competition.", "entailment"),
    ("The car crashed into a wall.", "The car was damaged.", "entailment"),
    ("He was born in Paris.", "He was born in France.", "entailment"),
    ("All mammals are warm-blooded.", "Dogs are warm-blooded.", "entailment"),
    ("The company went bankrupt.", "The company had financial problems.", "entailment"),
    ("It rained heavily all day.", "The ground was wet.", "entailment"),
    ("She is a physician.", "She has a medical degree.", "entailment"),
    ("The volcano erupted.", "There was a natural disaster.", "entailment"),
    ("He ran a marathon.", "He engaged in physical exercise.", "entailment"),
    ("The temperature reached 45 degrees.", "It was extremely hot.", "entailment"),
    ("She speaks five languages fluently.", "She is multilingual.", "entailment"),
    ("The factory was shut down by regulators.", "The factory stopped production.", "entailment"),
    ("He was sentenced to prison.", "He was found guilty.", "entailment"),
    ("The lake froze over.", "The temperature was below freezing.", "entailment"),
    ("She graduated summa cum laude.", "She performed well academically.", "entailment"),

    # Neutral
    ("The cat sat on the mat.", "The stock market rose today.", "neutral"),
    ("She enjoys reading novels.", "The weather was sunny.", "neutral"),
    ("The train departed at noon.", "Pizza is popular in Italy.", "neutral"),
    ("He studied mathematics.", "The garden needs watering.", "neutral"),
    ("The building has ten floors.", "She likes classical music.", "neutral"),
    ("The river flows eastward.", "The election results were surprising.", "neutral"),
    ("He owns a bicycle.", "The restaurant serves Italian food.", "neutral"),
    ("The library opens at nine.", "The mountain is covered in snow.", "neutral"),
    ("She works in marketing.", "The airplane landed safely.", "neutral"),
    ("The movie lasts two hours.", "Trees lose their leaves in autumn.", "neutral"),
    ("He plays the violin.", "The road was recently paved.", "neutral"),
    ("The conference starts Monday.", "Dolphins are highly intelligent.", "neutral"),
    ("She bought a new laptop.", "The river is polluted.", "neutral"),
    ("He teaches high school.", "The painting sold for millions.", "neutral"),
    ("The ship docked at port.", "She won the cooking competition.", "neutral"),
]

# ============================================================================
# TEST DATASET - Philosophy/Business domain (unseen during training)
# ============================================================================
TEST_PAIRS_PHILOSOPHY = [
    ("Value is determined by logical coherence.", "Value is arbitrary and unrelated to logic.", "contradiction"),
    ("Free markets allocate resources efficiently.", "Free markets lead to systematic misallocation.", "contradiction"),
    ("Rational agents maximize utility.", "Rational agents often act against their interests.", "contradiction"),
    ("Competition drives innovation.", "Competition stifles innovation.", "contradiction"),
    ("Property rights are essential for prosperity.", "Property rights are the primary cause of poverty.", "contradiction"),
    ("Moral truths are objective.", "Moral truths are entirely subjective.", "contradiction"),
    ("Democracy leads to better governance.", "Democracy leads to worse governance.", "contradiction"),
    ("Education increases earning potential.", "Education has no effect on earning potential.", "contradiction"),

    ("Markets reward coherent value propositions.", "Successful businesses have logically sound arguments.", "entailment"),
    ("Contradictions undermine persuasion.", "Logical inconsistencies weaken arguments.", "entailment"),
    ("Efficient allocation requires information.", "Markets need information to function well.", "entailment"),
    ("Innovation requires creative destruction.", "New industries displace old ones.", "entailment"),
    ("The firm has no competitors.", "The firm operates in an uncontested space.", "entailment"),
    ("Consumer preferences drive production.", "Businesses respond to demand.", "entailment"),
    ("Monopolies restrict output.", "Market power reduces supply.", "entailment"),
    ("Human capital increases productivity.", "Educated workers produce more.", "entailment"),

    ("Value is determined by logical coherence.", "The weather in Tokyo is mild.", "neutral"),
    ("Free markets allocate resources efficiently.", "She enjoys painting landscapes.", "neutral"),
    ("Innovation requires creative destruction.", "The cat slept on the windowsill.", "neutral"),
    ("Property rights are essential for prosperity.", "He plays tennis every Saturday.", "neutral"),
    ("Moral truths are objective.", "The train arrives at platform three.", "neutral"),
    ("Democracy leads to better governance.", "Pasta is best served al dente.", "neutral"),
    ("Education increases earning potential.", "The film premiered at Cannes.", "neutral"),
    ("Consumer preferences drive production.", "The glacier has retreated significantly.", "neutral"),
]

# ============================================================================
# TEST DATASET - Hard cases (subtle contradictions, paraphrases)
# ============================================================================
TEST_PAIRS_HARD = [
    # Subtle contradictions (not simple negation)
    ("The company has a monopoly on the market.", "Several strong competitors challenge the company.", "contradiction"),
    ("Our product is for everyone.", "Our product targets a niche audience of experts.", "contradiction"),
    ("We bootstrap and avoid external funding.", "We raised a Series B round last year.", "contradiction"),
    ("The algorithm is completely transparent.", "The algorithm's decision process cannot be explained.", "contradiction"),
    ("We prioritize data privacy above all.", "We sell anonymized user data to third parties.", "contradiction"),
    ("Our growth is organic and sustainable.", "We are burning cash at an unsustainable rate to acquire users.", "contradiction"),

    # Paraphrased entailments
    ("The startup ran out of money.", "The company's financial resources were depleted.", "entailment"),
    ("Customers are switching to our product.", "We are gaining market share.", "entailment"),
    ("The CEO resigned under pressure.", "There was a leadership change at the top.", "entailment"),
    ("The technology was patented.", "The intellectual property was legally protected.", "entailment"),
    ("Sales exceeded projections.", "Revenue performance was above expectations.", "entailment"),
    ("The factory was automated.", "Manual labor was replaced by machines.", "entailment"),

    # Tricky neutrals (topically related but independent)
    ("The company is based in San Francisco.", "The company reported strong earnings.", "neutral"),
    ("The CEO studied at Harvard.", "The company pivoted to enterprise sales.", "neutral"),
    ("The product uses machine learning.", "The office has an open floor plan.", "neutral"),
    ("The team has 50 employees.", "The company was founded in 2019.", "neutral"),
    ("The product is available on iOS.", "Customer satisfaction scores are high.", "neutral"),
    ("The company raised venture capital.", "The product integrates with Slack.", "neutral"),
]


def hoyer_sparsity(v):
    """Compute Hoyer sparsity index. 0 = uniform, 1 = one-hot."""
    n = len(v)
    l1 = np.sum(np.abs(v))
    l2 = np.sqrt(np.sum(v**2))
    if l2 == 0:
        return 0
    return (np.sqrt(n) - l1/l2) / (np.sqrt(n) - 1)


def cosine_sim(u, v):
    """Cosine similarity between two vectors."""
    return 1 - cosine(u, v)


def compute_features(model, pairs):
    """Compute difference vectors and features for sentence pairs."""
    results = []
    for premise, hypothesis, label in pairs:
        emb_p = model.encode(premise)
        emb_h = model.encode(hypothesis)
        diff = emb_h - emb_p
        cos = cosine_sim(emb_p, emb_h)
        hoy = hoyer_sparsity(diff)
        results.append({
            'premise': premise,
            'hypothesis': hypothesis,
            'label': label,
            'emb_premise': emb_p,
            'emb_hypothesis': emb_h,
            'diff_vector': diff,
            'cosine_sim': cos,
            'hoyer_sparsity': hoy,
            'diff_l2_norm': np.linalg.norm(diff),
        })
    return results


def test_1_learn_contradiction_direction(train_data):
    """Learn the contradiction direction c_hat via logistic regression."""
    print("\n" + "="*70)
    print("TEST 1: Learning the Contradiction Direction")
    print("="*70)

    # Use difference vectors as features, binary labels (contradiction vs not)
    X = np.array([d['diff_vector'] for d in train_data])
    y = np.array([1 if d['label'] == 'contradiction' else 0 for d in train_data])

    clf = LogisticRegression(max_iter=1000, C=1.0)

    # Cross-validated accuracy
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    scores = cross_val_score(clf, X, y, cv=cv, scoring='f1')
    print(f"  5-fold CV F1 (contradiction vs rest): {scores.mean():.3f} ± {scores.std():.3f}")

    # Train on full training set to extract direction
    clf.fit(X, y)
    c_hat = clf.coef_[0]
    c_hat = c_hat / np.linalg.norm(c_hat)  # Normalize to unit vector

    print(f"  Learned direction c_hat: norm = {np.linalg.norm(c_hat):.3f}")
    print(f"  Number of active dimensions (|coef| > 0.01): {np.sum(np.abs(clf.coef_[0]) > 0.01)}")
    print(f"  Fraction of active dims: {np.sum(np.abs(clf.coef_[0]) > 0.01) / len(c_hat):.3f}")

    return clf, c_hat


def test_2_cross_domain_generalization(clf, c_hat, model, test_pairs, domain_name):
    """Test whether the learned direction generalizes to unseen domains."""
    print(f"\n{'='*70}")
    print(f"TEST 2: Cross-Domain Generalization ({domain_name})")
    print("="*70)

    test_data = compute_features(model, test_pairs)
    X_test = np.array([d['diff_vector'] for d in test_data])
    y_test = np.array([1 if d['label'] == 'contradiction' else 0 for d in test_data])

    # Classifier prediction
    y_pred = clf.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)

    print(f"  Accuracy: {acc:.3f}")
    print(f"  F1 (contradiction): {f1:.3f}")
    print(f"\n  Classification Report:")
    print(classification_report(y_test, y_pred, target_names=['not-contradiction', 'contradiction'], zero_division=0))

    # Projection scores
    projections = X_test @ c_hat
    for label_name, label_val in [('contradiction', 1), ('entailment/neutral', 0)]:
        mask = y_test == label_val
        if mask.any():
            projs = projections[mask]
            print(f"  Projection ({label_name}): mean={projs.mean():.3f}, std={projs.std():.3f}")

    return acc, f1, test_data


def test_3_detection_method_comparison(train_data, test_data_list):
    """Compare cosine-only vs Hoyer-only vs combined vs linear probe."""
    print(f"\n{'='*70}")
    print("TEST 3: Detection Method Comparison")
    print("="*70)

    all_test = []
    for td in test_data_list:
        all_test.extend(td)

    y_true = np.array([1 if d['label'] == 'contradiction' else 0 for d in all_test])

    # Method 1: Cosine similarity threshold
    cosines = np.array([d['cosine_sim'] for d in all_test])
    # Contradictions tend to have mid-range cosine (they share topic)
    # Try: predict contradiction if cosine is in a specific range
    best_cos_f1 = 0
    best_cos_thresh = 0
    for thresh in np.arange(0.0, 1.0, 0.05):
        y_pred = (cosines < thresh).astype(int)
        f1 = f1_score(y_true, y_pred, zero_division=0)
        if f1 > best_cos_f1:
            best_cos_f1 = f1
            best_cos_thresh = thresh
    print(f"  Cosine-only (best threshold={best_cos_thresh:.2f}): F1 = {best_cos_f1:.3f}")

    # Method 2: Hoyer sparsity threshold
    hoyers = np.array([d['hoyer_sparsity'] for d in all_test])
    best_hoy_f1 = 0
    best_hoy_thresh = 0
    for thresh in np.arange(0.0, 1.0, 0.02):
        y_pred = (hoyers > thresh).astype(int)
        f1 = f1_score(y_true, y_pred, zero_division=0)
        if f1 > best_hoy_f1:
            best_hoy_f1 = f1
            best_hoy_thresh = thresh
    print(f"  Hoyer-only (best threshold={best_hoy_thresh:.2f}): F1 = {best_hoy_f1:.3f}")

    # Method 3: Combined score (alpha * cosine + (1-alpha) * hoyer)
    best_combined_f1 = 0
    best_alpha = 0
    best_combined_thresh = 0
    for alpha in np.arange(0.0, 1.05, 0.1):
        combined = alpha * (1 - cosines) + (1 - alpha) * hoyers
        for thresh in np.arange(0.0, 1.0, 0.02):
            y_pred = (combined > thresh).astype(int)
            f1 = f1_score(y_true, y_pred, zero_division=0)
            if f1 > best_combined_f1:
                best_combined_f1 = f1
                best_alpha = alpha
                best_combined_thresh = thresh
    print(f"  Combined (alpha={best_alpha:.1f}, thresh={best_combined_thresh:.2f}): F1 = {best_combined_f1:.3f}")

    # Method 4: Linear probe on difference vectors (already trained)
    X_train = np.array([d['diff_vector'] for d in train_data])
    y_train = np.array([1 if d['label'] == 'contradiction' else 0 for d in train_data])
    clf = LogisticRegression(max_iter=1000, C=1.0)
    clf.fit(X_train, y_train)

    X_test = np.array([d['diff_vector'] for d in all_test])
    y_pred = clf.predict(X_test)
    probe_f1 = f1_score(y_true, y_pred)
    print(f"  Linear probe on diff vectors: F1 = {probe_f1:.3f}")

    print(f"\n  SUMMARY:")
    print(f"    Cosine alone:    {best_cos_f1:.3f}")
    print(f"    Hoyer alone:     {best_hoy_f1:.3f}")
    print(f"    Combined:        {best_combined_f1:.3f}")
    print(f"    Linear probe:    {probe_f1:.3f}")

    return {
        'cosine_f1': best_cos_f1,
        'hoyer_f1': best_hoy_f1,
        'combined_f1': best_combined_f1,
        'probe_f1': probe_f1,
    }


def test_4_signal_concentration(train_data, c_hat):
    """Analyze how many dimensions carry the contradiction signal."""
    print(f"\n{'='*70}")
    print("TEST 4: Signal Concentration Analysis")
    print("="*70)

    diffs_contra = np.array([d['diff_vector'] for d in train_data if d['label'] == 'contradiction'])
    diffs_entail = np.array([d['diff_vector'] for d in train_data if d['label'] == 'entailment'])
    diffs_neutral = np.array([d['diff_vector'] for d in train_data if d['label'] == 'neutral'])

    # Mean absolute difference per dimension
    mean_contra = np.mean(np.abs(diffs_contra), axis=0)
    mean_entail = np.mean(np.abs(diffs_entail), axis=0)

    # Where does contradiction differ most from entailment?
    discrimination = np.abs(mean_contra - mean_entail)
    sorted_dims = np.argsort(discrimination)[::-1]

    # Cumulative discrimination
    cumulative = np.cumsum(discrimination[sorted_dims]) / np.sum(discrimination)

    # How many dims capture 50%, 80%, 90% of the signal?
    for target in [0.5, 0.8, 0.9, 0.95]:
        n_dims = np.searchsorted(cumulative, target) + 1
        print(f"  {target*100:.0f}% of contradiction signal in {n_dims} dims ({n_dims/len(c_hat)*100:.1f}%)")

    # PCA on contradiction difference vectors
    if len(diffs_contra) > 2:
        pca = PCA(n_components=min(len(diffs_contra)-1, 20))
        pca.fit(diffs_contra)
        cumvar = np.cumsum(pca.explained_variance_ratio_)
        for target in [0.5, 0.8, 0.9]:
            idx = np.searchsorted(cumvar, target)
            if idx < len(cumvar):
                print(f"  PCA: {target*100:.0f}% variance in {idx+1} components")

    # Save discrimination plot data
    np.save(os.path.join(OUTPUT_DIR, 'discrimination_per_dim.npy'), discrimination)

    return sorted_dims, discrimination


def test_5_robustness(model, c_hat, clf):
    """Test robustness to different negation styles and paraphrasing."""
    print(f"\n{'='*70}")
    print("TEST 5: Robustness to Negation Styles")
    print("="*70)

    base_statement = "The company is growing rapidly."

    negation_variants = [
        ("The company is not growing rapidly.", "simple negation"),
        ("The company is shrinking.", "antonym"),
        ("The company's growth has stalled completely.", "indirect negation"),
        ("Far from growing, the company is in decline.", "emphatic negation"),
        ("Growth is the last word anyone would use to describe the company.", "ironic negation"),
        ("The company has experienced zero growth.", "quantitative negation"),
    ]

    emb_base = model.encode(base_statement)

    print(f"  Base: '{base_statement}'")
    print(f"  {'Variant':<55} {'Cosine':>7} {'Hoyer':>7} {'Proj':>7} {'Pred':>6}")
    print(f"  {'-'*55} {'-'*7} {'-'*7} {'-'*7} {'-'*6}")

    for variant, style in negation_variants:
        emb_v = model.encode(variant)
        diff = emb_v - emb_base
        cos = cosine_sim(emb_base, emb_v)
        hoy = hoyer_sparsity(diff)
        proj = diff @ c_hat
        pred = clf.predict(diff.reshape(1, -1))[0]
        pred_label = "CONTRA" if pred == 1 else "other"

        print(f"  {variant:<55} {cos:>7.3f} {hoy:>7.3f} {proj:>7.3f} {pred_label:>6}")


def test_6_three_class(train_data):
    """Test 3-class classification (contradiction / entailment / neutral)."""
    print(f"\n{'='*70}")
    print("TEST 6: Three-Class Classification")
    print("="*70)

    label_map = {'contradiction': 0, 'entailment': 1, 'neutral': 2}
    X = np.array([d['diff_vector'] for d in train_data])
    y = np.array([label_map[d['label']] for d in train_data])

    clf3 = LogisticRegression(max_iter=1000, C=1.0, multi_class='multinomial')
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    scores = cross_val_score(clf3, X, y, cv=cv, scoring='accuracy')
    print(f"  5-fold CV Accuracy (3-class): {scores.mean():.3f} ± {scores.std():.3f}")

    clf3.fit(X, y)
    y_pred = clf3.predict(X)
    print(f"\n  Training set classification report:")
    print(classification_report(y, y_pred, target_names=['contradiction', 'entailment', 'neutral'], zero_division=0))

    # Extract the three directions
    for i, name in enumerate(['contradiction', 'entailment', 'neutral']):
        direction = clf3.coef_[i]
        active = np.sum(np.abs(direction) > 0.01)
        print(f"  {name} direction: {active} active dims ({active/len(direction)*100:.1f}%)")

    return clf3


def main():
    print("Loading model:", MODEL_NAME)
    model = SentenceTransformer(MODEL_NAME)

    print("Computing training features...")
    train_data = compute_features(model, TRAIN_PAIRS)

    # Summary statistics
    for label in ['contradiction', 'entailment', 'neutral']:
        subset = [d for d in train_data if d['label'] == label]
        cos_vals = [d['cosine_sim'] for d in subset]
        hoy_vals = [d['hoyer_sparsity'] for d in subset]
        print(f"\n  {label:>15}: cosine={np.mean(cos_vals):.3f}±{np.std(cos_vals):.3f}, "
              f"hoyer={np.mean(hoy_vals):.3f}±{np.std(hoy_vals):.3f}")

    # Run tests
    clf, c_hat = test_1_learn_contradiction_direction(train_data)

    test_data_phil = compute_features(model, TEST_PAIRS_PHILOSOPHY)
    acc_phil, f1_phil, _ = test_2_cross_domain_generalization(
        clf, c_hat, model, TEST_PAIRS_PHILOSOPHY, "Philosophy/Business")

    test_data_hard = compute_features(model, TEST_PAIRS_HARD)
    acc_hard, f1_hard, _ = test_2_cross_domain_generalization(
        clf, c_hat, model, TEST_PAIRS_HARD, "Hard Cases")

    test_3_detection_method_comparison(train_data, [test_data_phil, test_data_hard])

    sorted_dims, discrimination = test_4_signal_concentration(train_data, c_hat)

    test_5_robustness(model, c_hat, clf)

    clf3 = test_6_three_class(train_data)

    # Save results
    results = {
        'model': MODEL_NAME,
        'train_size': len(TRAIN_PAIRS),
        'test_philosophy_acc': acc_phil,
        'test_philosophy_f1': f1_phil,
        'test_hard_acc': acc_hard,
        'test_hard_f1': f1_hard,
        'top_10_discriminating_dims': sorted_dims[:10].tolist(),
    }

    with open(os.path.join(OUTPUT_DIR, 'direction_experiment_results.json'), 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*70}")
    print("EXPERIMENT COMPLETE")
    print("="*70)
    print(f"Results saved to {OUTPUT_DIR}/")


if __name__ == '__main__':
    main()

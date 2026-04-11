"""
Curated contradiction, entailment, and neutral sentence pairs
across multiple domains and contradiction types.

Each pair is (sentence_a, sentence_b, relationship, domain, subtype)
"""

# ─── GENERAL DOMAIN ──────────────────────────────────────────────────────────

GENERAL_PAIRS = [
    # Contradictions — simple negation
    ("The store is open today.", "The store is closed today.", "contradiction", "general", "negation"),
    ("She passed the exam.", "She failed the exam.", "contradiction", "general", "antonym"),
    ("The project was completed on time.", "The project was delayed significantly.", "contradiction", "general", "antonym"),
    ("Revenue increased this quarter.", "Revenue declined this quarter.", "contradiction", "general", "antonym"),
    ("The team supports the proposal.", "The team opposes the proposal.", "contradiction", "general", "antonym"),
    ("Water freezes at zero degrees Celsius.", "Water remains liquid at zero degrees Celsius.", "contradiction", "general", "factual"),
    ("The company is profitable.", "The company is losing money.", "contradiction", "general", "antonym"),
    ("He arrived early.", "He arrived late.", "contradiction", "general", "scalar"),
    ("The policy reduces inequality.", "The policy increases inequality.", "contradiction", "general", "antonym"),
    ("Demand is growing rapidly.", "Demand is shrinking rapidly.", "contradiction", "general", "antonym"),
    ("The experiment confirmed the hypothesis.", "The experiment refuted the hypothesis.", "contradiction", "general", "antonym"),
    ("The bridge is safe for traffic.", "The bridge is structurally unsound and dangerous.", "contradiction", "general", "factual"),
    ("All students passed the test.", "No student passed the test.", "contradiction", "general", "quantifier"),
    ("The medication has no side effects.", "The medication causes severe side effects.", "contradiction", "general", "negation"),
    ("The city is growing.", "The city is shrinking.", "contradiction", "general", "antonym"),

    # Entailments
    ("The cat is black.", "The cat has a color.", "entailment", "general", "hypernym"),
    ("She ran a marathon.", "She exercised.", "entailment", "general", "hypernym"),
    ("The restaurant is closed on Sundays.", "The restaurant is not open every day.", "entailment", "general", "implication"),
    ("He is a doctor.", "He works in healthcare.", "entailment", "general", "hypernym"),
    ("It rained all day.", "The ground got wet.", "entailment", "general", "causal"),
    ("The population doubled.", "The population increased.", "entailment", "general", "scalar"),
    ("She speaks French fluently.", "She knows French.", "entailment", "general", "implication"),
    ("Every seat is taken.", "The room is full.", "entailment", "general", "implication"),
    ("He broke his leg.", "He was injured.", "entailment", "general", "hypernym"),
    ("The sun is a star.", "The sun is a celestial body.", "entailment", "general", "hypernym"),
    ("All mammals are warm-blooded.", "Dogs are warm-blooded.", "entailment", "general", "instantiation"),
    ("The car is red.", "The car is not colorless.", "entailment", "general", "negation_entail"),
    ("She won the gold medal.", "She competed.", "entailment", "general", "implication"),
    ("The flight was cancelled.", "The passengers did not depart.", "entailment", "general", "causal"),
    ("He is a bachelor.", "He is unmarried.", "entailment", "general", "definition"),

    # Neutrals
    ("The cat is black.", "The car is fast.", "neutral", "general", "unrelated"),
    ("Revenue increased this quarter.", "The weather was mild.", "neutral", "general", "unrelated"),
    ("She passed the exam.", "The bridge is being repaired.", "neutral", "general", "unrelated"),
    ("The store is open today.", "Jupiter has many moons.", "neutral", "general", "unrelated"),
    ("He arrived early.", "The painting is beautiful.", "neutral", "general", "unrelated"),
    ("The team won the game.", "The library closes at nine.", "neutral", "general", "unrelated"),
    ("The economy is growing.", "The sunset was beautiful.", "neutral", "general", "unrelated"),
    ("Water freezes at zero degrees.", "Shakespeare wrote Hamlet.", "neutral", "general", "unrelated"),
    ("The medication works well.", "The train arrived on time.", "neutral", "general", "unrelated"),
    ("She speaks French.", "The mountain is tall.", "neutral", "general", "unrelated"),
    ("The building was demolished.", "Coffee prices are rising.", "neutral", "general", "unrelated"),
    ("The dog is sleeping.", "The algorithm is efficient.", "neutral", "general", "unrelated"),
    ("Taxes went up.", "The novel was published.", "neutral", "general", "unrelated"),
    ("The server crashed.", "Roses are red.", "neutral", "general", "unrelated"),
    ("The election results are in.", "The glacier is melting.", "neutral", "general", "unrelated"),
]

# ─── POLITICAL DOMAIN (draws from Marx/Smith ideological territory) ───────────

POLITICAL_PAIRS = [
    # Contradictions
    ("Private property is the foundation of all civilization.", "Private property is the root of all exploitation and must be abolished.", "contradiction", "political", "ideological"),
    ("The free market allocates resources efficiently.", "The market produces chaos and crises of overproduction.", "contradiction", "political", "ideological"),
    ("The state must wither away for true freedom.", "A strong state is necessary to protect individual rights.", "contradiction", "political", "ideological"),
    ("Class struggle is the engine of historical progress.", "Class harmony and cooperation drive social advancement.", "contradiction", "political", "ideological"),
    ("Taxation is theft.", "Taxation is the price of civilization.", "contradiction", "political", "ideological"),
    ("Workers are exploited under capitalism.", "Workers freely choose to sell their labor.", "contradiction", "political", "ideological"),
    ("Central planning can rationally allocate resources.", "No central planner can replicate the information in market prices.", "contradiction", "political", "ideological"),
    ("Democracy is the best form of government.", "Democracy is the tyranny of the majority.", "contradiction", "political", "ideological"),
    ("Profit is the reward for serving consumers.", "Profit is extracted surplus value stolen from workers.", "contradiction", "political", "ideological"),
    ("Individual liberty is the highest political value.", "Collective welfare must take priority over individual freedom.", "contradiction", "political", "ideological"),
    ("The bourgeoisie is a revolutionary class.", "The bourgeoisie is a parasitic class.", "contradiction", "political", "ideological"),
    ("Economic inequality is natural and productive.", "Economic inequality is artificial and destructive.", "contradiction", "political", "ideological"),
    ("Trade unions protect workers.", "Trade unions distort labor markets.", "contradiction", "political", "ideological"),
    ("Imperialism is the highest stage of capitalism.", "Free trade between nations promotes peace and prosperity.", "contradiction", "political", "ideological"),
    ("Religion is the opium of the people.", "Religion is the moral foundation of civilization.", "contradiction", "political", "ideological"),

    # Entailments
    ("The proletariat must seize the means of production.", "The working class must take political action.", "entailment", "political", "implication"),
    ("Capitalism requires private ownership of industry.", "Under capitalism, not all property is collectively owned.", "entailment", "political", "implication"),
    ("The state enforces property rights.", "The state plays a role in the economy.", "entailment", "political", "hypernym"),
    ("All workers deserve fair wages.", "Workers deserve compensation.", "entailment", "political", "scalar"),
    ("Monopolies restrict competition.", "Monopolies affect market dynamics.", "entailment", "political", "hypernym"),
    ("Taxes fund public services.", "Government collects revenue.", "entailment", "political", "implication"),
    ("Class struggle shapes history.", "Social conflict exists.", "entailment", "political", "hypernym"),
    ("Free trade increases total wealth.", "Trade has economic effects.", "entailment", "political", "hypernym"),
    ("The revolution will transform society.", "Society will change.", "entailment", "political", "hypernym"),
    ("Private property enables accumulation.", "Ownership has economic consequences.", "entailment", "political", "hypernym"),

    # Neutrals
    ("The bourgeoisie controls the means of production.", "The Amazon River is the largest by volume.", "neutral", "political", "unrelated"),
    ("Taxation funds public infrastructure.", "Saturn has visible rings.", "neutral", "political", "unrelated"),
    ("Democracy requires informed citizens.", "Photosynthesis converts light to energy.", "neutral", "political", "unrelated"),
    ("Workers deserve fair compensation.", "The Mona Lisa hangs in the Louvre.", "neutral", "political", "unrelated"),
    ("The state should protect individual rights.", "Dolphins are mammals.", "neutral", "political", "unrelated"),
    ("Free markets encourage innovation.", "DNA has a double helix structure.", "neutral", "political", "unrelated"),
    ("Class consciousness arises from shared conditions.", "The Pacific Ocean is the largest ocean.", "neutral", "political", "unrelated"),
    ("Capitalism creates wealth inequality.", "Mount Everest is the tallest mountain.", "neutral", "political", "unrelated"),
    ("Central planning eliminates market waste.", "The speed of light is constant.", "neutral", "political", "unrelated"),
    ("Private property precedes the state.", "Chess was invented in India.", "neutral", "political", "unrelated"),
]

# ─── PHILOSOPHICAL DOMAIN ────────────────────────────────────────────────────

PHILOSOPHICAL_PAIRS = [
    # Contradictions
    ("Free will is an illusion determined by prior causes.", "Humans possess genuine free will independent of causation.", "contradiction", "philosophical", "metaphysical"),
    ("Morality is objective and universal.", "Morality is relative to culture and circumstance.", "contradiction", "philosophical", "ethical"),
    ("The mind is identical to the brain.", "The mind is fundamentally distinct from physical matter.", "contradiction", "philosophical", "metaphysical"),
    ("Knowledge requires certainty.", "All knowledge is probabilistic and fallible.", "contradiction", "philosophical", "epistemic"),
    ("Meaning is determined by the speaker's intention.", "Meaning is determined by social convention and use.", "contradiction", "philosophical", "linguistic"),
    ("The universe has a purpose.", "The universe is fundamentally purposeless.", "contradiction", "philosophical", "metaphysical"),
    ("Mathematics is discovered, not invented.", "Mathematics is a human invention.", "contradiction", "philosophical", "metaphysical"),
    ("Beauty is in the eye of the beholder.", "Beauty is an objective property of things.", "contradiction", "philosophical", "aesthetic"),
    ("Consciousness can be fully explained by physics.", "Consciousness requires explanation beyond physical processes.", "contradiction", "philosophical", "metaphysical"),
    ("Language determines the limits of thought.", "Thought is prior to and independent of language.", "contradiction", "philosophical", "linguistic"),
    ("Existence precedes essence.", "Essence precedes existence.", "contradiction", "philosophical", "existential"),
    ("The good life consists in pleasure.", "The good life consists in virtue regardless of pleasure.", "contradiction", "philosophical", "ethical"),
    ("Time is real and fundamental.", "Time is an illusion arising from more basic processes.", "contradiction", "philosophical", "metaphysical"),
    ("Personal identity persists through change.", "There is no enduring self, only momentary states.", "contradiction", "philosophical", "metaphysical"),
    ("Logic is the foundation of all rational thought.", "Reason has limits that logic alone cannot overcome.", "contradiction", "philosophical", "epistemic"),

    # Entailments
    ("All knowledge comes from experience.", "Sensory experience contributes to knowledge.", "entailment", "philosophical", "implication"),
    ("The mind is the brain.", "Mental states are physical states.", "entailment", "philosophical", "implication"),
    ("Free will exists.", "Moral responsibility is possible.", "entailment", "philosophical", "implication"),
    ("Nothing exists beyond the physical.", "Ghosts do not exist.", "entailment", "philosophical", "instantiation"),
    ("Morality is objective.", "Some actions are wrong regardless of opinion.", "entailment", "philosophical", "implication"),
    ("Language shapes thought.", "Learning a new language may change how you think.", "entailment", "philosophical", "implication"),
    ("Consciousness cannot be reduced to physics.", "Physics alone does not explain everything.", "entailment", "philosophical", "implication"),
    ("Truth is correspondence with reality.", "A statement is true if it matches the facts.", "entailment", "philosophical", "definition"),

    # Neutrals
    ("Morality is objective.", "The speed of light is 299,792 km/s.", "neutral", "philosophical", "unrelated"),
    ("Free will exists.", "Copper conducts electricity.", "neutral", "philosophical", "unrelated"),
    ("The mind is the brain.", "The Amazon rainforest is shrinking.", "neutral", "philosophical", "unrelated"),
    ("Knowledge requires certainty.", "Penguins live in Antarctica.", "neutral", "philosophical", "unrelated"),
    ("Language determines thought.", "The Nile flows north.", "neutral", "philosophical", "unrelated"),
    ("Beauty is subjective.", "Gravity pulls objects downward.", "neutral", "philosophical", "unrelated"),
    ("Consciousness is physical.", "Rome was founded in 753 BC.", "neutral", "philosophical", "unrelated"),
    ("Time is an illusion.", "Bananas are berries.", "neutral", "philosophical", "unrelated"),
]

# ─── EMPIRICAL DOMAIN ────────────────────────────────────────────────────────

EMPIRICAL_PAIRS = [
    # Contradictions
    ("The Earth is approximately 4.5 billion years old.", "The Earth is less than 10,000 years old.", "contradiction", "empirical", "factual"),
    ("Vaccines prevent disease effectively.", "Vaccines cause the diseases they claim to prevent.", "contradiction", "empirical", "factual"),
    ("Human activity is the primary driver of climate change.", "Climate change is entirely natural and unrelated to human activity.", "contradiction", "empirical", "causal"),
    ("Evolution explains the diversity of life.", "All species were created in their present form.", "contradiction", "empirical", "theoretical"),
    ("Antibiotics kill bacteria.", "Antibiotics have no effect on bacteria.", "contradiction", "empirical", "factual"),
    ("The universe is expanding.", "The universe is static and unchanging.", "contradiction", "empirical", "factual"),
    ("Smoking causes lung cancer.", "Smoking has no causal relationship to cancer.", "contradiction", "empirical", "causal"),
    ("Light travels faster than sound.", "Sound travels faster than light.", "contradiction", "empirical", "factual"),
    ("Exercise improves cardiovascular health.", "Exercise damages cardiovascular health.", "contradiction", "empirical", "causal"),
    ("The brain controls behavior.", "Behavior is independent of brain function.", "contradiction", "empirical", "causal"),
    ("Gravity is proportional to mass.", "Gravity is unrelated to mass.", "contradiction", "empirical", "factual"),
    ("DNA carries genetic information.", "DNA has no role in heredity.", "contradiction", "empirical", "factual"),
    ("Ocean acidification harms coral reefs.", "Ocean acidification benefits coral reefs.", "contradiction", "empirical", "causal"),
    ("Sleep deprivation impairs cognitive function.", "Sleep deprivation improves cognitive function.", "contradiction", "empirical", "causal"),
    ("Plate tectonics causes earthquakes.", "Earthquakes have no relationship to plate tectonics.", "contradiction", "empirical", "causal"),

    # Entailments
    ("The Earth orbits the Sun.", "The Earth moves through space.", "entailment", "empirical", "implication"),
    ("Water boils at 100 degrees Celsius at sea level.", "Water changes state at high temperatures.", "entailment", "empirical", "scalar"),
    ("Mammals are warm-blooded.", "Mammals regulate their body temperature.", "entailment", "empirical", "definition"),
    ("The speed of light is finite.", "Light takes time to travel.", "entailment", "empirical", "implication"),
    ("DNA replicates during cell division.", "Cells contain genetic material.", "entailment", "empirical", "implication"),
    ("Photosynthesis requires sunlight.", "Plants need light.", "entailment", "empirical", "hypernym"),
    ("Neurons transmit electrical signals.", "The nervous system uses electricity.", "entailment", "empirical", "hypernym"),
    ("The universe began with the Big Bang.", "The universe has a finite age.", "entailment", "empirical", "implication"),

    # Neutrals
    ("DNA carries genetic information.", "The French Revolution began in 1789.", "neutral", "empirical", "unrelated"),
    ("Water boils at 100 degrees.", "Shakespeare was born in Stratford.", "neutral", "empirical", "unrelated"),
    ("The Earth orbits the Sun.", "Mozart composed symphonies.", "neutral", "empirical", "unrelated"),
    ("Vaccines prevent disease.", "The Great Wall is visible from space.", "neutral", "empirical", "unrelated"),
    ("Gravity attracts objects.", "Kafka wrote The Metamorphosis.", "neutral", "empirical", "unrelated"),
    ("Neurons transmit signals.", "The Roman Empire fell in 476 AD.", "neutral", "empirical", "unrelated"),
    ("Evolution explains diversity.", "Pi is approximately 3.14159.", "neutral", "empirical", "unrelated"),
    ("Light travels at 300,000 km/s.", "Beethoven was deaf.", "neutral", "empirical", "unrelated"),
]

# ─── NEGATION VARIETIES ──────────────────────────────────────────────────────
# For Experiment 3: testing how different negation styles map in embedding space

NEGATION_TEST_PAIRS = [
    # (original, simple_negation, antonym_negation, indirect_negation)
    {
        "original": "The door is open.",
        "simple": "The door is not open.",
        "antonym": "The door is closed.",
        "indirect": "The door is shut tight.",
        "scalar": "The door is barely ajar.",
        "modal": "The door cannot be open.",
        "quantifier": "No door in this building is open.",
    },
    {
        "original": "The economy is growing.",
        "simple": "The economy is not growing.",
        "antonym": "The economy is shrinking.",
        "indirect": "The economy is in recession.",
        "scalar": "The economy is stagnant.",
        "modal": "The economy cannot grow.",
        "quantifier": "No sector of the economy is growing.",
    },
    {
        "original": "She is happy.",
        "simple": "She is not happy.",
        "antonym": "She is sad.",
        "indirect": "She is in distress.",
        "scalar": "She is slightly content.",
        "modal": "She cannot be happy.",
        "quantifier": "Nobody in her family is happy.",
    },
    {
        "original": "The experiment succeeded.",
        "simple": "The experiment did not succeed.",
        "antonym": "The experiment failed.",
        "indirect": "The experiment produced no usable results.",
        "scalar": "The experiment barely produced results.",
        "modal": "The experiment could not succeed.",
        "quantifier": "None of the experiments succeeded.",
    },
    {
        "original": "The government supports free trade.",
        "simple": "The government does not support free trade.",
        "antonym": "The government opposes free trade.",
        "indirect": "The government has imposed tariffs and trade barriers.",
        "scalar": "The government is ambivalent about free trade.",
        "modal": "The government cannot support free trade.",
        "quantifier": "No government supports free trade.",
    },
    {
        "original": "Private property is sacred.",
        "simple": "Private property is not sacred.",
        "antonym": "Private property is illegitimate.",
        "indirect": "Property claims are social constructs with no inherent sanctity.",
        "scalar": "Private property is merely tolerated.",
        "modal": "Private property cannot be considered sacred.",
        "quantifier": "No form of property is sacred.",
    },
    {
        "original": "All humans are equal.",
        "simple": "Not all humans are equal.",
        "antonym": "Humans are fundamentally unequal.",
        "indirect": "Natural hierarchies exist among people.",
        "scalar": "Humans are approximately equal in some respects.",
        "modal": "Humans cannot be truly equal.",
        "quantifier": "No two humans are truly equal.",
    },
    {
        "original": "The market is efficient.",
        "simple": "The market is not efficient.",
        "antonym": "The market is wasteful.",
        "indirect": "Resources are systematically misallocated.",
        "scalar": "The market is sometimes efficient.",
        "modal": "The market cannot be efficient.",
        "quantifier": "No market is truly efficient.",
    },
    {
        "original": "Democracy produces good outcomes.",
        "simple": "Democracy does not produce good outcomes.",
        "antonym": "Democracy produces terrible outcomes.",
        "indirect": "The democratic process leads to mediocre governance.",
        "scalar": "Democracy sometimes produces acceptable outcomes.",
        "modal": "Democracy cannot produce good outcomes.",
        "quantifier": "No democratic system produces good outcomes.",
    },
    {
        "original": "Violence is never justified.",
        "simple": "Violence is not never justified.",
        "antonym": "Violence is sometimes necessary.",
        "indirect": "There are circumstances where force is the only option.",
        "scalar": "Violence is rarely justified.",
        "modal": "It cannot be said that violence is never justified.",
        "quantifier": "Every society has justified violence at some point.",
    },
]

# ─── PRAGMATIC CONTRADICTIONS ─────────────────────────────────────────────────
# Contradictions that require world knowledge, not just semantic opposition

PRAGMATIC_PAIRS = [
    ("He is a lifelong bachelor.", "His wife called him.", "contradiction", "pragmatic", "world_knowledge"),
    ("She is an only child.", "Her brother visited yesterday.", "contradiction", "pragmatic", "world_knowledge"),
    ("The company went bankrupt last year.", "The company reported record profits last year.", "contradiction", "pragmatic", "temporal"),
    ("He has never left the country.", "He described his trip to Paris.", "contradiction", "pragmatic", "world_knowledge"),
    ("The building was demolished in 2019.", "The building hosted an event in 2023.", "contradiction", "pragmatic", "temporal"),
    ("She is a strict vegan.", "She ordered the steak.", "contradiction", "pragmatic", "world_knowledge"),
    ("He is completely deaf.", "He described the sound of the orchestra.", "contradiction", "pragmatic", "world_knowledge"),
    ("The river has been dry for decades.", "The flood from the river destroyed the town.", "contradiction", "pragmatic", "temporal"),
    ("She has never learned to read.", "She reviewed the manuscript carefully.", "contradiction", "pragmatic", "world_knowledge"),
    ("He is a committed pacifist.", "He enlisted in the army to fight.", "contradiction", "pragmatic", "world_knowledge"),
]


def get_all_pairs():
    """Return all pairs across all domains."""
    return GENERAL_PAIRS + POLITICAL_PAIRS + PHILOSOPHICAL_PAIRS + EMPIRICAL_PAIRS + PRAGMATIC_PAIRS


def get_pairs_by_domain(domain):
    """Return pairs for a specific domain."""
    mapping = {
        "general": GENERAL_PAIRS,
        "political": POLITICAL_PAIRS,
        "philosophical": PHILOSOPHICAL_PAIRS,
        "empirical": EMPIRICAL_PAIRS,
        "pragmatic": PRAGMATIC_PAIRS,
    }
    return mapping.get(domain, [])


def get_pairs_by_relationship(relationship):
    """Return all pairs of a given relationship type across all domains."""
    return [p for p in get_all_pairs() if p[2] == relationship]

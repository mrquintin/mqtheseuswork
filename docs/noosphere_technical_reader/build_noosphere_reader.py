#!/usr/bin/env python3
"""Build the Noosphere technical reader packet.

This script intentionally separates source collection from synthesis. It caches
officially linked PDFs/pages where available, records failures or paywalled
items, and generates a pdflatex-built reader that paraphrases and teaches the
ideas instead of republishing full copyrighted sources.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import fitz
import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
CACHE = OUT / "source_cache"
PDF_CACHE = CACHE / "pdf"
HTML_CACHE = CACHE / "html"
TEXT_CACHE = CACHE / "text"
META_CACHE = CACHE / "metadata"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


SOURCES = [
    {
        "domain": "LLM foundations",
        "title": "3Blue1Brown Neural Networks series",
        "url": "https://www.3blue1brown.com/topics/neural-networks",
        "kind": "html",
        "use": "Conceptual visual foundation for networks, gradients, attention, and transformers.",
    },
    {
        "domain": "LLM foundations",
        "title": "Jay Alammar, The Illustrated Transformer",
        "url": "https://jalammar.github.io/illustrated-transformer/",
        "kind": "html",
        "use": "First-pass architecture map: embeddings, attention, encoder/decoder blocks.",
    },
    {
        "domain": "LLM foundations",
        "title": "Stephen Wolfram, What Is ChatGPT Doing?",
        "url": "https://writings.stephenwolfram.com/2023/02/what-is-chatgpt-doing-and-why-does-it-work/",
        "kind": "html",
        "use": "Nontechnical explanation of next-token prediction, embeddings, and generated structure.",
    },
    {
        "domain": "LLM foundations",
        "title": "Andrej Karpathy, Let's build GPT",
        "url": "https://www.youtube.com/watch?v=kCc8FmEb1nY",
        "kind": "video",
        "use": "Implementation-oriented mental model for attention, blocks, loss, and training.",
    },
    {
        "domain": "LLM foundations",
        "title": "Jurafsky and Martin, Speech and Language Processing",
        "url": "https://web.stanford.edu/~jurafsky/slp3/",
        "kind": "html",
        "use": "Textbook spine for neural NLP, transformers, embeddings, extraction, and QA.",
    },
    {
        "domain": "LLM foundations",
        "title": "Vaswani et al., Attention Is All You Need",
        "url": "https://arxiv.org/abs/1706.03762",
        "kind": "arxiv",
        "use": "Original transformer architecture; read for attention, positional encoding, and residual blocks.",
    },
    {
        "domain": "LLM foundations",
        "title": "Lena Voita, NLP Course",
        "url": "https://lena-voita.github.io/nlp_course.html",
        "kind": "html",
        "use": "Careful course notes for embeddings, attention, transfer learning, and analysis.",
    },
    {
        "domain": "Scaling and alignment",
        "title": "Kaplan et al., Scaling Laws for Neural Language Models",
        "url": "https://arxiv.org/abs/2001.08361",
        "kind": "arxiv",
        "use": "Why model behavior changes predictably with compute, data, and parameter count.",
    },
    {
        "domain": "Scaling and alignment",
        "title": "Hoffmann et al., Training Compute-Optimal Large Language Models",
        "url": "https://arxiv.org/abs/2203.15556",
        "kind": "arxiv",
        "use": "Chinchilla correction: data/parameter ratio matters, not just parameter count.",
    },
    {
        "domain": "Scaling and alignment",
        "title": "Ouyang et al., Training Language Models to Follow Instructions",
        "url": "https://arxiv.org/abs/2203.02155",
        "kind": "arxiv",
        "use": "Instruction tuning and RLHF; explains why production LLMs are not raw predictors.",
    },
    {
        "domain": "Scaling and alignment",
        "title": "Bai et al., Constitutional AI",
        "url": "https://arxiv.org/abs/2212.08073",
        "kind": "arxiv",
        "use": "AI-feedback alignment and model priors relevant to Claude-backed extraction.",
    },
    {
        "domain": "Interpretability",
        "title": "Elhage et al., A Mathematical Framework for Transformer Circuits",
        "url": "https://transformer-circuits.pub/2021/framework/index.html",
        "kind": "html",
        "use": "Mechanistic decomposition of transformer computations into circuits.",
    },
    {
        "domain": "Interpretability",
        "title": "Elhage et al., Toy Models of Superposition",
        "url": "https://transformer-circuits.pub/2022/toy_model/index.html",
        "kind": "html",
        "use": "Why features can be polysemantic and why a clean coherence direction may not exist.",
    },
    {
        "domain": "Interpretability",
        "title": "Templeton et al., Scaling Monosemanticity",
        "url": "https://transformer-circuits.pub/2024/scaling-monosemanticity/",
        "kind": "html",
        "use": "Sparse autoencoders and interpretable features in a production-scale model.",
    },
    {
        "domain": "Interpretability",
        "title": "Olah et al., Distill Circuits thread",
        "url": "https://distill.pub/2020/circuits/",
        "kind": "html",
        "use": "Methodological ancestor of circuit-level interpretability.",
    },
    {
        "domain": "Interpretability",
        "title": "Belinkov and Glass, Analysis Methods in Neural Language Processing",
        "url": "https://arxiv.org/abs/1812.08951",
        "kind": "arxiv",
        "use": "Taxonomy of probing and behavioral analysis methods.",
    },
    {
        "domain": "Embedding geometry",
        "title": "3Blue1Brown Essence of Linear Algebra",
        "url": "https://www.3blue1brown.com/topics/linear-algebra",
        "kind": "html",
        "use": "Geometric intuition for vectors, bases, eigenvectors, and transformations.",
    },
    {
        "domain": "Embedding geometry",
        "title": "MIT OCW 18.06 Linear Algebra",
        "url": "https://ocw.mit.edu/courses/18-06-linear-algebra-spring-2010/",
        "kind": "html",
        "use": "Formal linear algebra backbone for embeddings and transformations.",
    },
    {
        "domain": "Embedding geometry",
        "title": "Jay Alammar, The Illustrated Word2vec",
        "url": "https://jalammar.github.io/illustrated-word2vec/",
        "kind": "html",
        "use": "Visual bridge from words to distributed vectors.",
    },
    {
        "domain": "Embedding geometry",
        "title": "Mikolov et al., Efficient Estimation of Word Representations",
        "url": "https://arxiv.org/abs/1301.3781",
        "kind": "arxiv",
        "use": "Historical source for learned word embeddings as semantic objects.",
    },
    {
        "domain": "Embedding geometry",
        "title": "Jurafsky and Martin, Chapter 6: Vector Semantics and Embeddings",
        "url": "https://web.stanford.edu/~jurafsky/slp3/6.pdf",
        "kind": "pdf",
        "use": "PPMI, SVD, word2vec, GloVe, and embedding evaluation.",
    },
    {
        "domain": "Embedding geometry",
        "title": "Pennington et al., GloVe",
        "url": "https://nlp.stanford.edu/pubs/glove.pdf",
        "kind": "pdf",
        "use": "Co-occurrence matrix factorization view of embeddings.",
    },
    {
        "domain": "Embedding geometry",
        "title": "Reimers and Gurevych, Sentence-BERT",
        "url": "https://arxiv.org/abs/1908.10084",
        "kind": "arxiv",
        "use": "Sentence-level embeddings, directly relevant to claim and principle vectors.",
    },
    {
        "domain": "Embedding geometry",
        "title": "Cuturi and Peyre, Computational Optimal Transport",
        "url": "https://arxiv.org/abs/1803.00567",
        "kind": "arxiv",
        "use": "Distribution-level geometry for comparing clouds of embeddings.",
    },
    {
        "domain": "Embedding geometry",
        "title": "Bronstein et al., Geometric Deep Learning",
        "url": "https://arxiv.org/abs/2104.13478",
        "kind": "arxiv",
        "use": "Unifies learning under symmetry across grids, graphs, manifolds, and transformers.",
    },
    {
        "domain": "Embedding geometry",
        "title": "Fefferman et al., Testing the Manifold Hypothesis",
        "url": "https://arxiv.org/abs/1310.0425",
        "kind": "arxiv",
        "use": "Mathematical version of the claim that high-dimensional data lies on low-dimensional structure.",
    },
    {
        "domain": "Representation geometry",
        "title": "Park, Choe, and Veitch, Linear Representation Hypothesis",
        "url": "https://arxiv.org/abs/2311.03658",
        "kind": "arxiv",
        "use": "Formal backbone for treating concepts as linear directions in LLM representations.",
    },
    {
        "domain": "Representation geometry",
        "title": "Marks and Tegmark, Geometry of Truth",
        "url": "https://arxiv.org/abs/2310.06824",
        "kind": "arxiv",
        "use": "Empirical truth directions in LLM activation space.",
    },
    {
        "domain": "Representation geometry",
        "title": "Burns et al., Discovering Latent Knowledge without Supervision",
        "url": "https://arxiv.org/abs/2212.03827",
        "kind": "arxiv",
        "use": "Contrast-consistent search and logical consistency directions.",
    },
    {
        "domain": "Representation geometry",
        "title": "Zou et al., Representation Engineering",
        "url": "https://arxiv.org/abs/2310.01405",
        "kind": "arxiv",
        "use": "Practical direction-finding and direction-steering toolkit.",
    },
    {
        "domain": "NLP extraction",
        "title": "Manning et al., Computational Linguistics and Deep Learning",
        "url": "https://aclanthology.org/Q16-1019/",
        "kind": "acl",
        "use": "Deep learning transition in NLP.",
    },
    {
        "domain": "NLP extraction",
        "title": "Advanced NLP with spaCy",
        "url": "https://course.spacy.io/",
        "kind": "html",
        "use": "Classical pipeline implementation: tokenization, NER, dependency parsing, matching.",
    },
    {
        "domain": "NLP extraction",
        "title": "Natural Language Processing with Python",
        "url": "https://www.nltk.org/book/",
        "kind": "html",
        "use": "Friendly introduction to rule-based and statistical NLP pipelines.",
    },
    {
        "domain": "NLP extraction",
        "title": "Jurafsky and Martin, Chapter 18: Information Extraction",
        "url": "https://web.stanford.edu/~jurafsky/slp3/18.pdf",
        "kind": "pdf",
        "use": "NER, relation extraction, event extraction, temporal expressions.",
    },
    {
        "domain": "NLP extraction",
        "title": "Devlin et al., BERT",
        "url": "https://arxiv.org/abs/1810.04805",
        "kind": "arxiv",
        "use": "Pretrained bidirectional encoder behind modern extraction systems.",
    },
    {
        "domain": "NLP extraction",
        "title": "Lee et al., End-to-end Neural Coreference Resolution",
        "url": "https://arxiv.org/abs/1707.07045",
        "kind": "arxiv",
        "use": "Coreference as a prerequisite for clean graph nodes.",
    },
    {
        "domain": "NLP extraction",
        "title": "Cabot and Navigli, REBEL",
        "url": "https://aclanthology.org/2021.findings-emnlp.204/",
        "kind": "acl",
        "use": "Relation extraction by sequence generation.",
    },
    {
        "domain": "NLP extraction",
        "title": "Wang et al., Neural Relation Extraction Survey",
        "url": "https://aclanthology.org/C18-1326/",
        "kind": "acl",
        "use": "Survey of relation extraction approaches before instruction-tuned LLMs.",
    },
    {
        "domain": "NLP extraction",
        "title": "Wadhwa et al., Information Extraction from LLMs",
        "url": "https://arxiv.org/abs/2305.05003",
        "kind": "arxiv",
        "use": "Zero/few-shot LLM extraction behavior and failure modes.",
    },
    {
        "domain": "NLP extraction",
        "title": "Qiao et al., Reasoning with Language Model Prompting",
        "url": "https://arxiv.org/abs/2212.09597",
        "kind": "arxiv",
        "use": "Prompting survey: decomposition, chain-of-thought, self-consistency, tools.",
    },
    {
        "domain": "NLP extraction",
        "title": "Lewis et al., Retrieval-Augmented Generation",
        "url": "https://arxiv.org/abs/2005.11401",
        "kind": "arxiv",
        "use": "Retrieval-grounded generation and knowledge-intensive tasks.",
    },
    {
        "domain": "NLP extraction",
        "title": "Stab and Gurevych, Parsing Argumentation Structures",
        "url": "https://aclanthology.org/J17-3005/",
        "kind": "acl",
        "use": "Claims, premises, support relations, and argument mining.",
    },
    {
        "domain": "Knowledge graphs",
        "title": "Hogan et al., Knowledge Graphs",
        "url": "https://arxiv.org/abs/2003.02320",
        "kind": "arxiv",
        "use": "Knowledge graph handbook: data models, identity, quality, refinement.",
    },
    {
        "domain": "Knowledge graphs",
        "title": "NetworkX tutorial",
        "url": "https://networkx.org/documentation/stable/tutorial.html",
        "kind": "html",
        "use": "Practical graph representation and traversal operations used in Noosphere.",
    },
    {
        "domain": "Knowledge graphs",
        "title": "Diestel, Graph Theory",
        "url": "https://diestel-graph-theory.com/",
        "kind": "html",
        "use": "Formal graph-theory reference. Full downloadable PDF was not assumed from mirrors.",
    },
    {
        "domain": "Logic and coherence",
        "title": "SEP, Coherentist Theories of Epistemic Justification",
        "url": "https://plato.stanford.edu/entries/justep-coherence/",
        "kind": "html",
        "use": "Philosophical target: coherence as justification, not automatically truth.",
    },
    {
        "domain": "Logic and coherence",
        "title": "SEP, Coherence Theory of Truth",
        "url": "https://plato.stanford.edu/entries/truth-coherence/",
        "kind": "html",
        "use": "Distinguishes coherence-as-truth from coherence-as-justification.",
    },
    {
        "domain": "Knowledge graphs",
        "title": "Bordes et al., TransE",
        "url": "https://proceedings.neurips.cc/paper/2013/hash/1cecc7a77928ca8133fa24680a88d2f9-Abstract.html",
        "kind": "neurips",
        "use": "Knowledge-graph embeddings as translation in vector space.",
    },
    {
        "domain": "Knowledge graphs",
        "title": "Wang et al., Knowledge Graph Embedding Survey",
        "url": "https://ieeexplore.ieee.org/document/8047276",
        "kind": "html",
        "use": "KG embedding vocabulary and model taxonomy; page cached, full IEEE PDF not public here.",
    },
    {
        "domain": "Logic and coherence",
        "title": "SEP, Paraconsistent Logic",
        "url": "https://plato.stanford.edu/entries/logic-paraconsistent/",
        "kind": "html",
        "use": "Reasoning without explosion under contradiction.",
    },
    {
        "domain": "Logic and coherence",
        "title": "SEP, Mereology",
        "url": "https://plato.stanford.edu/entries/mereology/",
        "kind": "html",
        "use": "Part-whole relations for principle distillation and claim composition.",
    },
    {
        "domain": "Logic and coherence",
        "title": "SEP, Logic of Belief Revision",
        "url": "https://plato.stanford.edu/entries/logic-belief-revision/",
        "kind": "html",
        "use": "Formal belief update and revision.",
    },
    {
        "domain": "Knowledge graphs",
        "title": "Nickel et al., Relational Machine Learning for Knowledge Graphs",
        "url": "https://arxiv.org/abs/1503.00759",
        "kind": "arxiv",
        "use": "Relational learning, latent-feature models, and graph-feature models.",
    },
    {
        "domain": "Representation geometry",
        "title": "Lin et al., TruthfulQA",
        "url": "https://arxiv.org/abs/2109.07958",
        "kind": "arxiv",
        "use": "Truthfulness benchmark for models that mimic human falsehoods.",
    },
    {
        "domain": "Representation geometry",
        "title": "Li et al., Inference-Time Intervention",
        "url": "https://arxiv.org/abs/2306.03341",
        "kind": "arxiv",
        "use": "Intervening on attention-head directions correlated with truthfulness.",
    },
    {
        "domain": "Logic and coherence",
        "title": "Thagard, Coherence as Constraint Satisfaction",
        "url": "https://onlinelibrary.wiley.com/doi/10.1207/s15516709cog2201_1",
        "kind": "html",
        "use": "Computational coherentism as network constraint satisfaction; page cached, full text not public here.",
    },
    {
        "domain": "Interpretability",
        "title": "Olsson et al., In-context Learning and Induction Heads",
        "url": "https://transformer-circuits.pub/2022/in-context-learning-and-induction-heads/index.html",
        "kind": "html",
        "use": "Circuit-level explanation of a concrete in-context learning behavior.",
    },
    {
        "domain": "Math primers",
        "title": "Blitzstein and Hwang, Introduction to Probability / Stat 110",
        "url": "https://projects.iq.harvard.edu/stat110",
        "kind": "html",
        "use": "Probability prerequisite for calibration, Bayesian updates, and uncertainty.",
    },
    {
        "domain": "Math primers",
        "title": "MIT OCW 18.02 Multivariable Calculus",
        "url": "https://ocw.mit.edu/courses/18-02-multivariable-calculus-fall-2007/",
        "kind": "html",
        "use": "Calculus prerequisite for gradients and optimization.",
    },
    {
        "domain": "Math primers",
        "title": "MacKay, Information Theory, Inference, and Learning Algorithms",
        "url": "https://www.inference.org.uk/itila/book.html",
        "kind": "web_book",
        "pdf_url": "https://www.inference.org.uk/itprnn/book.pdf",
        "use": "Information theory and probabilistic inference primer.",
    },
    {
        "domain": "Math primers",
        "title": "Boyd and Vandenberghe, Convex Optimization",
        "url": "https://web.stanford.edu/~boyd/cvxbook/",
        "kind": "web_book",
        "pdf_url": "https://web.stanford.edu/~boyd/cvxbook/bv_cvxbook.pdf",
        "use": "Optimization primer for training objectives and convex geometry.",
    },
    {
        "domain": "KG and LLM frontier",
        "title": "Pan et al., Unifying Large Language Models and Knowledge Graphs",
        "url": "https://arxiv.org/abs/2306.08302",
        "kind": "arxiv",
        "use": "Current roadmap for KG-enhanced LLMs, LLM-augmented KGs, and synergized systems.",
    },
    {
        "domain": "KG and LLM frontier",
        "title": "Bian, LLM-empowered Knowledge Graph Construction",
        "url": "https://arxiv.org/abs/2510.20345",
        "kind": "arxiv",
        "use": "Recent survey of LLM-based ontology engineering, extraction, and fusion.",
    },
    {
        "domain": "KG and LLM frontier",
        "title": "Pan et al., Large Language Models and Knowledge Graphs",
        "url": "https://arxiv.org/abs/2308.06374",
        "kind": "arxiv",
        "use": "Position paper on explicit KGs and parametric knowledge in LLMs.",
    },
]


LOCAL_SOURCES = [
    {
        "domain": "Theseus local",
        "title": "Theseus README",
        "path": "README.md",
        "use": "Defines Theseus as principle extraction, algorithm execution, and accountable bets.",
    },
    {
        "domain": "Theseus local",
        "title": "Algorithmized Decision Making",
        "path": "docs/architecture/Algorithmized_Decision_Making.md",
        "use": "Defines traces, rule graphs, investable outputs, and metric contracts.",
    },
    {
        "domain": "Theseus local",
        "title": "Claim extractor implementation",
        "path": "noosphere/noosphere/claim_extractor.py",
        "use": "Shows the JSON claim/principle extraction contract and external-claim filtering.",
    },
    {
        "domain": "Theseus local",
        "title": "Embedding pipeline implementation",
        "path": "noosphere/noosphere/embedding_pipeline.py",
        "use": "Shows how source text is embedded and written into the canonical store.",
    },
    {
        "domain": "Theseus local",
        "title": "Canonical contradiction engine",
        "path": "noosphere/noosphere/coherence/contradiction_engine.py",
        "use": "Householder reflection, Hoyer sparsity, reliability calibration, and limits.",
    },
    {
        "domain": "Theseus local",
        "title": "Bayesian Belief Layer",
        "path": "docs/methods/Bayesian_Belief_Layer.md",
        "use": "Derived Bayesian network over the cascade graph.",
    },
    {
        "domain": "Theseus local",
        "title": "QH Benchmark v1 Results",
        "path": "docs/research/QH_Benchmark_v1_Results.pdf",
        "use": "Empirical warning: firm contradiction geometry underperformed on accuracy in the first run.",
    },
    {
        "domain": "Theseus local",
        "title": "Householder Ablation",
        "path": "docs/research/Householder_Ablation.pdf",
        "use": "Empirical warning: the ablation was zero-power under the frozen threshold.",
    },
]


ARXIV_RE = re.compile(r"https://arxiv\.org/abs/([0-9.]+)")


def ensure_dirs() -> None:
    for path in [PDF_CACHE, HTML_CACHE, TEXT_CACHE, META_CACHE]:
        path.mkdir(parents=True, exist_ok=True)


def slug(text: str, max_len: int = 70) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    if len(value) > max_len:
        value = value[:max_len].rstrip("_")
    return value or hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def pdf_download_url(src: dict[str, str]) -> str | None:
    if src.get("pdf_url"):
        return src["pdf_url"]
    url = src["url"]
    kind = src["kind"]
    match = ARXIV_RE.match(url)
    if kind == "arxiv" and match:
        return f"https://arxiv.org/pdf/{match.group(1)}"
    if kind == "pdf":
        return url
    if kind == "acl":
        return url.rstrip("/") + ".pdf"
    if kind == "neurips":
        return (
            "https://proceedings.neurips.cc/paper_files/paper/2013/file/"
            "1cecc7a77928ca8133fa24680a88d2f9-Paper.pdf"
        )
    return None


def clean_html_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def fetch(src: dict[str, str]) -> dict[str, object]:
    result: dict[str, object] = {
        "domain": src["domain"],
        "title": src["title"],
        "url": src["url"],
        "kind": src["kind"],
        "use": src["use"],
        "status": "not-started",
        "cache_path": "",
        "pdf_pages": "",
        "error": "",
    }

    if src["kind"] == "video":
        result["status"] = "metadata-only"
        result["error"] = "Video source; not downloaded as PDF."
        return result

    headers = {"User-Agent": USER_AGENT}
    pdf_url = pdf_download_url(src)
    file_stem = f"{slug(src['domain'])}__{slug(src['title'])}"

    if pdf_url:
        target = PDF_CACHE / f"{file_stem}.pdf"
        try:
            if not target.exists() or target.stat().st_size < 1000:
                response = requests.get(pdf_url, headers=headers, timeout=60)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if "pdf" not in content_type and not response.content.startswith(b"%PDF"):
                    raise RuntimeError(f"expected PDF, got {content_type or 'unknown content-type'}")
                target.write_bytes(response.content)
                time.sleep(0.4)
            result["status"] = "cached-pdf"
            result["cache_path"] = str(target.relative_to(OUT))
            try:
                doc = fitz.open(target)
                result["pdf_pages"] = doc.page_count
                doc.close()
            except Exception as exc:  # noqa: BLE001
                result["error"] = f"PDF cached but page count failed: {exc}"
            return result
        except Exception as exc:  # noqa: BLE001
            result["status"] = "pdf-failed"
            result["error"] = str(exc)

    try:
        response = requests.get(src["url"], headers=headers, timeout=45)
        response.raise_for_status()
        html_target = HTML_CACHE / f"{file_stem}.html"
        txt_target = TEXT_CACHE / f"{file_stem}.txt"
        html_target.write_bytes(response.content)
        txt_target.write_text(clean_html_text(response.text), encoding="utf-8")
        result["status"] = "cached-html"
        result["cache_path"] = str(txt_target.relative_to(OUT))
        time.sleep(0.2)
        return result
    except Exception as exc:  # noqa: BLE001
        if result["status"] == "pdf-failed":
            result["error"] += f"; html fallback failed: {exc}"
        else:
            result["status"] = "failed"
            result["error"] = str(exc)
        return result


def write_manifest(results: list[dict[str, object]]) -> None:
    lines = [
        "# Noosphere Technical Reader Source Manifest",
        "",
        "This manifest records official source-cache attempts for the continuous reader.",
        "The reader paraphrases and teaches the ideas; it does not republish full copyrighted source texts.",
        "",
        "## Cached web/PDF sources",
        "",
        "| Domain | Source | Status | Cache | Pages | Use | URL |",
        "| --- | --- | --- | --- | ---: | --- | --- |",
    ]
    for row in results:
        lines.append(
            "| {domain} | {title} | {status} | {cache_path} | {pages} | {use} | {url} |".format(
                domain=md(row["domain"]),
                title=md(row["title"]),
                status=md(row["status"]),
                cache_path=md(row.get("cache_path", "")),
                pages=md(row.get("pdf_pages", "")),
                use=md(row["use"]),
                url=md(row["url"]),
            )
        )
    lines += [
        "",
        "## Local Theseus sources used",
        "",
        "| Domain | Source | Path | Use |",
        "| --- | --- | --- | --- |",
    ]
    for row in LOCAL_SOURCES:
        lines.append(
            f"| {md(row['domain'])} | {md(row['title'])} | {md(row['path'])} | {md(row['use'])} |"
        )
    (OUT / "source_manifest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (META_CACHE / "source_manifest.json").write_text(
        json.dumps({"web_sources": results, "local_sources": LOCAL_SOURCES}, indent=2),
        encoding="utf-8",
    )


def md(value: object) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


LATEX_ESCAPE = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def tex_escape(value: object) -> str:
    text = "" if value is None else str(value)
    return "".join(LATEX_ESCAPE.get(ch, ch) for ch in text)


READER_PREFIX = r"""
\documentclass[11pt]{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage[margin=0.82in]{geometry}
\usepackage{microtype}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{array}
\usepackage{enumitem}
\usepackage{xcolor}
\usepackage[most]{tcolorbox}
\usepackage{hyperref}
\usepackage{amsmath}
\hypersetup{colorlinks=true,linkcolor=blue!45!black,urlcolor=blue!45!black,citecolor=blue!45!black}
\setlist[itemize]{leftmargin=1.3em,itemsep=0.18em,topsep=0.25em}
\setlist[enumerate]{leftmargin=1.5em,itemsep=0.18em,topsep=0.25em}
\newtcolorbox{readerbox}[1]{colback=gray!4,colframe=gray!45!black,title=#1,arc=1.5mm,boxrule=0.4pt,left=1.2mm,right=1.2mm,top=1mm,bottom=1mm}
\newcommand{\code}[1]{\texttt{#1}}
\newcommand{\sourcehref}[2]{\href{#1}{#2}}
\title{\textbf{Noosphere Technical Reader}\\\large LLMs, Embedding Geometry, NLP Extraction, Knowledge Graphs, and Coherence-Based Intellectual Capital Modeling}
\author{Prepared for Michael Quintin / Theseus}
\date{May 17, 2026}
\begin{document}
\maketitle
\tableofcontents
\newpage

\section{What This Packet Is}

This reader turns the linked technical reading list into a single continuous
study document. It is not a pasted anthology. Most of the source material is
copyrighted even when it is publicly readable, so the main body is a synthesized
walk-through: it teaches the ideas, cites the source trail, and tells you where
the official PDF or page was cached when available. The source cache and the
manifest live beside this PDF.

\begin{readerbox}{Core claim}
Noosphere is easiest to understand as a pipeline that turns text into typed
propositions, embeds those propositions into vector space, places them in a
graph of support and conflict, and then asks whether the resulting structure is
coherent enough to support a conclusion or decision.
\end{readerbox}

\subsection{The Four Substrates}

The source guide divides the background into four domains, and that division is
correct:

\begin{enumerate}
\item \textbf{The LLM substrate.} Claude or another model extracts claims,
distills principles, judges coherence layers, and writes explanations. The model
is not a neutral parser. Its transformer architecture, alignment training, and
prompt interface shape the outputs.
\item \textbf{The embedding substrate.} Claims and principles become high
dimensional vectors. Noosphere's geometric hypothesis is that relations such as
similarity, contradiction, truth, and coherence leave measurable structure in
those vectors or in differences between them.
\item \textbf{The NLP extraction substrate.} Raw text must be segmented,
attributed, disambiguated, and transformed into atomic truth-apt claims before a
graph can be trusted.
\item \textbf{The graph and logic substrate.} The knowledge store is not only a
bag of embeddings. It is a graph of claims, conclusions, supports, refutations,
dependencies, revisions, and derived probabilistic views.
\end{enumerate}

\section{Noosphere as a System}

The local Theseus repository defines the project as a machine for extracting
principles from a curated corpus, running algorithms over those principles, and
making conclusions or bets accountable to downstream evidence. In repository
terms, \code{theseus-codex} is the workspace and public face, \code{noosphere}
is the reasoning engine, and \code{dialectic} is the live conversation analyzer.

\subsection{The Actual Data Shape}

The fundamental unit in \code{noosphere/noosphere/models.py} is a \textbf{Claim}:
an atomic proposition extracted from text, attributed to a speaker, and
optionally positioned in embedding space. Relations between claims and
principles include support, contradiction, refinement, instantiation, extension,
analogy, presupposition, and qualification.

\begin{readerbox}{Why this matters}
If claim extraction is wrong, every downstream graph and coherence score is
contaminated. If embeddings are stale, geometry-based scores drift. If graph
edges are under-specified, the public explanation can look rigorous while the
actual decision trace is underspecified. Noosphere's engineering problem is to
make each of those failure modes visible.
\end{readerbox}

\subsection{Operational Pipeline}

The software path can be read as:

\begin{enumerate}
\item \textbf{Source ingestion.} Text enters as chunks with metadata and
provenance.
\item \textbf{Claim extraction.} \code{ClaimExtractor} asks an LLM for JSON
containing truth-apt claims, claim type, hedges, evidence pointers, and whether
the author actually endorses the claim.
\item \textbf{Principle extraction.} Later extraction turns source spans into
principle-shaped decision rules with domains of applicability, proxies, and
examples.
\item \textbf{Embedding.} \code{embedding_pipeline.py} idempotently embeds source
text, records the model name and text hash, writes vectors into the store, and
updates locality indices for claims and conclusions.
\item \textbf{Graph construction.} The cascade graph records nodes and edges
such as supports, refutes, contradicts, depends on, specializes, generalizes,
coheres with, predicts, and extracted from.
\item \textbf{Coherence and contradiction.} Pairwise checks and contradiction
engines score whether claims cohere, conflict, or remain unresolved.
\item \textbf{Trace generation.} Algorithmized decisions must record named
metrics, rule graph nodes, vetoes, and outputs. The prose explanation is
secondary; the trace is the source of truth.
\end{enumerate}

\section{LLMs: From Next Tokens to Reasoning Instruments}

\subsection{The Basic Transformer Picture}

The transformer is a differentiable architecture for contextual sequence
processing. Tokens enter as vectors. Each layer lets tokens read from other
tokens through attention, then transforms the result through feed-forward
networks. The original architecture is in
\sourcehref{https://arxiv.org/abs/1706.03762}{Vaswani et al.}; Jay Alammar's
\sourcehref{https://jalammar.github.io/illustrated-transformer/}{Illustrated
Transformer} is still the best first visual pass; Karpathy's GPT walkthrough is
the best bridge from diagram to executable code.

The minimum mental model is:

\begin{itemize}
\item A token embedding is a learned vector representing a symbol in context.
\item Self-attention computes weighted mixtures of other token representations.
\item Query, key, and value projections are learned views of each token. Query
and key determine which tokens attend to each other; value carries the content
to mix.
\item Layer normalization, residual connections, and feed-forward blocks make
deep composition trainable.
\item A language model is trained to predict the next token, but the internal
representations needed to do this become useful general-purpose features.
\end{itemize}

\subsection{Why Scale Matters}

Kaplan et al. made scaling laws a central part of LLM engineering: loss changes
predictably with model size, dataset size, and compute. Hoffmann et al.'s
Chinchilla work corrected the naive lesson by showing that more parameters are
not enough; compute-optimal training requires enough data for the model size.
For Noosphere, the point is not merely that larger models are better. It is that
model behavior is partly a function of scaling regime, not only prompt wording.

This matters for intellectual-capital modeling because a claim extractor using
a frontier model and one using a small local model are not just two
implementations of the same parser. They may differ in entity resolution,
implicit premise recovery, sensitivity to hedges, and willingness to infer
structure not explicitly stated.

\subsection{Alignment Changes the Instrument}

Instruction tuning and RLHF, as in the InstructGPT paper, alter the interface
between raw next-token prediction and user-facing behavior. Constitutional AI
adds another layer: model behavior is shaped by critique, revision, and
principle-guided feedback. That is useful, but it means a model used inside
Noosphere carries inherited priors about harmlessness, helpfulness, refusal,
uncertainty, and argumentative framing.

\begin{readerbox}{Practical implication}
When Claude extracts a claim or judges a contradiction, it is not an inert
semantic microscope. It is an aligned language model. Noosphere should therefore
log prompts, model versions, schema versions, and failure modes so that later
methodology review can distinguish source truth from model-induced structure.
\end{readerbox}

\section{Embeddings: Semantic Objects in Vector Space}

\subsection{From Word2vec to Sentence Embeddings}

Word2vec made the modern intuition vivid: learned vectors can encode semantic
regularities. GloVe made the co-occurrence matrix factorization view explicit.
Jurafsky and Martin's Chapter 6 is the clean textbook path through PPMI, SVD,
word2vec, GloVe, and evaluation. Sentence-BERT then moves the operational unit
from isolated words to whole sentences or short paragraphs, which is closer to
Noosphere's claims and principles.

The crucial shift is this: once propositions are vectors, reasoning systems can
query neighborhoods, compare directions, estimate distances, and cluster
meaning. But every one of those operations depends on the embedding model, the
text span, the normalization, and the metric.

\subsection{Cosine Is Useful but Not Enough}

Cosine similarity measures angle, not logical relation. Two contradictory
sentences can have high cosine similarity because they discuss the same topic
with almost the same words. This is the ``cosine paradox'' behind Theseus's
internal contradiction-geometry work. If contradiction is topic-local, then raw
similarity can confuse opposition with agreement.

Noosphere's geometry rationale therefore looks at \textbf{difference vectors}
and \textbf{Hoyer sparsity}. If two claims differ along a small number of
meaning-bearing dimensions, the difference vector may concentrate mass in those
dimensions. Hoyer sparsity is a scalar in $[0,1]$ that is low for dense vectors
and high for vectors whose mass is concentrated.

\subsection{Manifolds, Symmetry, and Linear Directions}

Bronstein et al.'s geometric deep learning monograph broadens the picture: deep
learning architectures can be read as ways to exploit symmetries in the domain.
Convolution exploits translation symmetry on grids. Graph neural networks
exploit permutation structure on graphs. Transformers can be read in the same
general family of symmetry-aware architectures.

The manifold hypothesis, treated rigorously by Fefferman, Mitter, and
Narayanan, supplies a related intuition: high-dimensional data often lies near a
lower-dimensional structure. For Noosphere, the speculative version is that
``meaning'' may occupy structured regions inside an embedding or activation
space rather than filling the ambient dimension uniformly.

The Linear Representation Hypothesis and work such as Geometry of Truth,
Contrast-Consistent Search, Inference-Time Intervention, and Representation
Engineering then ask whether concepts and truth-related properties can be
represented as directions. If this is right, a coherence or contradiction
detector can search for directions or subspaces. If it is wrong or only locally
true, direction-based methods will overstate what the geometry can support.

\section{The Noosphere Geometry Hypothesis}

The local contradiction engine records the strongest version of the firm's
geometric bet. It estimates a learned contradiction direction, reflects one
embedding across a hyperplane using a Householder transform,
\[
  b' = b - 2(b \cdot \hat d)\hat d,
\]
then scores Hoyer sparsity of $b' - a$. The method version is recorded as
\code{geometry/householder/v2}, with a reliability curve and confidence band.

This is an ambitious hypothesis. It is not yet a proven theorem or a mature
benchmark result.

\subsection{What the Internal Evidence Actually Says}

The local QH benchmark results are deliberately important because they prevent
the reader from absorbing only the optimistic part of the source list. The first
QH-v1 run reported that the firm contradiction-geometry probe lost on overall
3-way accuracy to cosine and even to a random baseline, while still showing a
better AUROC slice for contradicting versus coherent. The Householder ablation
then found a zero-power label test under the frozen threshold: all variants
predicted the same label, so the run could neither justify removing nor
confirming the Householder step.

\begin{readerbox}{Rigorous reading}
The current evidence supports continued experimentation, not triumphal claims.
The geometry may contain useful signal, but the production argument must pass
through calibration, benchmark design, ablations with power, and cross-model
replication before it can be treated as a reliable contradiction detector.
\end{readerbox}

\section{NLP Extraction: Turning Text into Claims}

\subsection{Classical Pipeline}

Noosphere needs more than embeddings. It must decide what the text says, who
says it, whether the author endorses it, and how claims relate. Classical NLP
still matters here:

\begin{itemize}
\item Tokenization and sentence segmentation decide the units of analysis.
\item Part-of-speech and dependency parsing expose grammatical structure.
\item Named-entity recognition finds people, organizations, concepts, and
places.
\item Coreference resolution decides when ``the founder,'' ``he,'' and a proper
name refer to the same entity.
\item Relation extraction converts text into typed edges.
\end{itemize}

spaCy and NLTK are included in the source guide because even an LLM-backed
system benefits from knowing what older pipeline components do. Jurafsky and
Martin's information-extraction chapter is the cleanest compact technical
reference.

\subsection{Modern Extraction}

BERT shifted extraction by making pretrained contextual encoders standard.
REBEL and neural relation extraction show how relation triples can be generated
or classified from text. LLM-based extraction adds flexibility but also danger:
the model can infer plausible structure that was not asserted, merge distinct
claims, lose hedges, or fail to preserve speaker attribution.

The local \code{ClaimExtractor} is designed around exactly that risk. Its prompt
requires JSON, distinguishes author assertions from external or opposing claims,
and attaches hedges and evidence pointers. It explicitly tries to avoid
polluting founder beliefs with prompts, counterpositions, or rhetorical
questions that the author is merely engaging.

\subsection{Argument Mining}

Argument mining is the closest established field to Noosphere's higher-level
principle extraction. Stab and Gurevych's work on claims, premises, and support
relations matters because Noosphere's graph needs typed argumentative edges, not
just semantic similarity. A good extraction system must know the difference
between:

\begin{itemize}
\item a claim,
\item evidence for a claim,
\item a premise in an argument,
\item a qualification,
\item an objection,
\item an example, and
\item a stronger principle abstracted from several claims.
\end{itemize}

\section{Knowledge Graphs and Cascade Structure}

\subsection{Why a Graph Is Necessary}

Embeddings give soft geometry. Graphs give inspectable structure. A knowledge
graph can represent identity, provenance, support, contradiction, abstraction,
and dependency. Hogan et al. provide the reference survey; NetworkX supplies the
implementation vocabulary; Diestel supplies the formal graph-theory background.

The local \code{CascadeGraph} is not a generic graph toy. It enforces conflict
rules, prevents cycles for dependency edges, attaches method invocation
provenance to edges, and supports deterministic projection into a Bayesian
skeleton.

\subsection{KG Embeddings}

TransE begins with a simple geometric idea: a relation can act like a
translation from head entity to tail entity. Later KG-embedding models complicate
this with different spaces, scoring functions, rotations, complex embeddings,
and auxiliary text. For Noosphere, the point is less that TransE should be
copied and more that graph structure and vector structure can be coupled.

This is the natural bridge between a symbolic graph of claims and an embedding
space of meanings. It also introduces a warning: graph embeddings optimize for
link prediction, not necessarily for philosophical coherence or truth.

\section{Logic, Contradiction, and Belief Revision}

\subsection{Classical Logic Is Not Enough}

If a system stores live human beliefs, contradictions will appear. Classical
logic contains the principle of explosion: from a contradiction, anything can
follow. That is unacceptable for a practical knowledge system. Paraconsistent
logic is therefore not an exotic side topic; it is one way to reason in a graph
that can contain unresolved conflict without collapsing.

Mereology matters because principles can be composed from parts and wholes.
Belief revision matters because source retractions and new evidence should
change stored belief in a controlled way. Description logic matters if the
ontology becomes formal enough to use OWL-like classes, subsumption, and
satisfiability.

\subsection{Bayesian Derived Views}

The local Bayesian Belief Layer makes the same distinction carefully: the
cascade remains the primary representation, while the Bayesian network is a
derived view rebuilt on demand. It turns an acyclic skeleton into binary
truth-valued nodes with conditional probability tables, then supports marginal
probabilities, evidence updates, and sensitivity analysis.

That is exactly the right caution. A posterior probability is useful only when
the model structure and CPTs are honest about what they assume. Noosphere's
specification keeps the BN founder-side, reports exact versus approximate
inference, and distinguishes seeded rows from data-fit rows.

\section{Coherence: Philosophy and Computation}

\subsection{Coherence as Justification vs Coherence as Truth}

The Stanford Encyclopedia entries separate two claims that are easy to conflate.
Coherentism about justification says a belief is justified by its role in a
mutually supporting system. The coherence theory of truth says truth itself is a
matter of coherence among beliefs. Noosphere should be extremely careful here.

A coherence score may be evidence that a belief fits the firm's corpus. It is
not automatically evidence that the belief is true. Bovens and Hartmann's work,
Olsson's critique of coherentism, and Thagard's computational coherentism all
push against naive equations of coherence with probability or truth.

\subsection{Six-Layer Coherence}

The local six-layer method combines:

\begin{enumerate}
\item NLI consistency,
\item abstract argumentation,
\item probabilistic coherence,
\item embedding geometry,
\item information-theoretic compression, and
\item an LLM judge.
\end{enumerate}

The aggregator requires a 4-of-6 supermajority for a definitive cohere or
contradict verdict. That design is sensible as a hedge against any single weak
signal, but the local rationale correctly names the weakness: layers are not
fully independent. NLI and geometry can share embedding failure modes; the
probabilistic layer and LLM judge can share model-induced reasoning failure
modes. Supermajority only helps when errors are not too correlated.

\section{From Reasoning to Decisions}

\subsection{Trace Before Prose}

The Algorithmized Decision Making document states the right contract: prose is
generated from the trace, not the other way around. The trace must contain named
metrics, typed values, low-confidence flags, method versions, rule graph nodes,
vetoes, and the final output.

For intellectual-capital modeling, this is the difference between an essay that
sounds rigorous and a decision that can be audited. A forecast or investment
candidate should be reconstructible from:

\begin{itemize}
\item the market or question,
\item the event representation,
\item the corpus slice,
\item the active principles,
\item calibration state,
\item liquidity/cost data where relevant,
\item metric values,
\item rule graph version, and
\item vetoes considered.
\end{itemize}

\subsection{The Correct Liability Ladder}

Theseus's architecture draws a useful ladder:

\begin{center}
\begin{tabular}{lll}
\toprule
Layer & Output & Primary judge \\
\midrule
Interpretive reasoning & Essay or conclusion & Reader review \\
Decision trace & Data structure & Algorithmic audit \\
Investable output & Action or abstention & Market outcome \\
\bottomrule
\end{tabular}
\end{center}

Each step removes prose freedom and increases accountability. That is the
engineering core of ``intellectual capital modeling'': principles are not just
stored ideas; they become constrained inputs to traceable decisions.

\section{Frontier Research Map}

\subsection{Mechanistic Interpretability}

Transformer circuits work asks what computation the model actually performs.
Superposition says features may share neurons or directions, which makes clean
linear interpretations dangerous. Sparse autoencoder work tries to recover more
monosemantic features. Induction-head work is important because it is one of the
few cases where a behavior has been tied to identifiable mechanism.

For Noosphere, this literature supplies both hope and constraint. Hope: models
do contain internal structure that can sometimes be decomposed. Constraint:
surface embeddings and activation directions can be polysemantic, basis-
dependent, layer-dependent, and prompt-sensitive.

\subsection{Representation Engineering}

Representation engineering treats activations as a control surface: identify
directions, test whether they correspond to concepts, and intervene. This is
adjacent to the Quintin Hypothesis because both ask whether abstract semantic
properties have geometric structure. The difference is that representation
engineering usually works inside model activations, while many Noosphere
methods operate on external text embeddings or stored claim vectors.

\subsection{KG and LLM Convergence}

The 2023-2025 KG/LLM survey literature frames three broad patterns:

\begin{itemize}
\item KGs can enhance LLMs by supplying explicit facts, retrieval context, and
interpretability handles.
\item LLMs can augment KGs by extracting entities, relations, ontologies, and
candidate edges.
\item Hybrid systems can use LLMs and KGs in a loop, where explicit graph state
and parametric model state correct each other.
\end{itemize}

Noosphere is squarely in the hybrid category. Its risk is also the hybrid
category's risk: generated graph edges can look explicit while inheriting hidden
LLM uncertainty, and LLM answers can look grounded while leaning on parametric
knowledge not present in the graph.

\section{A One-Go Reading Path}

\subsection{Pass 1: Build the Skeleton}

\begin{enumerate}
\item 3Blue1Brown Essence of Linear Algebra.
\item Alammar's Illustrated Transformer.
\item Karpathy's GPT-from-scratch video.
\item Jurafsky and Martin Chapter 6.
\item Hogan et al. Knowledge Graphs, introductory sections.
\end{enumerate}

\subsection{Pass 2: Understand Noosphere's Moving Parts}

\begin{enumerate}
\item Read the local Theseus README.
\item Read \code{claim_extractor.py} and the source manifest notes.
\item Read \code{embedding_pipeline.py}.
\item Read the six-layer coherence rationale.
\item Read the contradiction-geometry rationale, then the QH benchmark and
Householder ablation summaries.
\item Read Algorithmized Decision Making, especially the trace/rule-graph
contract.
\end{enumerate}

\subsection{Pass 3: Enter the Frontier}

\begin{enumerate}
\item Linear Representation Hypothesis.
\item Geometry of Truth.
\item Discovering Latent Knowledge without Supervision.
\item Inference-Time Intervention.
\item Representation Engineering.
\item Toy Models of Superposition.
\item Scaling Monosemanticity.
\end{enumerate}

\subsection{Pass 4: Build the Critique}

\begin{enumerate}
\item SEP on coherentist justification and coherence theory of truth.
\item Paraconsistent logic.
\item Belief revision.
\item Thagard's coherence-as-constraint-satisfaction work.
\item Bovens, Hartmann, Olsson, and BonJour if you have library access.
\end{enumerate}

\section{Concept Glossary}

\begin{description}
\item[Activation] A vector inside a neural network layer, often more directly
analyzable than the final output.
\item[Attention] A learned operation letting one token representation read
from others.
\item[Cascade graph] Theseus's primary support/refutation/dependency structure
over claims, conclusions, principles, and artifacts.
\item[Claim] An atomic truth-apt proposition extracted from text.
\item[Coherence] Fit among claims in a system. It may justify a belief without
proving it true.
\item[Contradiction direction] A learned or fallback vector estimating where an
embedding's negating counterpart should lie.
\item[Embedding] A vector representation of text or another object.
\item[Hoyer sparsity] A scalar measuring whether vector mass is concentrated in
few coordinates.
\item[Knowledge graph] A graph representation of entities, relations, context,
identity, and provenance.
\item[LLM alignment] Training and feedback processes that make a model follow
instructions and norms rather than merely continue text.
\item[Paraconsistent logic] A logic family that can tolerate contradictions
without deriving everything.
\item[Principle] A reusable decision rule or general claim distilled from
source material.
\item[Representation engineering] Identifying and intervening on model
activation directions associated with concepts.
\item[Rule graph] A versioned graph of thresholds, combiners, buckets, and
vetoes used to turn metrics into decisions.
\item[Superposition] The phenomenon where multiple features share representa-
tional dimensions.
\end{description}

"""


READER_SUFFIX = r"""

\section{Closing Synthesis}

The deepest question behind Noosphere is not whether LLMs can write plausible
summaries. They can. The question is whether a system can turn interpreted text
into a durable, auditable, and empirically disciplined model of intellectual
capital.

The strongest version of the architecture is a hybrid:

\begin{itemize}
\item LLMs do high-recall linguistic work, but schema validation and provenance
discipline prevent them from silently authoring the knowledge base.
\item Embeddings supply soft geometry, but benchmarked calibration prevents
cosine or sparsity from being mistaken for logic.
\item Graphs make support, contradiction, and dependency inspectable, but
probabilistic and paraconsistent layers prevent the graph from pretending to be
cleaner than it is.
\item Decision traces turn principles into accountable computations, while
market or forecast outcomes provide calibration pressure.
\end{itemize}

The source literature makes this project plausible. The local benchmark
documents make it intellectually honest: the geometric hypothesis is promising,
but not yet vindicated. The rigorous path forward is not to weaken the claim
into a vague metaphor. It is to keep the claim sharp enough that benchmarks,
ablations, source retractions, and failed forecasts can actually wound it.

\end{document}
"""


def write_reader_tex(results: list[dict[str, object]]) -> None:
    table = [
        r"\section{Source Inventory}",
        "",
        "The following table records what was cached and how each source was used.",
        "Rows marked as HTML are saved as cleaned text in the cache; rows marked as PDF include page counts when PyMuPDF could read the file.",
        "",
        r"\small",
        r"\begin{longtable}{p{0.16\linewidth}p{0.25\linewidth}p{0.13\linewidth}p{0.32\linewidth}}",
        r"\toprule",
        r"Domain & Source & Status & Reader use \\",
        r"\midrule",
        r"\endfirsthead",
        r"\toprule",
        r"Domain & Source & Status & Reader use \\",
        r"\midrule",
        r"\endhead",
    ]
    for row in results:
        status = str(row["status"])
        pages = row.get("pdf_pages", "")
        if pages:
            status = f"{status}; {pages} pp"
        table.append(
            "{} & {} & {} & {} \\\\".format(
                tex_escape(row["domain"]),
                tex_escape(row["title"]),
                tex_escape(status),
                tex_escape(row["use"]),
            )
        )
    for row in LOCAL_SOURCES:
        table.append(
            "{} & {} & {} & {} \\\\".format(
                tex_escape(row["domain"]),
                tex_escape(row["title"]),
                tex_escape("local"),
                tex_escape(row["use"]),
            )
        )
    table += [r"\bottomrule", r"\end{longtable}", r"\normalsize", ""]
    tex = READER_PREFIX + "\n".join(table) + READER_SUFFIX
    (OUT / "Noosphere_Technical_Reader.tex").write_text(tex, encoding="utf-8")


def main() -> None:
    ensure_dirs()
    results: list[dict[str, object]] = []
    for idx, src in enumerate(SOURCES, 1):
        print(f"[{idx:02d}/{len(SOURCES):02d}] {src['title']}")
        results.append(fetch(src))
    write_manifest(results)
    write_reader_tex(results)
    print(f"Wrote {(OUT / 'source_manifest.md').relative_to(ROOT)}")
    print(f"Wrote {(OUT / 'Noosphere_Technical_Reader.tex').relative_to(ROOT)}")


if __name__ == "__main__":
    main()

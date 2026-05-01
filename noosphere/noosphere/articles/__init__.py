"""Generated longform articles and transcript enrichment utilities."""

__all__ = ["Article", "ArticleKind", "generate_article"]


def __getattr__(name: str):
    if name in __all__:
        from noosphere.articles.generator import Article, ArticleKind, generate_article

        exports = {
            "Article": Article,
            "ArticleKind": ArticleKind,
            "generate_article": generate_article,
        }
        return exports[name]
    raise AttributeError(name)

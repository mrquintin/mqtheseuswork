# Fixture: doc with broken links

This file exists only as a test fixture for
`scripts/check_doc_freshness.py`. It deliberately links to paths
that do not exist; the test asserts the freshness check catches
each one.

- A broken relative link: [missing](./does_not_exist.md)
- A broken image: ![nope](./missing_image.png)
- A broken absolute link: [also missing](/this/path/is/not/in/the/repo.md)

External links should be ignored:

- [Anthropic](https://www.anthropic.com)
- [anchor only](#some-section)

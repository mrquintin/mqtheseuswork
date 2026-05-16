"""Load-bearing safety regression suite.

Every safety property the firm has shipped (eight-gate contract,
trigger-predicate sandbox, verbatim citation discipline, no-network
in tests, no-PII in logs, no-credential in output) has a dedicated
regression test here. A failure in this suite blocks the sync.

See ``docs/security/SAFETY_PROPERTIES.md`` for the threat model behind
each test and the procedure for amending any of the underlying
properties.
"""

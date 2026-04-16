# Coordinated disclosure — Theseus Researcher API

We want methodological attacks **reported to us before they are weaponized in the wild**.

## Scope

- Cross-tenant data isolation, authentication, and rate-limit bypasses on the Researcher API.
- Attacks that extract or mutate **another** researcher’s sandbox data.
- Systemic manipulation of shared methodology (coherence, embeddings, calibration) when exercised through the API in ways that violate the acceptable-use policy but still constitute credible security or integrity findings.

Out of scope: disagreements with philosophical conclusions, generic LLM jailbreaks unrelated to Theseus-specific surfaces, or spam.

## How to report

Email the operators who issued your API key (or `security@` your deployment uses). Include:

- Endpoint(s), request shape (redacted where needed), and timestamps with `X-Theseus-API-Version` / `X-Theseus-Git-SHA` from responses.
- Minimal reproduction steps.
- Impact assessment and whether you believe other tenants are affected.

## Timelines (intent)

| Stage | Target |
|-------|--------|
| Acknowledgment | 72 hours |
| Fix, mitigation, or documented accepted-risk decision | 30 days |
| Public credit | At your request after resolution |

## Bug bounty

A modest bounty may be offered for **confirmed novel** attacks that compromise tenant isolation or authentication. Amounts are at operator discretion and require a clear write-up suitable for the internal Robustness Ledger.

## Safe harbor

Do not access data you are not authorized to access. Do not perform destructive tests against production tenants without prior written approval.

# QingYuan AML · Anti-Money-Laundering Monitoring Platform (Demo MVP)

> Every alert conclusion can be traced back to the exact clause of Chinese AML regulations.
> **Demo system · All data is synthetic and de-identified · For learning purposes only**

A single-person-built, fully runnable demo MVP of an AML monitoring platform for small banks
and payment institutions in China: a **rule engine** keeps the compliance baseline, an
**AI diagnosis layer** drafts conclusions (never touching raw customer data), and every
STR report element is traceable to the official regulation text.

**[中文文档（完整版）请看 README.md](README.md)** · Product spec: [docs/PRD.md](docs/PRD.md)

## Highlights

- **Rule engine with legal traceability** — 17 rules defined (10 executable: R001–R009 + R017),
  each mapped to specific clauses of PBOC Decree No.3 〔2016〕3, the 2025 AML Law, and the
  official *Suspicious Transaction Types & Identification Points* table. A 4-layer trace
  panel links every alert: rule → regulation text → official type identification point →
  penalty reference.
- **62-element STR report** — full element set of Decree No.3 Annex (banking), with per-element
  provenance labels (system / demo-prefilled / AI-generated for elements 21–22 only / N-A),
  bilingual CN/EN narrative, revision history, 3-level authorization (maker/checker/approver)
  and a submission ledger with **server-generated receipt numbers**.
- **Tamper-evident audit chain** — append-only log protected by SQLite triggers plus a
  SHA256 hash chain with server-side millisecond timestamps (+08:00) and monotonic sequence
  numbers. One-click full-chain replay verification; tampering is detectable even if the
  database file is modified directly. Read operations that touch sensitive data (sanction
  screening, CDD queries, archived-case views) are also logged; ID numbers are masked.
- **Honest AI boundary** — AI only sees structured rule-engine features, never raw data;
  the legal reporting action never passes through AI. Mock provider (pre-verified results,
  zero token) by default; Live provider (OpenAI-compatible, e.g. DeepSeek) behind an
  output-schema guardrail (invalid model output is rejected and retried, never leaks into
  reports). The UI always labels which provider produced a conclusion.
- **CDD demo window** — corporate due diligence and personal identity verification with
  *real* checksum algorithms (GB 11643 for PRC ID numbers, GB 32100 for Unified Social
  Credit Codes), 3 synthetic companies, and a placeholder provider for Qichacha API
  (reports "not connected" honestly when unconfigured — never fakes a real check).
- **Never overclaims** — element 24 (suspicious-feature code) stays empty because the
  official code table is not integrated; the XML export is labeled "draft, not
  XSD-validated"; read-only mode for public demos is fail-closed.

## Quick start

```bash
./run.sh          # installs deps if missing, initializes SQLite, starts on 127.0.0.1:8000
# open http://127.0.0.1:8000

QINGYUAN_READ_ONLY=1 ./run.sh    # public demo: read-only, all write APIs blocked
```

Requires Python ≥ 3.10. To plug in a real LLM: `cp .env.example .env`, set
`AML_AI_PROVIDER=live` + `OPENAI_API_KEY` (DeepSeek is pay-per-token, a few CNY covers
the whole demo).

## Architecture

```
Native JS SPA (9 pages, no build step)
  └── FastAPI backend (backend/main.py)
        ├── domain/rules/        rule engine, thresholds from DB params
        ├── ai_diagnosis.py      Mock / Live dual provider + output guardrail
        ├── domain/cases/        char n-gram TF-IDF + structural features (no vector DB)
        ├── domain/report/       62-element STR builder + bilingual text + deadline
        ├── services/cdd.py      CDD providers (real GB checksum algorithms)
        ├── infra/audit.py       append-only SHA256 audit chain
        └── SQLite               8 regulations / 239 clauses (FTS5 trigram) + ledger
                                 + qualified-case library + audit_log
Demo cases live in a standalone JSON (17 synthetic cases, dataset demo v1.1).
```

## Tests

```bash
python3 tests/run_all.py   # similarity 6 + linkage 7 + audit-chain 7 + API contract 16
                           # + browser E2E 26 + auth state machine 31
```

Audit-chain tests include tamper detection *after bypassing the triggers* (direct DB
mutation), seq-gap deletion detection, and read-only mode behavior. API contract tests
cover server receipt numbers, idempotency by report number, 422 on type confusion,
supersedes-authorization checks, and the privacy red line (ID numbers masked in audit).

## Honest boundary (what this is NOT)

| Not implemented | Why |
|---|---|
| CAMLMAC XML / XSD validation, official code tables | Requires the official interface spec distributed to institutions |
| PBOC dedicated line / front-end processor / digital certificates / real receipts | Institution onboarding only |
| Real sanction lists, public-security identity verification | Institution channels only (mock library of 3 entries, substring matching) |
| Production auth / RBAC | Out of MVP scope; audit actor is honestly labeled "unauthenticated" |
| Production database | Single-worker SQLite by design (demo); swap for PostgreSQL before any real load |

## License

MIT — see [LICENSE](LICENSE). This is a personal learning/demo project, not a certified
compliance system; all personas, cases and identifiers are synthetic.

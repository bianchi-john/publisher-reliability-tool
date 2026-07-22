# Requirements Traceability

**Status:** Normative MVP coverage map

Acceptance tests verify requirements but do not create requirements. Every
`AT-*` is mapped at least once below.

## Functional requirements

| Requirement | Acceptance tests |
| --- | --- |
| FR-001 | AT-001, AT-002, AT-003, AT-008 |
| FR-002 | AT-001, AT-002, AT-027, AT-028 |
| FR-003 | AT-002, AT-005, AT-076, AT-077, AT-093 |
| FR-004 | AT-009, AT-010, AT-018 |
| FR-005 | AT-007, AT-019, AT-021, AT-096 |
| FR-006 | AT-020, AT-023, AT-081 |
| FR-007 | AT-006, AT-034, AT-035, AT-038, AT-052, AT-059, AT-060, AT-061, AT-062, AT-063, AT-064, AT-065, AT-083, AT-091, AT-099 |
| FR-008 | AT-035, AT-039, AT-048, AT-053, AT-058, AT-084, AT-085 |
| FR-009 | AT-023, AT-048, AT-086, AT-090 |
| FR-010 | AT-036, AT-037, AT-042, AT-044, AT-085 |
| FR-011 | AT-048, AT-049, AT-050, AT-052, AT-053, AT-054, AT-058, AT-098 |
| FR-012 | AT-041, AT-051 |
| FR-013 | AT-047, AT-053, AT-055, AT-056, AT-057, AT-084, AT-098, AT-100 |
| FR-014 | AT-016, AT-049, AT-055, AT-058, AT-085 |
| FR-015 | AT-059, AT-060, AT-061, AT-062, AT-063, AT-064, AT-065 |
| FR-016 | AT-036, AT-048, AT-062, AT-066, AT-067, AT-068, AT-082, AT-085 |
| FR-017 | AT-063 |
| FR-018 | AT-003, AT-064, AT-065, AT-066, AT-067, AT-068, AT-069, AT-070, AT-091 |
| FR-019 | AT-006, AT-069, AT-070, AT-071, AT-072, AT-097 |
| FR-020 | AT-042, AT-045, AT-046 |
| FR-021 | AT-004, AT-033, AT-048, AT-086 |
| FR-022 | AT-011, AT-012, AT-013, AT-014, AT-015, AT-016, AT-087, AT-088, AT-095 |
| FR-023 | AT-029, AT-030 |
| FR-024 | AT-075 |
| FR-025 | AT-035, AT-036, AT-037, AT-038, AT-043, AT-083, AT-099 |
| FR-026 | AT-076, AT-077, AT-093 |
| FR-027 | AT-021, AT-022, AT-023, AT-024, AT-025, AT-026, AT-088, AT-089, AT-095, AT-096 |
| FR-028 | AT-003, AT-082, AT-083 |
| FR-029 | AT-031, AT-085, AT-092 |
| FR-030 | AT-004, AT-033, AT-089, AT-092 |
| FR-031 | AT-005, AT-013, AT-014, AT-017, AT-025, AT-072, AT-086, AT-087, AT-088, AT-089, AT-090 |

## Non-functional requirements

| Requirement | Acceptance tests |
| --- | --- |
| NFR-001 | AT-080 |
| NFR-002 | AT-019, AT-022, AT-023, AT-086 |
| NFR-003 | AT-033, AT-073, AT-074 |
| NFR-004 | AT-004 |
| NFR-005 | AT-010, AT-015, AT-040, AT-085 |
| NFR-006 | AT-038, AT-078, AT-081 |
| NFR-007 | AT-032, AT-048, AT-078, AT-086 |
| NFR-008 | AT-028 |
| NFR-009 | AT-032, AT-074, AT-079 |
| NFR-010 | AT-019, AT-027, AT-081, AT-082, AT-094 |

## Contract ownership and precedence

| Subject | Normative owner | Principal tests |
| --- | --- | --- |
| Product scope, workflows, UI, requirements | `product-specification.md` | AT-048–AT-058, AT-073–AT-075, AT-084–AT-086 |
| Scientific/model/input identity and formulas | `scientific-contract.md` | AT-045–AT-047, AT-059–AT-071, AT-082, AT-091, AT-096 |
| CSV persistence, recovery, retention | `csv-storage-contract.md` | AT-009–AT-018, AT-031, AT-087–AT-090, AT-095 |
| HTTP schemas, security, errors | `api-contract.md` | AT-027–AT-034, AT-084–AT-085, AT-092–AT-094, AT-097 |
| Native/container operation | `deployment.md` | AT-001–AT-008, AT-076–AT-083, AT-087–AT-089, AT-099 |
| Cross-cutting boundaries/invariants | `architecture.md` | AT-003–AT-005, AT-011–AT-018, AT-043, AT-077, AT-087–AT-093, AT-095, AT-097–AT-100 |

For an overlapping subject, owner precedence is scientific, storage, API,
deployment, then product. `architecture.md` constrains cross-cutting component
boundaries but cannot redefine an owner-specific schema/formula. Acceptance
tests and this mapping are verification artifacts; README is an entry point,
not a higher-precedence contract.

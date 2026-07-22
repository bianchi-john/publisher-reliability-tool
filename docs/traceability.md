# Requirements Traceability

**Status:** Normative research-demo coverage map

Acceptance tests verify requirements and do not create additional product
scope. AT-001–AT-045 are core; AT-046–AT-047 optional GPU; AT-048–AT-050
optional stress/fault.

## Functional requirements

| Requirement | Acceptance tests |
| --- | --- |
| FR-001 | AT-001, AT-002, AT-003, AT-004, AT-018 |
| FR-002 | AT-011, AT-012, AT-015 |
| FR-003 | AT-013, AT-014, AT-015, AT-016, AT-048 |
| FR-004 | AT-013, AT-020, AT-028, AT-042, AT-045 |
| FR-005 | AT-028, AT-044 |
| FR-006 | AT-021, AT-022, AT-044 |
| FR-007 | AT-026, AT-034 |
| FR-008 | AT-027, AT-028 |
| FR-009 | AT-029, AT-030, AT-034, AT-041, AT-044 |
| FR-010 | AT-031, AT-032, AT-033, AT-041 |
| FR-011 | AT-033 |
| FR-012 | AT-034, AT-035, AT-038, AT-039, AT-046, AT-047 |
| FR-013 | AT-035, AT-036, AT-046, AT-047 |
| FR-014 | AT-035, AT-037, AT-046, AT-047 |
| FR-015 | AT-023, AT-024, AT-025, AT-027, AT-030 |
| FR-016 | AT-021, AT-022 |
| FR-017 | AT-005, AT-007, AT-008, AT-009, AT-010, AT-043, AT-044, AT-049, AT-050 |
| FR-018 | AT-006, AT-016, AT-027, AT-030, AT-043 |
| FR-019 | AT-003, AT-018, AT-024 |
| FR-020 | AT-017, AT-040, AT-041, AT-042 |

## Non-functional requirements

| Requirement | Acceptance tests |
| --- | --- |
| NFR-001 | AT-007, AT-017, AT-040, AT-043 |
| NFR-002 | AT-019, AT-040, AT-048 |
| NFR-003 | AT-011, AT-015, AT-035, AT-039, AT-045 |
| NFR-004 | AT-005, AT-008, AT-009, AT-010, AT-044, AT-049, AT-050 |
| NFR-005 | AT-013, AT-020, AT-028, AT-042, AT-045 |
| NFR-006 | AT-002, AT-021, AT-040, AT-045 |
| NFR-007 | AT-020, AT-040, AT-041, AT-042 |
| NFR-008 | AT-017, AT-020, AT-026, AT-029 |

## Contract ownership and precedence

| Subject | Normative owner |
| --- | --- |
| Scientific formulas, model/input identity, provenance | `scientific-contract.md` |
| CSV schemas, write/recovery behavior, import digest | `csv-storage-contract.md` |
| HTTP schemas, statuses, pagination, stable errors | `api-contract.md` |
| Native/Compose configuration and operating procedure | `deployment.md` |
| Demo scope, workflow, UI, jobs, requirements | `product-specification.md` |
| Cross-cutting module boundaries and invariants | `architecture.md` |

For an owner-specific conflict, precedence is scientific, storage, API,
deployment, then product. Architecture may constrain boundaries but cannot
redefine an owner schema or formula. README is an entry point. Acceptance tests
and this matrix are verification artifacts.

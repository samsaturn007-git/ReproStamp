# PRD-08 — Generate and validate an app starter

[Shared implementation decisions](../PRODUCT_PLAN.md) · [Implementation status](../IMPLEMENTATION_STATUS.md)

**Depends on** PRD-05. Optional extension that keeps the original prompt-to-app concept.

**User outcome.** Describe a small task tracker, then download a working React and FastAPI starter with its validation results.

1. Translate the request into a typed configuration for one maintained template. Allow project naming, task fields, and status labels. Generate the project from that template with locked dependencies, a SQLite development store, and local startup instructions.
2. Validate FastAPI health and task CRUD, plus the user journey for creating, editing, and completing a task in the supported browser engines. Keep the acceptance suite outside the generated app. Export the source and a `starter_validation` receipt containing the checks that ran.
3. Demonstrate two configurations using the same template. Run the checked-in mock configuration in ordinary CI. Reuse the provider consent and usage accounting from PRD-05 for a live request.

**Exit gate.** A developer can download the generated source, start it locally, and rerun its tests from the README. Reject invalid configurations with readable errors. The template and validation gates work with the cloud model disabled.

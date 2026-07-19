# Documentation

- [setup.md](setup.md) — installing dependencies, running the test suite, repo layout
- [config_format.md](config_format.md) — the dataset config JSON format
- [adding_a_dataset.md](adding_a_dataset.md) — how to add a new dataset config and verify it
- [running_locally.md](running_locally.md) — environment variables, running the server, manual QA checklist
- [architecture.md](architecture.md) — module map and how this code maps onto the system design

The overall system design (config layers, providers, the file index, OPeNDAP/REST/
download/publish endpoints, access control, extensibility) is documented in
[`implementation_plan.md`](../implementation_plan.md) at the repo root — that document
is the source of truth for the *design*; the pages here document the *implementation* as
it exists today and how to work with it.

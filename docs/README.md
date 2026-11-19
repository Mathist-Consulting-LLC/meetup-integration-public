# Event Integrations developer guide

Use this reading order in a fresh checkout:

1. [Quickstart](quickstart.md): build locally and run an independent offline consumer.
2. [API reference](api.md): signatures, data models and language differences.
3. [Setup, authorization and transport](setup.md): replace fixtures with caller-owned services.
4. [Errors, recovery and lifecycle](recovery.md): limits, pagination and ownership.
5. [Extension guide](extension.md) and [component charter](component-charter.md).
6. [Validation](validation.md) and [requirements catalog](../requirements/README.md).

The supported runtime floor is Python 3.11+ and Node.js 20+ (ES modules).
All bundled examples use synthetic data and no credentials. Live API access
requires the caller's independent authorization and transport validation.
Local package builds from a pinned Git revision are the distribution path.
No registry release or live-provider acceptance is implied.

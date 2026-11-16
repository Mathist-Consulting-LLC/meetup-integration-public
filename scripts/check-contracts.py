"""Run after installing the package; no network or credential handling."""
from meetup_integration.contract_check import main

raise SystemExit(main())

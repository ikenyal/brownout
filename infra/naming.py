"""One place for resource names, so a second copy of Brownout can live next to the first.

BROWNOUT_NAME (default "brownout") prefixes every AWS resource. The default keeps the
original names and files, so an existing deployment is not affected.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT = "brownout"
NAME = os.environ.get("BROWNOUT_NAME", DEFAULT)

if not re.fullmatch(r"[a-z][a-z0-9]{2,19}", NAME):
    raise SystemExit(f"BROWNOUT_NAME must be 3-20 lowercase letters or digits, starting with a letter: {NAME!r}")

IS_DEFAULT = NAME == DEFAULT
OUTPUTS = HERE / ("outputs.json" if IS_DEFAULT else f"outputs-{NAME}.json")
RUNTIME_POLICY = HERE / ("runtime-policy.json" if IS_DEFAULT else f"runtime-policy-{NAME}.json")
EVENT_SOURCE = "examplecity.alerts" if IS_DEFAULT else f"examplecity.alerts.{NAME}"
TRIGGER = f"{NAME}-trigger"

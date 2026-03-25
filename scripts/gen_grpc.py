"""Generate Python gRPC stubs from the proto file.

Usage:
    python scripts/gen_grpc.py

Requires grpcio-tools to be installed:
    pip install grpcio-tools
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    try:
        from grpc_tools import protoc  # type: ignore[import-untyped]
    except ImportError:
        print(
            "grpcio-tools is required to generate stubs. Install it with: pip install grpcio-tools",
            file=sys.stderr,
        )
        return 1

    # Resolve paths relative to the project root (one level up from scripts/).
    project_root = Path(__file__).resolve().parent.parent
    proto_dir = project_root / "src" / "auracode" / "grid" / "proto"
    out_dir = project_root / "src" / "auracode" / "grid" / "_generated"

    out_dir.mkdir(parents=True, exist_ok=True)

    result = protoc.main(
        [
            "",
            f"-I{proto_dir}",
            f"--python_out={out_dir}",
            f"--grpc_python_out={out_dir}",
            "auracode_grid.proto",
        ]
    )

    if result != 0:
        print(f"protoc exited with code {result}", file=sys.stderr)
        return result

    # Ensure __init__.py exists.
    init_file = out_dir / "__init__.py"
    if not init_file.exists():
        init_file.write_text('"""Auto-generated gRPC stubs — do not edit."""\n')

    print(f"Generated stubs in {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

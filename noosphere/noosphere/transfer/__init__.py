"""Method packaging, signing, and transfer studies.

Two distinct things live here:

* the transfer *harness* (``run_transfer_study``) — a per-method
  calibration-delta tool, exported below, and
* the cross-domain transfer *study* — the empirical experiment in
  :mod:`noosphere.transfer.study` that asks whether a method's
  in-domain track record carries to a neighboring domain. The study is
  a CLI-style module (``python -m noosphere.transfer.study``); it is
  imported as ``from noosphere.transfer import study`` rather than
  eagerly here, mirroring ``noosphere.benchmarks.qh_analysis``, so the
  ``-m`` entrypoint does not double-import.
"""

from noosphere.transfer.adapter_template import render_adapter
from noosphere.transfer.docker_build import docker_build, render_dockerfile, write_dockerfile
from noosphere.transfer.harness import run_transfer_study
from noosphere.transfer.package_method import PackagePath, package
from noosphere.transfer.signing import (
    compute_checksums,
    sign_checksums,
    verify_checksums,
    verify_signed_checksums,
    write_signed_checksums,
)

__all__ = [
    "PackagePath",
    "compute_checksums",
    "docker_build",
    "package",
    "render_adapter",
    "render_dockerfile",
    "run_transfer_study",
    "sign_checksums",
    "verify_checksums",
    "verify_signed_checksums",
    "write_dockerfile",
    "write_signed_checksums",
]

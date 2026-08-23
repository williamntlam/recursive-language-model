# Trajectory and report contract

- Runtime events are written under the configured log directory (by default
  `.rlm/logs/`) and must remain available when a run aborts.
- Logs should contain operational metadata and bounded previews, not a source
  dump or credentials.
- The static report must escape untrusted event content; report rendering is
  covered by `tests/test_report.py`.
- Keep error categories distinguishable so the CLI can preserve its documented
  exit-code behavior.

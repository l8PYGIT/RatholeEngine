## Summary of changes

<!-- One sentence describing what this PR does. -->

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Documentation
- [ ] Refactor / cleanup

## Checklist

- [ ] `bash -n rathole-manager/ratholectl rathole-manager/ratholenode rathole-manager/common.sh` passes
- [ ] `shellcheck -S warning rathole-manager/ratholectl rathole-manager/ratholenode` passes (or deviations are justified)
- [ ] `python3 -m py_compile rathole-manager/ratholehub/hub.py rathole-manager/ratholehub/hubcmds.py rathole-manager/ratholehub/ssh_proxy.py rathole-manager/ratholeagent.py` passes (if Python files changed)
- [ ] `python3 -m unittest discover -s tests -p "test_*.py"` passes
- [ ] `node --check rathole-manager/ratholehub/ui/app.js && node tests/test_hub_provisioning.js` passes (if Hub UI JS changed)
- [ ] `bash rathole-manager/test-harness.sh` passes (if bash logic changed)
- [ ] Files have **LF** line endings (no CRLF)
- [ ] `CHANGELOG.md` and `CHANGELOG.en.md` updated under `[Unreleased]`
- [ ] No hardcoded version numbers in user-visible strings
- [ ] No secrets (certs, tokens, state.json) committed

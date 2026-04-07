# Lessons Learned For Ansible Roles

## 1) Validate external-system constraints before command execution
- Problem: `mc mb` failed with `Bucket name contains invalid characters`.
- Root cause: bucket names with `_` (e.g. `b_test_a`) are invalid for S3/MinIO.
- Fix:
  - Use S3-compatible names (`b-test-a`, `b-test-b`, `b-default`).
  - Add pre-check asserts in role input validation.
- Rule for future roles:
  - Always encode provider constraints (naming, length, formats) in `pre-req` validation, not only in runtime commands.

## 2) Keep defaults, tests, and docs in sync
- Problem: defaults/examples/tests used invalid bucket names.
- Fix:
  - Updated role defaults.
  - Updated Molecule `converge.yml` and `verify.yml`.
  - Updated README examples.
- Rule for future roles:
  - Any variable/schema change must be applied in 4 places together:
    1. `defaults/`
    2. `tasks/` validation and logic
    3. `molecule/` scenarios and checks
    4. `README.md` examples

## 3) Prefer Ansible/Jinja compatibility-safe filters
- Problem: task failed with `Could not load "length": 'length'`.
- Root cause: `select('length')` is not portable across all bundled Jinja/Ansible versions.
- Fix:
  - Replaced `select('length')` with `reject('equalto', '')` before `from_json`.
- Rule for future roles:
  - Avoid non-portable tests/filters where equivalent stable forms exist.
  - For JSONL parsing pipelines, first remove empty lines, then parse JSON.

## 4) Validate early, fail clearly
- Improvement made:
  - Added strict bucket name validation in `pre-req.yaml`:
    - length 3..63
    - lowercase letters/digits/dot/hyphen only
    - no underscores
    - not IPv4-like string
    - no `..`, `-.`, `.-`
- Rule for future roles:
  - Fail at input-validation stage with explicit, actionable error messages.

## 5) Text encoding hygiene
- Observation: some messages/doc text were displayed with mojibake (encoding mismatch).
- Fix approach:
  - Rewrite files in UTF-8 when editing problematic files.
- Rule for future roles:
  - Keep all YAML/Markdown in UTF-8 consistently.
  - If console shows garbled text, normalize encoding before further edits.

## Reusable pre-merge checklist for new/updated roles
1. Inputs are validated in `pre-req` (format, ranges, allowed values).
2. No provider-specific invalid values in defaults.
3. Molecule scenarios cover create/update/delete and negative cases.
4. `README` examples are executable and match current defaults.
5. Jinja filters/tests are compatible with target Ansible versions.
6. JSON parsing handles empty lines safely.
7. Error messages are explicit about what must be fixed.


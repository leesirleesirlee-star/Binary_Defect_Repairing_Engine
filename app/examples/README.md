# GUI examples

Example JSON is intentionally not committed yet.

The four screens consume `ContractV1`, `VerdictV1`, `ObservationV1` and
`EvidenceBundleV1`. Those schemas are not present on `main` at the time of this
change (G0). Committing guessed examples would invent fields the frozen schemas
do not define, which issue #3 forbids.

Once M1 lands the schemas, this directory will hold one validated example per
screen and `tests/app/test_examples.py` will validate every file with
`jsonschema`.

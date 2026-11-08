# Examples

All example data is synthetic. Names, identifiers, and domains are invented, and the domains use the reserved `example` top-level domain.

## roster-vs-directory

An HR roster compared with a directory export. It produces every kind of finding.

| File | Contents |
| --- | --- |
| `profile.toml` | The profile, with a comment on every setting. |
| `expected.csv` | Nine people who should have accounts. |
| `collected.csv` | Twelve accounts from a directory export. |
| `sample-report/` | The reports pakad produces for these files. |

Run it from the repository root:

```shell
pakad reconcile -p examples/roster-vs-directory/profile.toml \
  -e examples/roster-vs-directory/expected.csv \
  -c examples/roster-vs-directory/collected.csv \
  -o examples/roster-vs-directory/sample-report \
  --as-of 2026-11-07T12:00:00Z --force
```

The test suite checks that the committed sample reports match what the current code produces. After a change to report output, run the preceding command to regenerate them and commit the result. `pakad example` writes the same profile and data files, which ship inside the package.

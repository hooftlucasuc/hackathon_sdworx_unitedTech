# sources/ — how to add knowledge

One folder per country code plus `ALL` for material that applies everywhere. The folder name
is the country; ingest never guesses it from the file.

```
sources/BE/holiday_pay_policy_2026.md
sources/BE/holiday_pay_policy_2026.meta.yaml      # sidecar, same basename + .meta.yaml
sources/BE/teams_export_payroll_channel.json
sources/BE/teams_export_payroll_channel.meta.yaml
sources/ALL/client_escalation_procedure.docx
sources/ALL/client_escalation_procedure.meta.yaml
```

## Steps

1. Drop the file in `sources/<CODE>/`. Supported: `.md .txt .pdf .docx .eml .json`.
   JSON is a Teams/Slack export: a list of `{author, timestamp, text}`. Each message becomes
   its own chunk with its own timestamp.
2. Copy `sources/_meta.template.yaml` to `<file>.meta.yaml` next to it and fill it in.
   `source_type` must be a key of `source_hierarchy` in `countries/<CODE>.yaml`.
   `owner: null` is allowed: it is a trust signal, not a validation error.
3. Run the ingest CLI from `backend/`:

   ```bash
   python -m app.ingest.cli --country BE            # ingests sources/BE
   python -m app.ingest.cli --country BE --reset    # deletes BE items + chunks first
   python -m app.ingest.cli --all                   # every country folder + ALL
   ```

   Re-running is idempotent: the item id is `sha256(country + relative_path)[:16]`, so an
   edited file updates in place.

4. If the sidecar is missing, the CLI creates one with `title` from the filename and
   `updated_at` from the file's modification time, everything else null, and logs a warning.
   Fix it and re-run.

## Superseding an older version

Set `supersedes: "<old filename>"` in the new file's sidecar. On ingest the old item is marked
`status: superseded`. It is no longer retrieved, but the Trust Card still shows
"replaces …" on the new one and "superseded by …" on the old one when it is loaded explicitly.

## Same thing through the UI

`Sources` page → upload form with the same fields → `POST /sources/upload`. That runs the
identical pipeline; the folder CLI is just the batch path.

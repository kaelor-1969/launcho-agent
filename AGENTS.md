# Database backup operations

## Production verification — 2026-11-15

This section supersedes the earlier LOCAL ONLY and terminal-blocked notes below.
PR #24 is merged (8fefba2); Runflare shows v34 and a replacement pod.
The script exists in the deployed image. The pre-existing day-6.sqlite3 (45056
bytes) survived that deployment; no pre-deployment hash was recorded, so byte
identity is not claimed. The new command ran successfully through the entrypoint
at 12:45:20 UTC, validating backup, checks, restore and appuser write/replace.
The original daily cron survived deployment and was updated to the script command
below, keeping `17 2 * * *`. Only this daily entry remained after probe cleanup.

Container timezone is UTC. Scheduler timezone remains UNVERIFIED: a temporary
`* 12 * * *` probe registered around 12:47 UTC produced no timestamp marker by
12:50:18 UTC and was removed. This negative result is inconclusive; do not infer
Tehran or UTC for the scheduler. Provider confirmation/execution logs are needed.
External backup remains CLAIM ONLY. No webhook destination has been supplied.

Never stop the production service, replace/delete the production database, or print
credentials, session contents, environment values or private download URLs.

## Cron timezone

UNVERIFIED. Observed in the Runflare panel: `17 2 * * *` on service 88574,
project 37668. The existing inline command uses UTC for rotation and logging;
this does not establish the scheduler timezone. Do not describe this as 02:17
Tehran until an hour-specific probe or provider confirmation establishes it.
A five-minute probe alone cannot distinguish scheduler timezones. Record the
expression, actual UTC execution time and container offset; restore the daily
schedule after probing. Do not remove the working daily backup to add a probe.

## Failure observability

`scripts/daily_backup.py` returns 1 on backup failure, logging only status,
phase, timestamp and exception class. `ALERT_WEBHOOK_URL` is optional; failure
notifications contain only status, phase and timestamp. Webhook errors do not
change the failure exit status. No endpoint is configured by default.
Deployment status: LOCAL ONLY. The panel still runs its original inline command.
After deploying the tested script, the replacement command is:

```
/usr/local/bin/python /app/scripts/container_entrypoint.py /usr/local/bin/python /app/scripts/daily_backup.py
```

## Redeploy behavior

UNVERIFIED on Runflare. Persistent volume restart checks reported previously
do not prove cron persistence across redeploys. Operational checklist:
record existing backup filenames and hashes (never database contents); record
the cron expression and command; deploy without stopping the service; compare
the old backup hashes; verify cron still exists; run an appuser-only temporary
write probe inside daily-backups and remove only that probe. Recreate the cron
if missing. Do not claim provider cron persistence without this observation.

CI now runs `tests/check_backup_redeploy.py`: rebuild an image, replace disposable
containers sharing an isolated volume, compare prior backup hashes, read the
saved marker and verify UID 10001 can write. It does not test Runflare cron.
Local execution is blocked because Docker is not installed in this environment.
Panel terminal access is visible, but automated text input did not transmit
correctly (ASCII keystrokes became Persian text); no production backup command
or schedule was changed. Repository origin is a local filesystem checkout,
not the GitHub deployment remote. Production deployment remains pending.

## External backup — provider claim vs. verified

CLAIM ONLY: 4 daily / 1 weekly / 1 monthly. No provider-managed restore has been
verified. Ask support for naming, location, timezone, retention and restoration
instructions. Restore a provider backup into an isolated disposable database,
never over the live database, then verify integrity and foreign keys.

## Rotation

Slots use UTC weekday, Monday=0 through Sunday=6. The start timestamp is captured
once. Tests walk 14 days over week boundaries and European spring/autumn DST
dates and inspect every retained database marker. UTC itself does not use DST.

# Security & Privacy

## What this app does with your data

Cloud Save Sync only moves **your game save files** between **your own devices** and
**your own cloud account** (OneDrive / Google Drive / Dropbox / iCloud / a local folder).
Nothing is sent anywhere else; there is no telemetry, no account, no server of ours.

## Recommendations

- Keep the cloud folder (`SaveSync`) **private** on your cloud provider.
- For extra privacy (saves can contain personal data), use an rclone **crypt** remote as
  `remote` in the config: saves are then encrypted client-side before upload.
  ```
  rclone config    # create a "crypt" remote wrapping e.g. onedrive:SaveSyncEncrypted
  ```
  then set `"remote": "crypt"` in `~/.config/savesync/config.json` (or `%APPDATA%\savesync\config.json`).
- Don't run syncs on two machines at the exact same time (bisync holds a 2-minute lock).

## Reporting a vulnerability

Open a [private security advisory](https://github.com/benjamin-bock/nuage/security/advisories/new)
or an issue if the impact is low.

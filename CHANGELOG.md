# Changelog

## v0.1.0
- Initial release.
- Triggers: fireball (meteor peak brightness), aurora candidate, exceptional dark sky,
  nightly summary.
- Channels: website banner (`alerts.json`), Telegram (`sendPhoto`/`sendMessage`),
  e-mail (SMTP STARTTLS/SSL).
- Per-night deduplication via a state file; network sends run off the capture thread.

# allsky_skyalert

A **multi-channel sky alerting** module for [Allsky](https://github.com/AllskyTeam/allsky).

It watches the rolling data produced by
[allsky_skyquality](https://github.com/benhartwich/allsky-skyquality) and
[allsky_meteordetect](https://github.com/benhartwich/allsky-meteordetect) and raises
alerts on interesting events over one or more channels you can enable independently.

## Triggers

| Trigger | Fires when | How often |
|---|---|---|
| **Fireball** | a confirmed meteor's peak brightness exceeds a threshold | per event |
| **Aurora candidate** | the aurora index exceeds a threshold | once per night |
| **Exceptional dark sky** | SQM is better (higher) than a threshold | once per night |
| **Nightly summary** | at the night→day transition | once per night |

Each trigger can be switched on/off and has its own threshold.

## Channels

| Channel | Needs | Notes |
|---|---|---|
| **Website banner** | nothing | Writes `alerts.json` to the website (and uploads it). The bundled dashboard shows a banner. |
| **Telegram** | bot token + chat id | Sends the meteor image with fireball alerts (`sendPhoto`). |
| **E-mail** | SMTP host/port/user/pass + recipient | STARTTLS (587) or SSL (465); attaches the meteor image. |

A channel with missing credentials is silently skipped — the banner always works.
Network sends (Telegram / e-mail) run in a background thread so they never slow the
capture loop, and they only fire on an actual (rare) trigger.

## Installation

```bash
cp allsky_skyalert.py ~/allsky/scripts/modules/
```

Enable **"Sky Alerts"** in the Allsky WebUI for the **night** flow (it also hooks the
`nightday` event for the summary). Then fill in the triggers/channels you want.

Telegram needs the `requests` package (already present in a standard Allsky install).
E-mail uses only the Python standard library.

## Data it reads

- `skyquality.json` in the Allsky tmp folder (SQM, `mlim`, `aurora`, `moon_*`).
- `meteors.json` in the website `meteors` folder (or the folder you set), with `peak`
  brightness and `showers` context.

So this module is most useful alongside `allsky_skyquality` and `allsky_meteordetect`.

## Deduplication

A small state file (`allsky_skyalert_state.json`) makes sure the same meteor is not
re-alerted, and that the aurora / dark-sky / summary alerts fire at most once per night.

## Credits

- [Allsky](https://github.com/AllskyTeam/allsky) by Thomas Jacquin and team.
- Built for [astronomy.garden](https://astronomy.garden).

## License

MIT — see [LICENSE](LICENSE).

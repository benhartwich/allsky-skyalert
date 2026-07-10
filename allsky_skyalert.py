""" allsky_skyalert.py

Sky alerting module for Allsky.
https://github.com/AllskyTeam/allsky

Author:      Benjamin Hartwich (https://astronomy.garden)
Home / docs: https://github.com/benhartwich/allsky-skyalert

Watches the rolling data written by the allsky_skyquality and allsky_meteordetect
modules and raises alerts on interesting events, over one or more configurable
channels (a website banner, Telegram, e-mail). It reads:

    * skyquality.json  (SQM, limiting magnitude, aurora index, moon, ...)
    * meteors.json     (confirmed meteors with peak brightness + shower context)

Triggers (each can be turned on/off):

    * Fireball          - a confirmed meteor whose peak brightness exceeds a threshold
    * Aurora candidate  - the aurora index exceeds a threshold
    * Exceptional dark   - SQM better (higher) than a threshold, a rare top-tier night
    * Daily summary     - once per night (at the night->day transition): darkest SQM,
                          best limiting magnitude, meteor count

Each channel degrades gracefully: if its credentials are not filled in, that channel
is simply skipped. The website banner needs no credentials and is always available.
Network sends (Telegram / e-mail) run in a background thread so they never slow the
capture loop; they only fire on an actual (rare) trigger.
"""
import allsky_shared as s
import os
import json
import time
import threading

metaData = {
    "name": "Sky Alerts",
    "description": "Alerts on fireballs, aurora, exceptional dark skies and a nightly summary via banner / Telegram / e-mail",
    "version": "v0.1.0",
    "events": [
        "night",
        "nightday"
    ],
    "experimental": "false",
    "module": "allsky_skyalert",
    "arguments": {
        "meteor_dir": "",
        "t_fireball": "true",
        "fireball_peak": "120",
        "t_aurora": "true",
        "aurora_thr": "8",
        "t_darksky": "true",
        "darksky_thr": "21.3",
        "t_summary": "true",
        "chan_banner": "true",
        "chan_telegram": "false",
        "tg_token": "",
        "tg_chat": "",
        "chan_email": "false",
        "smtp_host": "",
        "smtp_port": "587",
        "smtp_user": "",
        "smtp_pass": "",
        "mail_from": "",
        "mail_to": "",
        "debug": "false"
    },
    "argumentdetails": {
        "meteor_dir": {
            "required": "false",
            "description": "Meteor Folder",
            "help": "Folder that holds meteors.json + images (from allsky_meteordetect). Empty = website 'meteors' folder.",
            "type": {"fieldtype": "text"}
        },
        "t_fireball": {
            "required": "false",
            "description": "Alert: Fireball",
            "help": "Alert when a confirmed meteor's peak brightness exceeds the threshold below",
            "tab": "Triggers",
            "type": {"fieldtype": "checkbox"}
        },
        "fireball_peak": {
            "required": "false",
            "description": "Fireball Peak Threshold",
            "help": "Meteor peak brightness (0-255, from meteors.json) above which it counts as a fireball",
            "tab": "Triggers",
            "type": {"fieldtype": "spinner", "min": 30, "max": 255, "step": 5}
        },
        "t_aurora": {
            "required": "false",
            "description": "Alert: Aurora Candidate",
            "help": "Alert when the aurora index (green glow on the north horizon) exceeds the threshold",
            "tab": "Triggers",
            "type": {"fieldtype": "checkbox"}
        },
        "aurora_thr": {
            "required": "false",
            "description": "Aurora Index Threshold",
            "help": "Aurora index above which to alert (matches the dashboard banner threshold)",
            "tab": "Triggers",
            "type": {"fieldtype": "spinner", "min": 3, "max": 40, "step": 1}
        },
        "t_darksky": {
            "required": "false",
            "description": "Alert: Exceptional Dark Sky",
            "help": "Alert (once per night) when SQM is better than the threshold",
            "tab": "Triggers",
            "type": {"fieldtype": "checkbox"}
        },
        "darksky_thr": {
            "required": "false",
            "description": "Dark-Sky SQM Threshold",
            "help": "SQM (mag/arcsec2) above which the night counts as exceptionally dark",
            "tab": "Triggers",
            "type": {"fieldtype": "spinner", "min": 19, "max": 22.5, "step": 0.1}
        },
        "t_summary": {
            "required": "false",
            "description": "Alert: Nightly Summary",
            "help": "Send one summary at dawn (darkest SQM, best limiting magnitude, meteor count)",
            "tab": "Triggers",
            "type": {"fieldtype": "checkbox"}
        },
        "chan_banner": {
            "required": "false",
            "description": "Channel: Website Banner",
            "help": "Write alerts.json to the website (and upload it) so the dashboard shows an alert banner. Needs no credentials.",
            "tab": "Channels",
            "type": {"fieldtype": "checkbox"}
        },
        "chan_telegram": {
            "required": "false",
            "description": "Channel: Telegram",
            "help": "Send alerts to a Telegram chat (with the meteor image for fireballs). Fill in the token + chat id below.",
            "tab": "Channels",
            "type": {"fieldtype": "checkbox"}
        },
        "tg_token": {
            "required": "false",
            "description": "Telegram Bot Token",
            "help": "Token from @BotFather, e.g. 123456:ABC-DEF...",
            "tab": "Channels",
            "type": {"fieldtype": "text"}
        },
        "tg_chat": {
            "required": "false",
            "description": "Telegram Chat ID",
            "help": "Numeric chat id (message your bot, then read it from getUpdates)",
            "tab": "Channels",
            "type": {"fieldtype": "text"}
        },
        "chan_email": {
            "required": "false",
            "description": "Channel: E-mail",
            "help": "Send alerts by e-mail via SMTP. Fill in the SMTP fields below.",
            "tab": "Channels",
            "type": {"fieldtype": "checkbox"}
        },
        "smtp_host": {
            "required": "false",
            "description": "SMTP Host",
            "help": "Outgoing mail server, e.g. smtp.gmail.com",
            "tab": "Channels",
            "type": {"fieldtype": "text"}
        },
        "smtp_port": {
            "required": "false",
            "description": "SMTP Port",
            "help": "587 for STARTTLS (default), 465 for SSL",
            "tab": "Channels",
            "type": {"fieldtype": "spinner", "min": 1, "max": 65535, "step": 1}
        },
        "smtp_user": {
            "required": "false",
            "description": "SMTP User",
            "help": "SMTP login user",
            "tab": "Channels",
            "type": {"fieldtype": "text"}
        },
        "smtp_pass": {
            "required": "false",
            "description": "SMTP Password",
            "help": "SMTP login password / app password",
            "tab": "Channels",
            "type": {"fieldtype": "text"}
        },
        "mail_from": {
            "required": "false",
            "description": "Mail From",
            "help": "From address (defaults to SMTP user)",
            "tab": "Channels",
            "type": {"fieldtype": "text"}
        },
        "mail_to": {
            "required": "false",
            "description": "Mail To",
            "help": "Recipient address",
            "tab": "Channels",
            "type": {"fieldtype": "text"}
        },
        "debug": {
            "required": "false",
            "description": "Enable debug logging",
            "help": "Log every trigger evaluation",
            "tab": "Debug",
            "type": {"fieldtype": "checkbox"}
        }
    },
    "enabled": "false",
    "changelog": {
        "v0.1.0": [
            {
                "author": "Benjamin Hartwich",
                "authorurl": "https://github.com/benhartwich",
                "changes": "Initial multi-channel alerting (fireball / aurora / dark-sky / nightly summary) via banner, Telegram and e-mail"
            }
        ]
    }
}

STATE_FILE = os.path.join(s.ALLSKY_TMP, "allsky_skyalert_state.json")


# ------------------------------ helpers ------------------------------

def _readJson(path, default):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return default


def _writeJson(path, data):
    try:
        with open(path, "w") as fh:
            json.dump(data, fh)
        return True
    except Exception as ex:
        s.log(1, f"WARNING: skyalert could not write {path}: {ex}")
        return False


def _websiteDir():
    website = s.getEnvironmentVariable("ALLSKY_WEBSITE")
    if not website:
        website = os.path.join(s.getEnvironmentVariable("ALLSKY_HOME") or os.path.expanduser("~/allsky"),
                               "html", "allsky")
    return website


def _nightKey():
    """A key that is stable across a single night: the date at local 'noon-anchored'
    time, so evening and the following early morning share one key."""
    lt = time.localtime()
    day = lt.tm_yday
    if lt.tm_hour < 12:          # after midnight still belongs to the previous evening
        day -= 1
    return f"{lt.tm_year}-{day:03d}"


# ------------------------------ channels ------------------------------

def _telegram(token, chat, text, image_path=None):
    try:
        import requests
    except Exception:
        s.log(1, "WARNING: skyalert telegram needs the 'requests' package")
        return
    try:
        base = f"https://api.telegram.org/bot{token}"
        if image_path and os.path.isfile(image_path):
            with open(image_path, "rb") as fh:
                requests.post(f"{base}/sendPhoto",
                              data={"chat_id": chat, "caption": text[:1024]},
                              files={"photo": fh}, timeout=20)
        else:
            requests.post(f"{base}/sendMessage",
                          data={"chat_id": chat, "text": text}, timeout=20)
    except Exception as ex:
        s.log(1, f"WARNING: skyalert telegram send failed: {ex}")


def _email(cfg, subject, body, image_path=None):
    import smtplib
    from email.message import EmailMessage
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = cfg["from"]
        msg["To"] = cfg["to"]
        msg.set_content(body)
        if image_path and os.path.isfile(image_path):
            with open(image_path, "rb") as fh:
                msg.add_attachment(fh.read(), maintype="image", subtype="jpeg",
                                   filename=os.path.basename(image_path))
        if cfg["port"] == 465:
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=20) as srv:
                if cfg["user"]:
                    srv.login(cfg["user"], cfg["pass"])
                srv.send_message(msg)
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=20) as srv:
                srv.starttls()
                if cfg["user"]:
                    srv.login(cfg["user"], cfg["pass"])
                srv.send_message(msg)
    except Exception as ex:
        s.log(1, f"WARNING: skyalert e-mail send failed: {ex}")


def _banner(alert):
    """Append the alert to alerts.json in the website root and upload it."""
    website = _websiteDir()
    path = os.path.join(website, "alerts.json")
    data = _readJson(path, [])
    if not isinstance(data, list):
        data = []
    data.append(alert)
    data = data[-30:]
    if _writeJson(path, data):
        _uploadRemote(path, "alerts.json")


def _uploadRemote(local, fname):
    try:
        if s.getSetting("useremotewebsite") != "true":
            return
        import subprocess
        scripts = s.getEnvironmentVariable("ALLSKY_SCRIPTS") or \
            os.path.join(s.getEnvironmentVariable("ALLSKY_HOME") or os.path.expanduser("~/allsky"), "scripts")
        uploader = os.path.join(scripts, "upload.sh")
        if not os.path.isfile(uploader) or not os.path.isfile(local):
            return
        rdir = (s.getSetting("remotewebsiteimagedir") or "").rstrip("/")
        subprocess.Popen([uploader, "--silent", "--wait", "--remote-web", local, rdir, fname, "SkyAlert"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as ex:
        s.log(1, f"WARNING: skyalert remote upload failed: {ex}")


def _dispatch(cfg, alert, image_path):
    """Fan the alert out to every enabled channel. Network sends run in a thread."""
    if cfg["chan_banner"]:
        _banner(alert)                              # fast local write + async upload

    def _net():
        text = f"{alert['title']}\n{alert['message']}"
        if cfg["chan_telegram"] and cfg["tg_token"] and cfg["tg_chat"]:
            _telegram(cfg["tg_token"], cfg["tg_chat"], text, image_path)
        if cfg["chan_email"] and cfg["smtp_host"] and cfg["mail_to"]:
            _email(cfg["email"], alert["title"], alert["message"], image_path)

    if (cfg["chan_telegram"] or cfg["chan_email"]):
        threading.Thread(target=_net, daemon=True).start()


# ------------------------------ trigger evaluation ------------------------------

def _summaryText(sqm_rows, meteors, key):
    night = [r for r in sqm_rows if r.get("sqm") is not None]
    darkest = max((r["sqm"] for r in night), default=None)
    best_nelm = max((r["mlim"] for r in night if r.get("mlim") is not None), default=None)
    # meteors whose timestamp falls in this night (last ~16h window)
    cutoff = time.time() - 16 * 3600
    def _epoch(m):
        t = m.get("time", "")
        try:
            st = time.strptime(t, "%Y%m%d%H%M%S")
            return time.mktime(st)
        except Exception:
            return 0
    n_met = sum(1 for m in meteors if _epoch(m) >= cutoff)
    parts = []
    parts.append(f"Darkest SQM: {darkest:.2f} mag/arcsec2" if darkest is not None else "Darkest SQM: n/a")
    if best_nelm is not None:
        parts.append(f"Limiting mag: {best_nelm:.1f}")
    parts.append(f"Meteors confirmed: {n_met}")
    return " · ".join(parts)


def skyalert(params, event):
    debug = params.get("debug", False)

    cfg = {
        "chan_banner": params.get("chan_banner", True),
        "chan_telegram": params.get("chan_telegram", False),
        "tg_token": params.get("tg_token", "").strip(),
        "tg_chat": params.get("tg_chat", "").strip(),
        "chan_email": params.get("chan_email", False),
        "smtp_host": params.get("smtp_host", "").strip(),
        "mail_to": params.get("mail_to", "").strip(),
        "email": {
            "host": params.get("smtp_host", "").strip(),
            "port": s.int(params.get("smtp_port", 587)),
            "user": params.get("smtp_user", "").strip(),
            "pass": params.get("smtp_pass", ""),
            "from": (params.get("mail_from", "").strip() or params.get("smtp_user", "").strip()),
            "to": params.get("mail_to", "").strip(),
        },
    }

    website = _websiteDir()
    meteor_dir = params.get("meteor_dir", "").strip() or os.path.join(website, "meteors")
    sqm_rows = _readJson(os.path.join(s.ALLSKY_TMP, "skyquality.json"), [])
    meteors = _readJson(os.path.join(meteor_dir, "meteors.json"), [])
    state = _readJson(STATE_FILE, {})
    key = _nightKey()

    fired = []

    # --- nightly summary at the dusk->dawn transition ---
    if event == "nightday":
        if params.get("t_summary", True) and state.get("summary_key") != key and sqm_rows:
            msg = _summaryText(sqm_rows, meteors, key)
            alert = {"t": int(time.time()), "type": "summary", "severity": "info",
                     "title": "Nightly sky summary", "message": msg}
            _dispatch(cfg, alert, None)
            state["summary_key"] = key
            fired.append("summary")
        _writeJson(STATE_FILE, state)
        return f"Summary sent" if fired else "No summary (already sent or no data)"

    # --- live night checks ---
    latest = sqm_rows[-1] if sqm_rows else None

    # Fireball: newest confirmed meteor above the peak threshold, not yet alerted
    if params.get("t_fireball", True) and meteors:
        thr = s.int(params.get("fireball_peak", 120))
        newest = meteors[-1]
        peak = newest.get("peak")
        mtime = newest.get("time", "")
        if peak is not None and peak >= thr and mtime and mtime != state.get("last_meteor"):
            showers = newest.get("showers") or []
            ctx = (", ".join(showers)) if showers else "sporadic"
            img = os.path.join(meteor_dir, newest.get("file", ""))
            alert = {"t": int(time.time()), "type": "fireball", "severity": "high",
                     "title": "🔥 Fireball detected",
                     "message": f"Bright meteor (peak {peak}) — {ctx}. {mtime}",
                     "image": newest.get("file", "")}
            _dispatch(cfg, alert, img if os.path.isfile(img) else None)
            state["last_meteor"] = mtime
            fired.append("fireball")

    # Aurora candidate: index over threshold, once per night
    if params.get("t_aurora", True) and latest is not None and latest.get("aurora") is not None:
        thr = s.asfloat(params.get("aurora_thr", 8))
        if latest["aurora"] >= thr and state.get("aurora_key") != key:
            alert = {"t": int(time.time()), "type": "aurora", "severity": "high",
                     "title": "⚡ Aurora candidate",
                     "message": f"Green glow on the north horizon (index {latest['aurora']:.0f})."}
            _dispatch(cfg, alert, None)
            state["aurora_key"] = key
            fired.append("aurora")

    # Exceptional dark sky: SQM over threshold, once per night
    if params.get("t_darksky", True) and latest is not None and latest.get("sqm") is not None:
        thr = s.asfloat(params.get("darksky_thr", 21.3))
        if latest["sqm"] >= thr and state.get("darksky_key") != key:
            nelm = latest.get("mlim")
            extra = f", limiting mag {nelm:.1f}" if nelm is not None else ""
            alert = {"t": int(time.time()), "type": "darksky", "severity": "info",
                     "title": "🌌 Exceptional dark sky",
                     "message": f"SQM {latest['sqm']:.2f} mag/arcsec2{extra}."}
            _dispatch(cfg, alert, None)
            state["darksky_key"] = key
            fired.append("darksky")

    _writeJson(STATE_FILE, state)

    if debug:
        s.log(1, f"INFO: skyalert evaluated (fired: {fired or 'none'})")
    return f"Alerts fired: {', '.join(fired)}" if fired else "No alerts"


def skyalert_cleanup():
    moduleData = {
        "metaData": metaData,
        "cleanup": {
            "files": {STATE_FILE},
            "env": set()
        }
    }
    s.cleanupModule(moduleData)

<<<<<<< HEAD
# Omnis Partner – FastAPI Port

This directory contains the Python 3.10 / FastAPI rewrite scaffold for the legacy Spring Boot service. The goal is to mirror the runtime wiring (`OmnisPartnerApplication`) so features can be migrated incrementally.

## Layout

- `app/main.py` – ASGI entrypoint (`uvicorn app.main:app`).
- `app/factory.py` – configures logging, settings, license guard, and service container.
- `app/bootstrap.py` – Async translation of `OmnisPartnerApplication.run`.
- `app/services/` – FastAPI-friendly implementations of the Java service beans (currently placeholders that log their work).
- `app/modules/alertmanager` – AlertManager code split by the original Java packages:
  - `cache/` sample data + in-memory cache
  - `cache/loader.py` loads rules directly from MySQL using the new repository
  - `domain/` dataclasses for alerts, channels, rules
  - `msgformat/`, `provider/`, `repositories/`, `service/`, `util/` etc. mirroring `com/omnis/alertmanager/**`
- `app/modules/deployfilemanage` – FastAPI router + service stubs exposing the original `DepAndReplaceController` endpoints (currently return “not implemented” placeholders so the API contract is visible).
  - Nexus download endpoints (`nexus2localdiskdownload`, `predowloadnexusfile`, `dowloadnexusfilebyagv`, etc.) are functional and stage artifacts under `NEXUS_DOWNLOAD_DIR`.
  - `replaceproperties` and `/jboss/replace` allow previewing simple property replacements and JBoss-style file staging using the new strategy layer.
- `app/settings.py` – Pydantic settings binding the original environment variables (`OMNIS_SWITCH_*`, `ALERTMANAGER_*`, DB credentials, license window).
- `app/license.py` & `app/switches.py` – Ports of `Lic4Business` and `OmnisSwitch`.

## Running Locally

```bash
cd new
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
uvicorn app.main:app --reload
```

Set the original feature flags as environment variables (e.g., `export OMNIS_SWITCH_WEBSQL=true`). The startup log mirrors the Java application to show which subsystems are active.

## AlertManager Endpoints

- `POST /alertmanager/push/zbx` – accepts raw Zabbix payloads (`eventId|hostname|ip|level|alertTime|recoverTime|eventType|[PROJECT]|[CODE]-message`). Optional query params: `projectIdentify`, `notsendmsg=1` to suppress outbound notifications, `syncdata=1` to skip slave sync.
- `POST /alertmanager/push/json` – accepts structured JSON messages. Provide `alertcode`, `alertsourcetype`, `hostname`, `hostip`, `project`, and a nested `msg` object (free-form fields). Query param `alertsourcetype` defaults to `BUSI`.

Example JSON payload:

```json
{
  "project": "TJH",
  "alertcode": "BUSI000",
  "alertsourcetype": "8",
  "hostname": "[TJH]-0.0.0.0-[api-gw]",
  "hostip": "10.0.0.10",
  "msg": {
    "message": "订单同步失败，重试次数耗尽",
    "orderId": "A20240912001"
  },
  "others": {
    "subject": "订单同步失败"
  }
}
```

### Configuration

- `ALERTMANAGER_PROJECT` – default project code when payloads omit one (defaults to `DEFAULT`).
- `ALERTMANAGER_SLAVE_TARGETS` – JSON list of slave base URLs; the sync loop logs outbound copies today.
- `ALERTMANAGER_ALLOWED_TOKENS` – JSON list of bearer tokens accepted by business message APIs.
- Shared MySQL connection (used by all modules, including AlertManager):
  - `DB_HOST` (default `127.0.0.1`)
  - `DB_PORT` (default `3306`)
  - `DB_NAME`
  - `DB_USER`
  - `DB_PASSWORD`
  - `DB_CHARSET` (default `utf8mb4`)
  - or specify a full DSN via `DATABASE_URL`
- Nexus repository (`deployfilemanage` downloads):
  - `NEXUS_BASE_URL` (e.g., `http://localhost:8081`)
  - `NEXUS_REPOSITORY` (`maven-releases`, `maven-snapshots`, etc.)
  - `NEXUS_USERNAME` / `NEXUS_PASSWORD` (optional, for basic auth)
  - `NEXUS_DOWNLOAD_DIR` (local cache directory for downloaded artifacts)
  - `DEPLOY_REPLACE_PATH` (where replacement artifacts are staged, e.g., `new/tmp/replace`)
- Provider-specific env/DB config mirrors the original setup: WeChat (`wx_corpid`, `wx_secret`, `wx_base_url`, etc.), DingTalk (`ding_robot_url`, `ding_robot_sign`), Mail (`mail_sender_smtp`, creds, recipients), SMS (`mas_sender_url`, creds, phone list), and the new Aliyun phone channel (`aliyun_access_key_id/secret`, `aliyun_voice_template_code`, `aliyun_voice_called_show_number`, `aliyun_voice_called_numbers`). The FastAPI registry now wires these providers so real notifications can be delivered once credentials are supplied.

## Parity Notes

- AlertManager now owns the same message-evaluation flow (rule lookup, channel fan-out, forbid rules, duplicate suppression) but uses in-memory repositories and logging providers; swap `InMemoryAlertManagerRepository` / `ProviderRegistry` with real DB + integrations when available.
- The MySQL repository skeleton (`modules/alertmanager/repositories/mysql.py`) shows where to select `alertitem`, `msg_send_rules`, `msg_channel`, `msg_channel_provider`, etc.; extend those queries to match your schema and populate the cache loader.
- Persistence (MyBatis, Redis, Oracle) and messaging clients are not yet implemented.
- Zabbix/JSON push endpoints return structured JSON instead of the `"[SUCCESS]"` strings; adjust clients if they expect the legacy text format.
- The slave sync/resend/repeat loops run but only log actions until external services are wired in.
=======
# OmnisPartner
>>>>>>> 8ef447aa5c04459b9fee130639ae480f41988419

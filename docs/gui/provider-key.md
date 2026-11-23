# Provider-key dialog (local service)

The console settings dialog reads/saves/tests the assistant provider key through
the local API:

- `GET /api/assistant/key` — masked status only (`configured`, `source`, `masked`,
  `can_clear`, `protection`); the key never crosses this boundary.
- `POST /api/assistant/key` — save a key (CSRF + local session). The file is
  `var/assistant.key` with mode `0600`, in the reference GUI's `BRKEY0` format, so
  an already configured key keeps working. The console also reads the reference
  GUI's key file (`../binary-repair-gui/var/assistant.key`) when no local file
  exists.
- `POST /api/assistant/key/test` — one tiny real DeepSeek-compatible chat call
  through the host's `curl` (key in a private config file, never in argv); the
  UI shows the actual provider model or a stable error such as
  `provider_rejected_key`.
- `DELETE /api/assistant/key` — remove the stored key (environment keys are
  managed and cannot be cleared from the UI).

Environment overrides: `BINARYREPAIR_ASSISTANT_PROVIDER_KEY` / `DEEPSEEK_API_KEY`,
`BINARYREPAIR_ASSISTANT_MODEL` / `DEEPSEEK_MODEL`,
`BINARYREPAIR_ASSISTANT_PROVIDER_BASE_URL` / `DEEPSEEK_BASE_URL`.

Screenshots: `screenshots/provider-key-status.png` (masked status in settings) and
`screenshots/provider-key-connected.png` (real connection test succeeded:
`连接成功 · 服务默认模型 (deepseek-flash)`).

Honesty note: the key test is an operator action only. It never writes a plan,
audit report or verdict, and no audit evidence is derived from it.

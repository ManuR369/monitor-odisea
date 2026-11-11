# monitor-dune

Avisa por Telegram apenas aparecen entradas de **Dune / Duna** en el
**IMAX Theatre (Norcenter)** de Showcase.

- Chequea cada 30 segundos con 2 pedidos HTTP (sin navegador).
- Corre gratis en GitHub Actions (repo público).
- Secrets necesarios: `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`.
- Avisa una sola vez por película (guarda lo avisado en `dune_avisadas.json`).

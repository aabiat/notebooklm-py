# NotebookLM personal en ChatGPT: auditoría y alternativa lista

Revisión: 15 de octubre de 2026 (CDMX). Código auditado: `4188d7e26a07b6b94b67bf95041c81bc1530c508`, versión `0.8.5`.

## Decisión sobre Sites

**El servidor existente no puede desplegarse directamente en el runtime soportado de ChatGPT Sites.** Sites publica Workers y exige un endpoint HTTP MCP sin estado. Su flujo de publicación no ofrece un contenedor Python, ejecución de `notebooklm-mcp`/Uvicorn ni montaje POSIX persistente para este proyecto.

La incompatibilidad concreta no es el protocolo MCP:

| Necesidad del código existente | Situación en Sites |
| --- | --- |
| Python >=3.10, `fastmcp==4.1.0`, servidor ASGI/Uvicorn | El flujo soportado de Sites empaqueta un Worker, no este proceso Python o su Dockerfile |
| Cliente asyncio ligado a un event loop por el lifespan del proceso | No se garantiza la vida de ese proceso entre peticiones |
| Keepalive/rotación de cookies y `chat_start`/`chat_status` con tareas en memoria | Requiere conservar proceso, cliente y registro de tareas |
| Perfil de Google y OAuth en archivos actualizables con locks y escritura atómica | D1/R2 no son un montaje POSIX intercambiable con estos archivos |
| Playwright/Chromium para login interactivo (opcional en ejecución normal) | No hay ejecución de ese navegador en el flujo soportado de Sites |

**Distinción:** Cloudflare ofrece Python Workers/ASGI en su propia plataforma. Eso no demuestra que Sites acepte ese despliegue ni que esta aplicación sea compatible sin adaptación. No se hizo una publicación fallida a propósito: el contrato del runtime y el código ya muestran los impedimentos. Una prueba local de Python tampoco probaría compatibilidad en Sites.

Un Site podría actuar como proxy hacia el servidor Python externo y generar su plugin. Seguiría necesitando hosting externo y agregaría otro componente; no es la alternativa más sencilla para este uso personal. Reescribir las 38 herramientas en TypeScript o adaptar persistencia/lifespans se sale del objetivo de reutilizar la lógica actual.

## Qué se reutiliza

No se modifica `src/`, `pyproject.toml`, `uv.lock`, el Dockerfile ni los Compose existentes. Se añaden archivos bajo `deploy/chatgpt/` en una rama independiente; `main` permanece intacta.

- `../Dockerfile`: Python 3.12, instala **este checkout** con `[mcp,headless]`, ejecuta como usuario sin privilegios.
- `../docker-compose.yml` y `../docker-compose.build.yml`: contenedor persistente, perfil Google y estado OAuth separados, puerto del host limitado a `127.0.0.1`, túnel HTTPS Cloudflare.
- `compose.yml`: activa HTTP MCP sin sesión (`FASTMCP_STATELESS_HTTP=true`) y deshabilita el widget experimental. Esto elimina la sesión HTTP; **no** elimina el estado del cliente Python y sus tareas.
- `prepare.py`: solicita secretos con entrada oculta y crea configuración fuera del checkout, permisos 0700/0600, sin sobrescribir credenciales existentes.
- `verify_mcp.py`: comprueba 401, handshake, 38 herramientas, listado real y consulta; evita imprimir contenido privado.
- `plugin-template/`: manifiestos portables HTTP; OAuth DCR se configura al registrar la conexión en ChatGPT. Son una plantilla, no un plugin registrado o instalado. No contienen secretos ni un endpoint activo.

## Las 38 herramientas verificadas

| Dominio | Herramientas |
| --- | --- |
| Notebooks (5) | `notebook_list`, `notebook_create`, `notebook_describe`, `notebook_rename`, `notebook_delete` |
| Fuentes (10) | `source_list`, `source_read`, `source_rename`, `source_delete`, `source_wait`, `source_add`, `source_add_drive_file`, `source_list_play_books`, `source_add_play_book`, `await_upload` |
| Chat (6) | `chat_ask`, `chat_start`, `chat_status`, `chat_cancel`, `chat_configure`, `suggest_prompts` |
| Notas (1) | `note_save` |
| Studio (7) | `studio_list`, `studio_generate`, `studio_status`, `studio_download`, `studio_rename`, `studio_retry`, `studio_delete` |
| Investigación (4) | `research_start`, `research_status`, `research_import`, `research_cancel` |
| Compartir (4) | `share_status`, `share_set_access`, `share_set_user`, `share_remove_user` |
| Diagnóstico (1) | `server_info` |

Los borrados exigen `confirm=true`; los cambios que amplían acceso tienen su propia confirmación. Se conserva ese comportamiento. El servidor es single-tenant: quien autoriza el plugin accede al perfil configurado, incluyendo sus notebooks propios y compartidos; no implementa una selección de notebooks por usuario.

## Autenticación y almacenamiento

Hay dos capas independientes:

1. **ChatGPT → MCP:** OAuth 2.1 existente, registro dinámico, PKCE, contraseña propia del MCP y tokens persistidos. Esa contraseña **no es la contraseña de Google**. El bearer adicional permite pruebas internas. La instancia usa un solo perfil.
2. **MCP → Google:** cliente no oficial, backend Web mediante cookies de sesión y RPC interno de NotebookLM, no una API pública oficial con OAuth Google estándar. El backend Android/gRPC es opcional y no se selecciona aquí. El login Google conectado a Drive/Gmail en ChatGPT no autentica este paquete.

El perfil se monta con lectura/escritura: renovar cookies requiere persistirlas. El estado OAuth se monta aparte. Los secretos se guardan solo en el host, fuera del repositorio y del contexto de build; los directorios son 0700 y `runtime.env` se crea 0600. El contenedor recibe secretos por entorno. Esto no cifra el disco: usa un host y copias de seguridad protegidos. No ejecutes `docker compose config`, no publiques `docker inspect` ni logs de depuración sin revisar: pueden incluir el entorno.

El login normal con cookies es la primera opción. `--master-token` permite recuperación headless más duradera, pero guarda una credencial de alcance amplio de Google; es opcional. Si se utiliza, trátala como credencial de cuenta completa. No pegues cookies, tokens, contraseñas ni el perfil en ChatGPT o GitHub.

## Despliegue en un host persistente Linux

Requisitos pendientes: un host con Docker Compose, acceso a ese host, un dominio/ruta estable de Cloudflare Tunnel y un login Google hecho por el titular. El equipo de esta revisión no tiene Docker ni credenciales Google, túnel o acceso a ese host. Estos pasos están preparados, no ejecutados en producción.

### 1. Abrir el checkout y autenticar Google

En el equipo que usarás para el login, con navegador gráfico:

```bash
git clone --branch deploy/chatgpt-personal-mcp https://github.com/aabiat/notebooklm-py.git
cd notebooklm-py
uv venv .venv
uv pip install --python .venv/bin/python -e '.[mcp,browser,headless]'
.venv/bin/python -m playwright install chromium
umask 077
NOTEBOOKLM_HOME="$HOME/.local/state/notebooklm-chatgpt/google" \
  .venv/bin/notebooklm --profile personal login
```

Completa Google y 2FA tú mismo en ese navegador. Si el host es headless, realiza el login en tu equipo y transfiere **el directorio completo del perfil** por SSH/SFTP al host, a un directorio privado fuera del checkout. No transfieras el perfil mediante GitHub. Alternativamente sigue el login headless/master-token documentado por upstream. El runtime no necesita Playwright cuando tiene un perfil válido; las cookies pueden expirar y requerir nuevo login.

### 2. Configurar HTTPS y secretos

En Cloudflare Tunnel, configura un hostname estable cuyo servicio sea `http://notebooklm-mcp:9420` (el sidecar está en la misma red Docker). Enruta **todo el origen**, no solo `/mcp`: OAuth necesita también metadata, registro, autorización y login. No añadas una página de login Cloudflare Access delante de las rutas que debe usar el cliente MCP.

En el host que ejecutará Docker:

```bash
python3 deploy/chatgpt/prepare.py \
  --origin https://TU-HOSTNAME \
  --profile-dir "$HOME/.local/state/notebooklm-chatgpt/google/profiles/personal"
sh deploy/chatgpt/compose.sh up -d --build
sh deploy/chatgpt/compose.sh ps
```

El asistente solicita en terminal, sin eco, una contraseña MCP aleatoria de al menos 16 caracteres URL-safe (guárdala en tu gestor) y el token de Cloudflare. Genera un bearer para pruebas sin imprimirlo. Usa el directorio `$XDG_STATE_HOME/notebooklm-chatgpt` o `~/.local/state/notebooklm-chatgpt`. Para otra ruta, pasa `--state-dir` y establece la misma ruta en `NOTEBOOKLM_CHATGPT_STATE_DIR` al usar `compose.sh`.

La imagen se construye desde el checkout; sus dependencias respetan las restricciones de upstream. La prueba de esta revisión usó Python 3.12.14 / FastMCP 4.1.0 / MCP 2.3.0 / httpx 0.28.1 / Uvicorn 0.54.0. El Dockerfile upstream no usa un lock de todas las dependencias transitivas; construir más tarde puede resolver otras versiones. No se presenta como build reproducible por digest.

### 3. Verificar realmente Google y MCP

Prueba interna usando el bearer del entorno del contenedor, sin copiarlo a argumentos:

```bash
sh deploy/chatgpt/compose.sh exec -T notebooklm-mcp \
  python /src/deploy/chatgpt/verify_mcp.py \
  --url http://127.0.0.1:9420/mcp --allow-loopback-http --discover-only
```

Con un UUID de notebook que tenga fuentes, ejecuta la prueba completa:

```bash
sh deploy/chatgpt/compose.sh exec -T notebooklm-mcp \
  python /src/deploy/chatgpt/verify_mcp.py \
  --url http://127.0.0.1:9420/mcp --allow-loopback-http \
  --notebook UUID-DEL-NOTEBOOK
```

Verificación externa desde tu equipo con navegador y el venv instalado:

```bash
.venv/bin/python deploy/chatgpt/verify_mcp.py \
  --url https://TU-HOSTNAME/mcp --oauth --notebook UUID-DEL-NOTEBOOK
```

Este último paso prueba TLS, OAuth, Google y consulta con fuentes. `chat_ask` puede agregar una conversación/turno y consumir cuota de NotebookLM. Las preguntas largas pueden superar el plazo del cliente: usa `chat_start` y consulta `chat_status` en el uso normal. No reinicies ni escales a múltiples réplicas durante una tarea: su registro vive en memoria.

### 4. Crear el plugin personal e instalarlo

En [ChatGPT Plugins](https://chatgpt.com/plugins): **+ → Add custom MCP server**. Nombre: `NotebookLM personal`; URL `https://TU-HOSTNAME/mcp`; autenticación OAuth. Crea el plugin y completa el login con la **contraseña MCP** guardada en el paso 2. Instálalo/conéctalo en tu cuenta y prueba `notebook_list`, seguido de `chat_ask` sobre un notebook elegido. No publiques este plugin en un catálogo compartido.

`prepare.py` también genera `plugin/plugin.json` y `plugin/mcp.json` fuera del checkout con el endpoint concreto, sin secretos. La configuración OAuth se selecciona en la conexión de ChatGPT, no se incluye en el manifiesto MCP portable: el esquema público 1.0.0 comprobado rechaza el campo `extensions` aunque la guía de OpenAI muestra ejemplos con él. La plantilla entregada pasa el esquema público sin ese campo. Es un paquete portable auxiliar; no sustituye registrar la conexión en ChatGPT ni demuestra que esté instalado. El plugin externo no recibe un ID automático de Sites.

Para revocar sesiones emitidas, detén el servidor, elimina el archivo privado `oauth/chatgpt.json` y reinicia; reconecta el plugin después. Cambiar solo la contraseña de acceso **no** revoca los tokens OAuth existentes.

### Si prefieres no tener un dominio público

El Compose de upstream también incluye Tailscale Funnel, pero esa ruta no se probó aquí. [Secure MCP Tunnel de OpenAI](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels) permite una conexión personal privada sin publicar el MCP: requiere `tunnel-client`, un `tunnel_id`, una clave de ejecución y asociación a tu cuenta/workspace. No se ha comprobado su disponibilidad en esta cuenta. No es hosting de Python y sigue necesitando el host persistente. No se crean recursos ni claves como parte de esta preparación.

## Evidencia y límites

- `main` remoto y checkout coincidían en `4188d7e2` al iniciar la revisión.
- 208 pruebas upstream aprobadas: manifiesto, autenticación bearer/OAuth, entrypoint, notebooks y chat. Los clientes Google están simulados; no son pruebas contra la cuenta del usuario.
- Véase `VALIDATION.md` para las pruebas de transporte y de la preparación añadida.
- No hay login Google disponible, no se listaron notebooks reales ni se ejecutaron consultas reales.
- No se construyó la imagen Docker en este entorno (Docker no está instalado).
- No hay Site publicado ni plugin registrado, instalado o conectado. No se ha solicitado ni expuesto ninguna credencial real.

## Fuentes

- Código: `src/notebooklm/mcp/{server.py,__main__.py,_auth.py,_oauth.py,_chattasks.py}`, `pyproject.toml`, `deploy/` y `tests/unit/mcp/test_manifest.py`.
- [Sites: límites soportados](https://learn.chatgpt.com/docs/sites#understand-limits-and-unsupported-uses).
- Contrato de publicación Sites inspeccionado en esta sesión: runtime Cloudflare Workers, 128 MB/isolate, conexiones HTTP, MCP `POST /mcp` stateless; D1/R2 para persistencia. No declara soporte para desplegar este proceso Python o un contenedor Docker.
- [Cloudflare Python Workers y FastAPI](https://developers.cloudflare.com/workers/languages/python/packages/fastapi/): capacidad de Cloudflare distinta de la interfaz de despliegue de Sites.
- [Empaquetar plugins y declarar OAuth DCR](https://developers.openai.com/plugins/build/plugins).
- [Conectar y probar un MCP en ChatGPT](https://developers.openai.com/plugins/deploy/connect-chatgpt).

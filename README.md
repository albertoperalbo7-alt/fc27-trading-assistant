# FC 27 Market Assistant — iPhone + Telegram + FUTBIN experimental connector

## Qué incluye
- Interfaz Streamlit adaptable a móvil.
- Saldo variable y límites de riesgo.
- Comisión de venta del 5% y beneficio neto mínimo configurable (700 por defecto).
- Importación CSV.
- Monitor de alertas por Telegram cada 5 minutos por defecto.
- Conector experimental de FUTBIN mediante un SDK comunitario no oficial.
- No automatiza compras, pujas ni ventas.

## Advertencia sobre FUTBIN
FUTBIN no publica una API de desarrollador pública oficial. El conector incluido depende de un SDK comunitario que consulta interfaces web no oficiales, que pueden cambiar o dejar de funcionar. Comprueba las condiciones de FUTBIN antes de usarlo y respeta sus límites. El conector solo analiza los conjuntos de cartas que el SDK devuelve como populares, recientes y TOTW; no equivale a un escaneo completo de todo el mercado ni garantiza que el precio pueda conseguirse dentro del juego.

EA reconoce FUTBIN y FUT.GG como sitios comunitarios aprobados para determinadas funciones de FC Community API, pero eso no convierte automáticamente este conector de precios en una API oficial.

## Requisitos
- Python 3.11 o posterior (requerido por el SDK comunitario).
- Un servidor persistente para mantener el monitor activo.
- Un bot de Telegram configurado por ti.

## Instalar en PC
```bash
python -m venv .venv
```

Windows PowerShell:
```powershell
.venv\Scripts\Activate.ps1
```

macOS/Linux:
```bash
source .venv/bin/activate
```

Instalar dependencias (el conector comunitario se instala desde su repositorio porque la versión publicada en PyPI puede no incluir los cambios para FC 27):
```bash
pip install -r requirements.txt
```

Iniciar el panel:
```bash
streamlit run app.py
```

## Configurar FUTBIN como proveedor
El archivo `provider_adapter.py` intenta usar:
- `get_popular_players()`
- `get_latest_players()`
- `get_totw()`

del paquete `futbin-sdk`, y conserva únicamente observaciones con precio PC positivo. Si FUTBIN cambia la web o el SDK deja de funcionar, el monitor mostrará un error; no inventará precios.

Configura la variable de entorno:
```text
FC27_PROVIDER_MODULE=provider_adapter
FC27_POLL_SECONDS=300
```

No se recomienda reducir el intervalo: comprueba los términos y límites de la fuente y evita consultas excesivas. El código aplica un mínimo de 60 segundos, pero eso no significa que FUTBIN autorice esa frecuencia.

## Configurar Telegram
1. En Telegram, crea un bot con `@BotFather`.
2. Configura `TELEGRAM_BOT_TOKEN` con el token del bot.
3. Configura `TELEGRAM_CHAT_ID` con el identificador del chat de destino.
4. No compartas ni subas el token a GitHub.

Variables de entorno necesarias:
```text
TELEGRAM_BOT_TOKEN=tu_token
TELEGRAM_CHAT_ID=tu_chat_id
FC27_PROVIDER_MODULE=provider_adapter
FC27_POLL_SECONDS=300
FC27_DB_PATH=market_assistant.db
```

Después de guardar el saldo y los ajustes en el panel, ejecuta el monitor en otro terminal:
```bash
python monitor.py
```

## Usarlo desde iPhone
Despliega la web en un servidor accesible por HTTPS. Abre la URL en Safari y selecciona Compartir → Añadir a pantalla de inicio. El monitor debe seguir ejecutándose en el servidor; no depende de que Safari esté abierto.

## CSV alternativo
Columnas obligatorias: `observed_at,platform,player_name,price,source`.
Opcional: `card_type`.
Los ejemplos de CSV son ilustrativos y no son cotizaciones reales.

## Estado
El conector se ha añadido al proyecto, pero no se ha validado contra una sesión real de FUTBIN desde este entorno. No se han configurado credenciales ni desplegado el servidor; por tanto, todavía no se envían alertas reales.

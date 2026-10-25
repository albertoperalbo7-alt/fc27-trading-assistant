"""
Conector experimental de FUTBIN para FC 27.

IMPORTANTE:
- No es una API oficial de FUTBIN; depende de un SDK comunitario que consulta
  endpoints web no oficiales y puede dejar de funcionar.
- Comprueba y respeta los términos de FUTBIN antes de utilizarlo de forma continua.
- La cobertura es de jugadores populares, recientes y TOTW devueltos por el SDK,
  no de todas las cartas ni de cada listado de la casa de subastas.
- No realiza compras, pujas ni ventas.
"""
import asyncio
from datetime import datetime, timezone

import pandas as pd
from futbin_sdk import FutbinClient

SOURCE_NAME = "FUTBIN (SDK comunitario no oficial)"

async def _fetch():
    rows = []
    async with FutbinClient(year=27) as client:
        # These documented SDK methods return player/card data; coverage depends
        # on the upstream website and the installed SDK version.
        batches = [
            ("popular", await client.get_popular_players()),
            ("latest", await client.get_latest_players()),
            ("totw", await client.get_totw()),
        ]
        observed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        seen = set()
        for group_name, players in batches:
            for player in players:
                name = str(getattr(player, "name", "") or "").strip()
                price = getattr(player, "price_pc", None)
                player_id = getattr(player, "futbin_id", None)
                if not name or price is None:
                    continue
                try:
                    price = int(price)
                except (TypeError, ValueError):
                    continue
                # Do not turn missing/zero prices into a valid quote.
                if price <= 0:
                    continue
                key = (str(player_id or name), group_name)
                if key in seen:
                    continue
                seen.add(key)
                rows.append({
                    "observed_at": observed_at,
                    "platform": "PC",
                    "player_name": name,
                    "card_type": group_name,
                    "price": price,
                    "source": SOURCE_NAME,
                })
    return pd.DataFrame(rows, columns=[
        "observed_at", "platform", "player_name", "card_type", "price", "source"
    ])

def fetch_prices() -> pd.DataFrame:
    """Devuelve precios PC de los conjuntos que el SDK consiga consultar."""
    try:
        return asyncio.run(_fetch())
    except RuntimeError as exc:
        # Clear diagnostic for event-loop incompatibility rather than fake data.
        raise RuntimeError(
            "No se pudo ejecutar el conector FUTBIN en este entorno. "
            "Prueba Python 3.11+ y verifica la versión del SDK."
        ) from exc

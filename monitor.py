"""
Monitor de alertas para FC 27 Market Assistant.

Este proceso no incluye una fuente de precios inventada. Implementa un módulo
provider_adapter.py propio solo cuando exista una fuente autorizada/documentada.
El proveedor debe exponer fetch_prices() y devolver un DataFrame con columnas:
observed_at, platform, player_name, card_type, price, source.
"""
import importlib
import os
import sqlite3
import time
from datetime import datetime, timezone

import pandas as pd
import requests

DB_PATH = os.getenv("FC27_DB_PATH", "market_assistant.db")
POLL_SECONDS = max(60, int(os.getenv("FC27_POLL_SECONDS", "300")))
FEE_RATE = 0.05

def connect():
    return sqlite3.connect(DB_PATH)

def net_sale(price):
    return int(int(price) * (1 - FEE_RATE))

def net_profit(buy, sell):
    return net_sale(sell) - int(buy)

def send_telegram(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[TELEGRAM PENDIENTE] Credenciales ausentes; no se envió ninguna notificación.")
        return False
    # Official Telegram Bot API endpoint pattern. No token is stored in source code.
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    response = requests.post(url, data={"chat_id": chat_id, "text": message}, timeout=15)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError("Telegram API no confirmó el envío.")
    return True

def read_settings():
    with connect() as con:
        rows = con.execute("SELECT key, value FROM settings").fetchall()
    settings = {k: v for k, v in rows}
    return {
        "balance": int(settings.get("balance", "40000")),
        "reserve_pct": int(settings.get("reserve_pct", "30")),
        "position_pct": int(settings.get("position_pct", "15")),
        "min_profit": int(settings.get("min_profit", "700")),
    }

def record_observations(df):
    needed = {"observed_at","platform","player_name","price","source"}
    if not needed.issubset(df.columns):
        raise ValueError(f"Proveedor debe devolver columnas: {sorted(needed)}")
    if "card_type" not in df.columns:
        df = df.copy()
        df["card_type"] = ""
    with connect() as con:
        df[["observed_at","platform","player_name","card_type","price","source"]].to_sql(
            "price_observations", con, if_exists="append", index=False
        )

def alert_once(key, message):
    with connect() as con:
        found = con.execute("SELECT 1 FROM sent_alerts WHERE alert_key=?", (key,)).fetchone()
        if found:
            return
        # Store before sending to reduce duplicate alerts after restarts.
        con.execute("INSERT INTO sent_alerts(alert_key,sent_at) VALUES(?,?)",
                    (key, datetime.now(timezone.utc).isoformat()))
    send_telegram(message)

def analyze_and_alert(df, settings):
    df = df.copy()
    df["observed_at"] = pd.to_datetime(df["observed_at"], errors="coerce", utc=True)
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df = df.dropna(subset=["observed_at","price","player_name"])
    now = pd.Timestamp.now(tz="UTC")
    fresh = df[df["observed_at"] >= now - pd.Timedelta(days=7)]
    if fresh.empty:
        print("No hay observaciones recientes para analizar.")
        return
    keys = ["platform","player_name","card_type"]
    latest = fresh.sort_values("observed_at").groupby(keys, dropna=False).tail(1).copy()
    med = fresh.groupby(keys, dropna=False)["price"].median().rename("median_7d")
    latest = latest.merge(med, on=keys, how="left")
    balance = settings["balance"]
    reserve = int(balance * settings["reserve_pct"] / 100)
    investable = max(0, balance - reserve)
    max_position = int(balance * settings["position_pct"] / 100)
    min_profit = settings["min_profit"]
    for _, row in latest.iterrows():
        if str(row["platform"]).lower() != "pc":
            continue
        if now - row["observed_at"] > pd.Timedelta(hours=6):
            continue
        target = int(round(row["median_7d"]))
        max_buy = max(0, net_sale(target) - min_profit)
        current = int(row["price"])
        if current <= max_buy and current <= investable and current <= max_position:
            key = f'{row["platform"]}|{row["player_name"]}|{row.get("card_type","")}|{current}|{target}'
            message = (
                "FC 27 Market Assistant — oportunidad para revisar\n"
                f'Carta: {row["player_name"]} ({row.get("card_type","")})\n'
                f'Plataforma: PC\nPrecio observado: {current:,} monedas\n'
                f'Precio objetivo orientativo: {target:,}\n'
                f'Compra máxima calculada: {max_buy:,}\n'
                f'Beneficio neto estimado: {net_profit(current, target):,} monedas\n'
                f'Comisión asumida: 5 %\n'
                "Verifica que el precio siga disponible. No se ha ejecutado ninguna operación."
            ).replace(",", ".")
            alert_once(key, message)

def main():
    provider_module = os.getenv("FC27_PROVIDER_MODULE")
    if not provider_module:
        print("Monitor detenido: configura FC27_PROVIDER_MODULE con un adaptador de proveedor autorizado.")
        print("No se han consultado precios ni enviado notificaciones.")
        return
    provider = importlib.import_module(provider_module)
    if not hasattr(provider, "fetch_prices"):
        raise RuntimeError("El módulo proveedor debe implementar fetch_prices().")
    print(f"Monitor iniciado. Intervalo configurado: {POLL_SECONDS} segundos.")
    while True:
        try:
            df = provider.fetch_prices()
            if not isinstance(df, pd.DataFrame):
                raise TypeError("fetch_prices() debe devolver un pandas DataFrame.")
            record_observations(df)
            analyze_and_alert(df, read_settings())
        except Exception as exc:
            print(f"Error en ciclo de monitor: {type(exc).__name__}: {exc}")
        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()

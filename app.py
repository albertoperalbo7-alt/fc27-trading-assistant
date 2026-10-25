import os
import sqlite3
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st

DB_PATH = Path(os.getenv("FC27_DB_PATH", "market_assistant.db"))
FEE_RATE = 0.05

st.set_page_config(
    page_title="FC 27 Market Assistant",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
.block-container {padding-top: 1rem; padding-bottom: 2rem; max-width: 1100px;}
div[data-testid="stMetric"] {border: 1px solid rgba(128,128,128,.25); padding: .7rem; border-radius: 12px;}
.stButton button {width: 100%; min-height: 2.8rem; border-radius: 12px;}
@media (max-width: 700px) {
  .block-container {padding-left: .8rem; padding-right: .8rem;}
  h1 {font-size: 1.65rem !important;}
  h2 {font-size: 1.25rem !important;}
}
</style>
""", unsafe_allow_html=True)

def connect():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with connect() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS price_observations (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          observed_at TEXT NOT NULL,
          platform TEXT NOT NULL,
          player_name TEXT NOT NULL,
          card_type TEXT DEFAULT '',
          price INTEGER NOT NULL,
          source TEXT NOT NULL
        )""")
        con.execute("""
        CREATE TABLE IF NOT EXISTS trades (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          traded_at TEXT NOT NULL,
          player_name TEXT NOT NULL,
          buy_price INTEGER NOT NULL,
          target_sell_price INTEGER NOT NULL,
          quantity INTEGER NOT NULL,
          status TEXT NOT NULL,
          actual_sell_price INTEGER,
          balance_at_entry INTEGER
        )""")
        con.execute("""
        CREATE TABLE IF NOT EXISTS settings (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        )""")
        con.execute("""
        CREATE TABLE IF NOT EXISTS sent_alerts (
          alert_key TEXT PRIMARY KEY,
          sent_at TEXT NOT NULL
        )""")

def get_setting(key, default):
    with connect() as con:
        row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

def set_setting(key, value):
    with connect() as con:
        con.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, str(value)))

def load_prices():
    with connect() as con:
        return pd.read_sql_query("SELECT * FROM price_observations ORDER BY observed_at DESC", con)

def load_trades():
    with connect() as con:
        return pd.read_sql_query("SELECT * FROM trades ORDER BY traded_at DESC", con)

def net_sale(price):
    return int(int(price) * (1 - FEE_RATE))

def profit(buy, sell):
    return net_sale(sell) - int(buy)

def break_even(buy):
    p = int(int(buy) / (1 - FEE_RATE))
    while net_sale(p) < int(buy):
        p += 1
    return p

init_db()

st.title("📈 FC 27 Market Assistant")
st.caption("Diseño móvil · Saldo variable · Plataforma PC · Avisos por Telegram (pendientes de configurar)")

with st.sidebar:
    st.subheader("⚙️ Ajustes")
    balance = st.number_input("Saldo actual (monedas)", min_value=0, value=int(get_setting("balance", 40000)), step=1000)
    reserve_pct = st.slider("Reserva sin invertir (%)", 10, 70, int(get_setting("reserve_pct", 30)))
    position_pct = st.slider("Máximo por operación (%)", 5, 30, int(get_setting("position_pct", 15)))
    min_profit = st.number_input("Beneficio neto mínimo por carta", min_value=0, value=int(get_setting("min_profit", 700)), step=100)
    st.caption("El saldo y los límites se recalculan en este panel. No se ejecutan operaciones en EA.")
    if st.button("Guardar ajustes"):
        set_setting("balance", balance)
        set_setting("reserve_pct", reserve_pct)
        set_setting("position_pct", position_pct)
        set_setting("min_profit", min_profit)
        st.success("Ajustes guardados en la base local.")

reserve = int(balance * reserve_pct / 100)
investable = max(0, int(balance - reserve))
max_position = int(balance * position_pct / 100)

m1, m2 = st.columns(2)
m1.metric("Saldo", f"{balance:,}".replace(",", "."))
m2.metric("Capital invertible", f"{investable:,}".replace(",", "."))
m3, m4 = st.columns(2)
m3.metric("Reserva", f"{reserve:,}".replace(",", "."))
m4.metric("Límite por operación", f"{max_position:,}".replace(",", "."))

st.info("Estado: interfaz preparada. La lectura automática de precios y los avisos reales requieren configurar un proveedor autorizado, credenciales de Telegram y un servidor que ejecute el monitor.")

tabs = st.tabs(["🎯 Oportunidades", "🔔 Alertas", "🧮 Calculadora", "📚 Historial", "📥 Datos"])

with with tabs[0]:
    st.subheader("Oportunidades")

    if st.button("🔄 Actualizar precios desde FUTBIN", type="primary"):
        try:
            from provider_adapter import fetch_prices

            with st.spinner("Consultando precios de FUTBIN..."):
                new_prices = fetch_prices()

            if new_prices.empty:
                st.warning(
                    "FUTBIN no ha devuelto precios. "
                    "Puede que la fuente no esté disponible."
                )
            else:
                required = {
                    "observed_at", "platform", "player_name",
                    "card_type", "price", "source"
                }

                if not required.issubset(new_prices.columns):
                    st.error("El conector ha devuelto columnas inesperadas.")
                else:
                    new_prices = new_prices[list(required)].copy()
                    new_prices["price"] = pd.to_numeric(
                        new_prices["price"], errors="coerce"
                    )
                    new_prices = new_prices.dropna(subset=["price"])
                    new_prices = new_prices[new_prices["price"] > 0]
                    new_prices["price"] = new_prices["price"].astype(int)

                    if new_prices.empty:
                        st.warning("No se han encontrado precios válidos.")
                    else:
                        with connect() as con:
                            new_prices[
                                [
                                    "observed_at", "platform", "player_name",
                                    "card_type", "price", "source"
                                ]
                            ].to_sql(
                                "price_observations",
                                con,
                                if_exists="append",
                                index=False
                            )

                        st.success(
                            f"Se han guardado {len(new_prices)} precios."
                        )
                        st.rerun()

        except Exception as e:
            st.error(f"No se pudieron actualizar los precios: {e}")

    prices = load_prices()

    if prices.empty:
        st.warning("Todavía no hay observaciones de precios. Importa un CSV real en la pestaña Datos.")
    else:
        prices["observed_at"] = pd.to_datetime(prices["observed_at"], errors="coerce")
        now = pd.Timestamp.now()
        latest = prices.sort_values("observed_at").groupby(
            ["platform", "player_name", "card_type"], dropna=False
        ).tail(1).copy()
        recent = prices[prices["observed_at"] >= now - pd.Timedelta(days=7)]
        medians = recent.groupby(["platform", "player_name", "card_type"], dropna=False)["price"].median().rename("median_7d")
        latest = latest.merge(medians, on=["platform", "player_name", "card_type"], how="left")
        latest["target_sell"] = latest["median_7d"].round().astype("Int64")
        latest["max_buy"] = latest["target_sell"].apply(
            lambda x: max(0, net_sale(int(x)) - int(min_profit)) if pd.notna(x) else 0
        )
        latest["net_profit_at_median"] = latest.apply(
            lambda r: profit(int(r["price"]), int(r["target_sell"])) if pd.notna(r["target_sell"]) else 0, axis=1
        )
        latest["fresh"] = latest["observed_at"] >= now - pd.Timedelta(hours=6)
        latest["capital_ok"] = (latest["price"] <= max_position) & (latest["price"] <= investable)
        latest["signal"] = latest.apply(
            lambda r: "REVISAR COMPRA" if r["fresh"] and pd.notna(r["median_7d"]) and
              r["price"] <= r["max_buy"] and r["capital_ok"]
              else ("PRECIO ANTIGUO" if not r["fresh"] else "ESPERAR / REVISAR"), axis=1
        )
        view = latest[["player_name","card_type","platform","price","median_7d","max_buy","target_sell","net_profit_at_median","signal","observed_at","source"]]
        st.dataframe(view.sort_values("net_profit_at_median", ascending=False), use_container_width=True, hide_index=True)
        st.caption("La mediana de 7 días es una referencia básica, no una predicción. Confirma la disponibilidad del precio antes de actuar.")

with tabs[1]:
    st.subheader("Alertas por Telegram")
    st.write("El monitor separado puede revisar el mercado cada 5 minutos, siempre que la fuente permita esa frecuencia.")
    st.write("Beneficio neto mínimo actual:", f"**{min_profit:,} monedas por carta**".replace(",", "."))
    telegram_ready = bool(os.getenv("TELEGRAM_BOT_TOKEN")) and bool(os.getenv("TELEGRAM_CHAT_ID"))
    source_ready = bool(os.getenv("FC27_PROVIDER_MODULE"))
    a, b = st.columns(2)
    a.metric("Telegram", "Credenciales detectadas" if telegram_ready else "Pendiente")
    b.metric("Fuente de precios", "Módulo configurado" if source_ready else "Pendiente")
    st.markdown("""
**Configuración necesaria**
1. Crea un bot mediante `@BotFather` en Telegram y copia su token a `TELEGRAM_BOT_TOKEN`.
2. Obtén tu `TELEGRAM_CHAT_ID` mediante un método fiable y privado.
3. Configura un adaptador para un proveedor de precios autorizado; el proyecto no inventa una URL ni presupone una API.
4. Ejecuta `python monitor.py` en un servidor persistente. Este monitor está diseñado para enviar alertas, no para comprar o vender.
""")
    st.code("TELEGRAM_BOT_TOKEN=tu_token\nTELEGRAM_CHAT_ID=tu_chat_id\nFC27_PROVIDER_MODULE=provider_adapter", language="text")

with tabs[2]:
    st.subheader("Calculadora con comisión del 5 %")
    col1, col2 = st.columns(2)
    with col1:
        buy = st.number_input("Precio de compra", min_value=0, value=8000, step=100, key="calc_buy")
    with col2:
        sell = st.number_input("Precio de venta", min_value=0, value=9500, step=100, key="calc_sell")
    qty = st.number_input("Número de cartas", min_value=1, value=1, step=1, key="calc_qty")
    net = profit(buy, sell)
    st.metric("Beneficio neto total", f"{net * qty:,}".replace(",", "."))
    st.write(f"Punto de equilibrio por carta: **{break_even(buy):,} monedas**".replace(",", "."))
    st.write(f"Compra máxima para ganar {min_profit:,} netas si vendes a {sell:,}: **{max(0, net_sale(sell)-min_profit):,}**".replace(",", "."))

with tabs[3]:
    st.subheader("Historial de operaciones")
    trades = load_trades()
    if trades.empty:
        st.info("No hay operaciones registradas.")
    else:
        trades["effective_sell"] = trades.apply(
            lambda r: int(r["actual_sell_price"]) if pd.notna(r["actual_sell_price"]) and int(r["actual_sell_price"]) > 0 else int(r["target_sell_price"]), axis=1
        )
        trades["profit_per_card"] = trades.apply(lambda r: profit(int(r["buy_price"]), int(r["effective_sell"])), axis=1)
        trades["profit_total"] = trades["profit_per_card"] * trades["quantity"]
        st.dataframe(trades, use_container_width=True, hide_index=True)
        st.metric("Beneficio estimado acumulado", f"{int(trades['profit_total'].sum()):,}".replace(",", "."))

with tabs[4]:
    st.subheader("Importar datos de precios")
    st.write("Carga un CSV de una fuente que permita su exportación/uso.")
    st.code("observed_at,platform,player_name,card_type,price,source\n2026-10-24T18:00:00,PC,Carta de ejemplo,Oro único,1200,fuente_autorizada", language="csv")
    st.caption("La fila es ficticia, no es un precio real.")
    uploaded = st.file_uploader("CSV de precios", type=["csv"])
    if uploaded:
        try:
            df = pd.read_csv(uploaded)
            required = {"observed_at","platform","player_name","price","source"}
            missing = required - set(df.columns)
            if missing:
                st.error("Faltan columnas: " + ", ".join(sorted(missing)))
            else:
                if "card_type" not in df:
                    df["card_type"] = ""
                df["price"] = pd.to_numeric(df["price"], errors="coerce")
                df = df.dropna(subset=["observed_at","player_name","price"])
                df["price"] = df["price"].astype(int)
                for c in ["platform","player_name","card_type","source"]:
                    df[c] = df[c].fillna("").astype(str)
                st.dataframe(df.head(20), use_container_width=True)
                if st.button("Guardar observaciones", type="primary"):
                    with connect() as con:
                        df[["observed_at","platform","player_name","card_type","price","source"]].to_sql("price_observations", con, if_exists="append", index=False)
                    st.success(f"Guardadas {len(df)} observaciones.")
        except Exception as e:
            st.error(f"No se pudo leer el CSV: {e}")

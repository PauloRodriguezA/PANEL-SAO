import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import unicodedata
import base64
import hashlib
import html
import re
import os
import sqlite3
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo
from regiones_chile import corregir_region_por_ciudad, normalizar_region_chile, region_por_ciudad_o_comuna

# =========================================================
# CONFIG
# =========================================================

st.set_page_config(
    page_title="Panel de Adherencia Entel",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

APP_CODE_PATH = Path(__file__).resolve()
APP_HASH_PATH = APP_CODE_PATH.with_name(APP_CODE_PATH.name + ".sha256")


def verificar_integridad_codigo():
    # Seguridad SHA desactivada temporalmente mientras el panel sigue en desarrollo.
    # Cuando el panel quede finalizado, se puede reactivar el control de integridad.
    return


verificar_integridad_codigo()

# =========================================================
# RUTAS
# =========================================================

APP_DIR = Path(__file__).resolve().parent
ASSETS_DIR = APP_DIR / "assets"
PST_DIR_OFICIAL = Path(r"C:\Users\artof\OneDrive\Paulo Rodriguez\PYTHON\PST")


def resolver_pst_dir_default_panel():
    if PST_DIR_OFICIAL.exists():
        return PST_DIR_OFICIAL
    if APP_DIR.parent.name.upper() == "ST" and len(APP_DIR.parents) >= 3:
        return APP_DIR.parents[2] / "PST"
    return APP_DIR.parent / "PST"


PST_DIR = Path(os.environ.get("PST_CORREO_DIR", resolver_pst_dir_default_panel())).expanduser()

DISPONIBILIDAD_ESTADOS = ["Cumple", "No cumple", "Reclamo"]

LOGO_ECC = ASSETS_DIR / "logo-ecc-transparente.png"
LOGO_ECC_ICONO = ASSETS_DIR / "logo-ecc-icono.png"
LOGO_ECC_NEGRO = ASSETS_DIR / "logo-ecc.png"

SERVICIOS_CONFIG = {
    "IBM": {
        "archivo": "IBM_2026.xlsx",
        "disponibilidad": "DISPONIBILIDAD_IBM_2026.csv",
        "reclamos": "RECLAMOS_IBM_2026.csv",
        "pst": PST_DIR / "pst-ibm.pst",
        "logo": ASSETS_DIR / "IBM-transparente.png",
        "epa_dir": "EPA",
        "epa_db": "epa_entel.sqlite3",
        "epa_db_legacy": "epa_ibm.sqlite3",
        "participa_disponibilidad": True,
        "participa_reclamos": True,
        "participa_uso_herramienta": True,
    },
    "SAO": {
        "archivo": "SAO_2026.xlsx",
        "disponibilidad": "DISPONIBILIDAD_SAO_2026.csv",
        "reclamos": "RECLAMOS_SAO_2026.csv",
        "pst": PST_DIR / "pst-sao.pst",
        "logo": ASSETS_DIR / "LOGO-SAO-transparente.png",
        "epa_dir": "EPA-SAO",
        "epa_db": "epa_entel_sao.sqlite3",
        "epa_db_legacy": "epa_entel.sqlite3",
        "participa_disponibilidad": True,
        "participa_reclamos": True,
        "participa_uso_herramienta": True,
    },
    "ECC": {
        "archivo": "ECC_2026.xlsx",
        "disponibilidad": "",
        "reclamos": "",
        "pst": None,
        "logo": LOGO_ECC,
        "epa_dir": "EPA-ECC",
        "epa_db": "epa_ecc.sqlite3",
        "epa_db_legacy": "epa_ecc.sqlite3",
        "participa_disponibilidad": False,
        "participa_reclamos": False,
        "participa_uso_herramienta": True,
    },
}
SERVICIO_TODO = "Todo"
SERVICIO_OPCIONES = list(SERVICIOS_CONFIG.keys()) + [SERVICIO_TODO]
SERVICIO_FIJO_ARCHIVO = APP_DIR / "servicio_fijo.txt"


def servicio_fijo_desde_contexto():
    servicio_env = os.environ.get("PANEL_SERVICIO_FIJO", "").strip().upper()
    if servicio_env in SERVICIOS_CONFIG:
        return servicio_env
    try:
        servicio_archivo = SERVICIO_FIJO_ARCHIVO.read_text(encoding="utf-8-sig").strip().upper()
    except OSError:
        servicio_archivo = ""
    if servicio_archivo in SERVICIOS_CONFIG:
        return servicio_archivo
    if APP_DIR.parent.name.upper() == "ST" and APP_DIR.name.upper() in SERVICIOS_CONFIG:
        return APP_DIR.name.upper()
    return ""


SERVICIO_FIJO = servicio_fijo_desde_contexto()
MODO_GERENCIAL = not SERVICIO_FIJO


def servicio_default_gerencial():
    servicio_env = os.environ.get("PANEL_SERVICIO_DEFAULT", "").strip()
    if servicio_env in SERVICIO_OPCIONES:
        return servicio_env
    if APP_DIR.name.upper() in {"PANEL_PUBLICAR_GIT_TODO", "PUBLICAR_GIT_PANEL", "PANEL_GIT_TODO"}:
        return SERVICIO_TODO
    return "IBM"

def imagen_data_uri(ruta):
    ruta = str(ruta)
    mime = "image/png" if ruta.lower().endswith(".png") else "image/jpeg"
    with open(ruta, "rb") as img_file:
        return f"data:{mime};base64," + base64.b64encode(img_file.read()).decode("ascii")

LOGO_ECC_DATA = imagen_data_uri(LOGO_ECC)
LOGO_ECC_ICONO_DATA = imagen_data_uri(LOGO_ECC_ICONO)

with st.sidebar:
    st.markdown(
        f"""
        <div class="sidebar-logo-shell">
            <img class="sidebar-logo-img" src="{LOGO_ECC_DATA}" alt="Entel Connect" draggable="false">
        </div>
        """,
        unsafe_allow_html=True
    )

    if MODO_GERENCIAL:
        servicio_default = st.session_state.get("servicio_tecnico", servicio_default_gerencial())
        if servicio_default not in SERVICIO_OPCIONES:
            servicio_default = servicio_default_gerencial()
        st.markdown('<span class="filter-anchor filter-anchor-service"></span>', unsafe_allow_html=True)
        servicio_actual = st.pills(
            "Servicio Técnico",
            SERVICIO_OPCIONES,
            default=servicio_default,
            selection_mode="single",
            key="servicio_tecnico_pills",
            width="stretch",
        ) or servicio_default
        st.session_state["servicio_tecnico"] = servicio_actual
    else:
        servicio_actual = SERVICIO_FIJO
        st.session_state["servicio_tecnico"] = servicio_actual

SERVICIO_ACTUAL = servicio_actual
SERVICIO_COMPARATIVO = SERVICIO_ACTUAL == SERVICIO_TODO
SERVICIOS_ACTIVOS = list(SERVICIOS_CONFIG.keys()) if SERVICIO_COMPARATIVO else [SERVICIO_ACTUAL]
SERVICIO_TITULO = "IBM + SAO + ECC" if SERVICIO_COMPARATIVO else SERVICIO_ACTUAL
SERVICIO_CONFIG = SERVICIOS_CONFIG[SERVICIOS_ACTIVOS[0]]

FILTROS_DEFAULT_VERSION = "2026-07-13-zona-tecnico-v3"
servicio_anterior_filtros = st.session_state.get("_servicio_filtros_actual")
reiniciar_filtros = (
    (servicio_anterior_filtros is not None and servicio_anterior_filtros != SERVICIO_ACTUAL)
    or st.session_state.get("_filtros_default_version") != FILTROS_DEFAULT_VERSION
)
if reiniciar_filtros:
    claves_a_limpiar = [
        key for key in st.session_state.keys()
        if key.startswith(("reg_", "tec_", "mes_", "sem_", "cli_", "disp_cli_", "disp_zona_", "disp_coord_", "disp_estado_"))
        or key in {
            "disp_cli_pills", "disp_zona_pills", "disp_estado_pills", "disp_mes_pills",
            "semana_pills", "disp_semana_pills",
            "toggle_clientes_disponibilidad_pills_empty_intent",
            "toggle_zonas_disponibilidad_pills_empty_intent",
            "toggle_estados_disponibilidad_pills_empty_intent",
            "toggle_meses_disponibilidad_pills_empty_intent",
            "toggle_semanas_pills_empty_intent",
            "toggle_semanas_disponibilidad_pills_empty_intent",
        }
        or key.endswith(("_empty_intent", "_force_all"))
    ]
    for key in claves_a_limpiar:
        st.session_state.pop(key, None)
st.session_state["_servicio_filtros_actual"] = SERVICIO_ACTUAL
st.session_state["_filtros_default_version"] = FILTROS_DEFAULT_VERSION

ARCHIVO = APP_DIR / str(SERVICIO_CONFIG["archivo"])
EPA_DIR = APP_DIR / str(SERVICIO_CONFIG["epa_dir"])
EPA_DB = EPA_DIR / str(SERVICIO_CONFIG["epa_db"])
EPA_DB_LEGACY = EPA_DIR / str(SERVICIO_CONFIG["epa_db_legacy"])
DISPONIBILIDAD_CACHE = APP_DIR / str(SERVICIO_CONFIG["disponibilidad"])
RECLAMOS_CACHE = APP_DIR / str(SERVICIO_CONFIG["reclamos"])
PST_DISPONIBILIDAD = SERVICIO_CONFIG["pst"]
LOGO_ST_DATA = "" if SERVICIO_COMPARATIVO else imagen_data_uri(SERVICIO_CONFIG["logo"])
LOGO_ST_CLASS = "brand-lockup-ecc" if SERVICIO_ACTUAL == "ECC" else "brand-lockup-ibm"

APP_OWNER = f"Entel Connect / {SERVICIO_TITULO} - Uso interno"
APP_SIGNATURE = f"ECONNECT-{SERVICIO_TITULO}-OPERACIONES-2026"

SAO_COORDINADORES_AUDITADOS = {
    "d.galarce@saocomputacion.cl": "Daniel Galarce",
    "pia.ossandon@saocomputacion.cl": "Pia Ossandon",
    "pia.saocomputacion@gmail.com": "Pia Ossandon",
    "angelicafuentes1@saocomputacion.cl": "Angelica Fuentes",
}
SAO_COORDINADORES_NOMBRES = {
    "daniel galarce": "Daniel Galarce",
    "pia ossandon": "Pia Ossandon",
    "angelica fuentes": "Angelica Fuentes",
}


def correo_limpio_panel(valor):
    return str(valor or "").strip().lower()


def nombre_coordinador_sao(valor_nombre="", valor_correo=""):
    correo = correo_limpio_panel(valor_correo)
    if correo in SAO_COORDINADORES_AUDITADOS:
        return SAO_COORDINADORES_AUDITADOS[correo]
    nombre_como_correo = correo_limpio_panel(valor_nombre)
    if nombre_como_correo in SAO_COORDINADORES_AUDITADOS:
        return SAO_COORDINADORES_AUDITADOS[nombre_como_correo]

    nombre = normalizar_texto_operacional(valor_nombre)
    if nombre in SAO_COORDINADORES_NOMBRES:
        return SAO_COORDINADORES_NOMBRES[nombre]
    return str(valor_nombre or "").strip()

# =====================================================
# COLORES CORPORATIVOS ENTEL
# =====================================================

AZUL = "#10069F"          # Azul corporativo
AZUL_CLARO = "#005CFF"    # Azul brillante

NARANJO = "#FF3D00"

VERDE = "#47E190"

CELESTE = "#2ECBF2"

GRIS = "#999999"

NEGRO = "#000000"

ROSADO = "#FD6C98"

BLANCO = "#FFFFFF"

FONDO = "#F7F9FC"

BORDE = "#E7ECF3"

# Uso visual separado para que los KPIs no se confundan con las series del gráfico.
KPI_TOTAL = "#2D8CFF"
KPI_CUMPLIMIENTO = CELESTE
KPI_PRIMERA_VISITA = VERDE
KPI_REVISITA = ROSADO
CHART_PALETTE = ["#168BFF", NARANJO, VERDE, ROSADO, CELESTE, "#8FA7FF"]

PLOTLY_CONFIG_SOLO_LECTURA = {
    "displayModeBar": False,
    "staticPlot": True,
    "scrollZoom": False,
    "doubleClick": False,
    "editable": False,
    "responsive": True,
}
DISPONIBILIDAD_META_PCT = 90
DISPONIBILIDAD_SLA_MIN = 30
RECLAMOS_META_CUMPLIMIENTO_PCT = 90
RECLAMOS_META_RATIO_INCUMPLIMIENTO_PCT = 100 - RECLAMOS_META_CUMPLIMIENTO_PCT
USO_HERRAMIENTA_META_PCT = 85
USO_HERRAMIENTA_META_NOTA = round(1 + (USO_HERRAMIENTA_META_PCT / 100) * 6, 1)
USO_HERRAMIENTA_NOTA_BUENA = round(1 + 0.80 * 6, 1)
USO_HERRAMIENTA_NOTA_CRITICA = round(1 + 0.65 * 6, 1)
DISPONIBILIDAD_TABLA_MAX_FILAS = 300


def nota_uso_desde_pct(valor):
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return pd.NA
    if pd.isna(numero):
        return pd.NA
    if numero <= 7:
        return round(max(1.0, min(7.0, numero)), 1)
    return round(1 + (max(0.0, min(100.0, numero)) / 100.0) * 6.0, 1)


def pct_desde_nota_uso(valor):
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return 0.0
    if pd.isna(numero):
        return 0.0
    if numero > 7:
        return max(0.0, min(100.0, numero))
    return round((max(1.0, min(7.0, numero)) - 1.0) / 6.0 * 100.0, 1)

# =========================================================
# CSS CORPORATIVO V3
# =========================================================

CSS_PATH = ASSETS_DIR / "panel.css"


@st.cache_data(show_spinner=False, max_entries=2)
def cargar_css_panel(ruta_css, version_css):
    css = Path(ruta_css).read_text(encoding="utf-8")
    reemplazos = {
        "__LOGO_ECC_ICONO_DATA__": LOGO_ECC_ICONO_DATA,
        "__AZUL_CLARO__": AZUL_CLARO,
        "__AZUL__": AZUL,
        "__CELESTE__": CELESTE,
        "__NARANJO__": NARANJO,
        "__ROSADO__": ROSADO,
        "__VERDE__": VERDE,
    }
    for token, valor in reemplazos.items():
        css = css.replace(token, valor)
    return css


CSS_VERSION = CSS_PATH.stat().st_mtime_ns if CSS_PATH.exists() else 0
st.markdown(
    f"<style>{cargar_css_panel(str(CSS_PATH), CSS_VERSION)}</style>",
    unsafe_allow_html=True,
)

# =========================================================
# ORDEN MESES
# =========================================================

MESES = [
    "Enero","Febrero","Marzo","Abril","Mayo","Junio",
    "Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"
]

MESES_CORTOS = {
    "Enero": "Ene",
    "Febrero": "Feb",
    "Marzo": "Mar",
    "Abril": "Abr",
    "Mayo": "May",
    "Junio": "Jun",
    "Julio": "Jul",
    "Agosto": "Ago",
    "Septiembre": "Sep",
    "Octubre": "Oct",
    "Noviembre": "Nov",
    "Diciembre": "Dic",
}

ZONA_HORARIA_PANEL = ZoneInfo("America/Santiago")
AHORA_PANEL = datetime.now(ZONA_HORARIA_PANEL).replace(tzinfo=None)
HOY_PANEL = AHORA_PANEL.replace(hour=0, minute=0, second=0, microsecond=0)
ANIO_PANEL = HOY_PANEL.year
MESES_HASTA_HOY = MESES[:HOY_PANEL.month]
MES_ACTUAL = MESES[HOY_PANEL.month - 1]
MES_ACTUAL_CORTO = MESES_CORTOS[MES_ACTUAL]


def normalizar_texto_mes(valor):
    """Normaliza textos de mes para que Ene, Enero, 01, 2026-01, etc. filtren igual."""
    if pd.isna(valor):
        return ""
    texto = unicodedata.normalize("NFKD", str(valor).strip())
    texto = texto.encode("ascii", "ignore").decode("ascii").lower()
    texto = "".join(caracter if caracter.isalnum() else " " for caracter in texto)
    return " ".join(texto.split())


MESES_NORMALIZADOS = {normalizar_texto_mes(mes): mes for mes in MESES}
MESES_NORMALIZADOS.update({normalizar_texto_mes(corto): mes for mes, corto in MESES_CORTOS.items()})
for indice_mes, nombre_mes in enumerate(MESES, start=1):
    MESES_NORMALIZADOS[str(indice_mes)] = nombre_mes
    MESES_NORMALIZADOS[f"{indice_mes:02d}"] = nombre_mes


def normalizar_mes_operacional(valor):
    texto = normalizar_texto_mes(valor)
    if not texto or texto in {"nan", "nat", "none", "null"}:
        return pd.NA

    if texto in MESES_NORMALIZADOS:
        return MESES_NORMALIZADOS[texto]

    for token in texto.split():
        if token in MESES_NORMALIZADOS:
            return MESES_NORMALIZADOS[token]
        try:
            numero = int(token)
        except ValueError:
            continue
        if 1 <= numero <= 12:
            return MESES[numero - 1]

    return pd.NA


def serie_mes_operacional(df_base, fecha_col, mes_col="mes"):
    """Devuelve el mes operacional priorizando la fecha real y usando la columna mes como respaldo."""
    if df_base is None or df_base.empty:
        return pd.Series(dtype="object")

    if fecha_col in df_base.columns:
        fecha = pd.to_datetime(df_base[fecha_col], errors="coerce")
        mes_fecha = fecha.dt.month.map(
            lambda mes: MESES[int(mes) - 1] if pd.notna(mes) and 1 <= int(mes) <= 12 else pd.NA
        )
    else:
        mes_fecha = pd.Series(pd.NA, index=df_base.index, dtype="object")

    if mes_col in df_base.columns:
        mes_respaldo = df_base[mes_col].map(normalizar_mes_operacional)
        return mes_fecha.fillna(mes_respaldo)

    return mes_fecha


def ordenar_meses_operacionales(meses):
    meses_set = set(str(mes) for mes in meses if pd.notna(mes))
    return [mes for mes in MESES if mes in meses_set]


def fechas_calendario(serie):
    """Convierte fechas heterogeneas del panel sin depender del texto del mes."""
    if serie is None:
        return pd.Series(dtype="datetime64[ns]")
    try:
        return pd.to_datetime(serie, format="mixed", dayfirst=True, errors="coerce")
    except (TypeError, ValueError):
        return pd.to_datetime(serie, dayfirst=True, errors="coerce")


def serie_semana_iso(serie):
    fechas = fechas_calendario(serie)
    if fechas.empty:
        return pd.Series(dtype="object")
    iso = fechas.dt.isocalendar()
    tokens = iso["year"].astype("Int64").astype(str) + "-W" + iso["week"].astype("Int64").astype(str).str.zfill(2)
    return tokens.where(fechas.notna(), pd.NA)


def semanas_calendario_disponibles(serie, meses_seleccionados):
    fechas = fechas_calendario(serie)
    if fechas.empty:
        return []
    fechas = fechas.loc[fechas.le(pd.Timestamp(HOY_PANEL))]
    if meses_seleccionados:
        numeros_mes = {MESES.index(mes) + 1 for mes in meses_seleccionados if mes in MESES}
        fechas = fechas.loc[fechas.dt.month.isin(numeros_mes)]
    return sorted(serie_semana_iso(fechas).dropna().astype(str).unique())


def etiqueta_semana_calendario(token):
    try:
        anio_texto, semana_texto = str(token).split("-W", 1)
        inicio = datetime.fromisocalendar(int(anio_texto), int(semana_texto), 1)
        termino = inicio + timedelta(days=6)
        mes_inicio = MESES_CORTOS[MESES[inicio.month - 1]]
        mes_termino = MESES_CORTOS[MESES[termino.month - 1]]
        rango = (
            f"{inicio.day:02d}-{termino.day:02d} {mes_termino}"
            if inicio.month == termino.month
            else f"{inicio.day:02d} {mes_inicio}-{termino.day:02d} {mes_termino}"
        )
        return f"Semana {int(semana_texto):02d} · {rango}"
    except (TypeError, ValueError):
        return f"Semana {token}"


def etiqueta_semana_calendario_clara(token):
    try:
        anio_texto, semana_texto = str(token).split("-W", 1)
        inicio = datetime.fromisocalendar(int(anio_texto), int(semana_texto), 1)
        termino = inicio + timedelta(days=6)
        mes_referencia = inicio + timedelta(days=3)
        mes = MESES_CORTOS[MESES[mes_referencia.month - 1]]
        return f"Semana {int(semana_texto):02d} - {mes} | {inicio.day:02d}-{termino.day:02d}"
    except (TypeError, ValueError):
        return f"Semana {token}"


etiqueta_semana_calendario = etiqueta_semana_calendario_clara


def resumen_meses_disponibilidad_para_filtro(df_base):
    columnas = ["mes", "solicitudes", "cumple", "no_cumple", "cumplimiento_pct", "bajo_meta"]
    if df_base.empty or "cumple_kpi" not in df_base.columns:
        return pd.DataFrame(columns=columnas)

    base = df_base.copy()
    base["_mes_operacional"] = serie_mes_operacional(base, "fecha_solicitud", "mes")
    base = base.dropna(subset=["_mes_operacional"])
    if base.empty:
        return pd.DataFrame(columns=columnas)

    base["_cumple"] = base["cumple_kpi"].fillna(False).astype(bool)
    resumen = (
        base.groupby("_mes_operacional", dropna=False)
        .agg(solicitudes=("_cumple", "size"), cumple=("_cumple", "sum"))
        .reset_index()
        .rename(columns={"_mes_operacional": "mes"})
    )
    resumen["no_cumple"] = resumen["solicitudes"] - resumen["cumple"]
    resumen["cumplimiento_pct"] = (resumen["cumple"] / resumen["solicitudes"].clip(lower=1) * 100).round(1)
    resumen["bajo_meta"] = resumen["cumplimiento_pct"].lt(DISPONIBILIDAD_META_PCT)
    resumen["_orden"] = resumen["mes"].map({mes: i for i, mes in enumerate(MESES)})
    return resumen.sort_values("_orden").drop(columns="_orden")


def resumen_meses_reclamos_para_filtro(df_base):
    columnas = ["mes", "reclamos"]
    if df_base.empty:
        return pd.DataFrame(columns=columnas)

    base = df_base.copy()
    base["_mes_operacional"] = serie_mes_operacional(base, "fecha_reclamo", "mes")
    base = base.dropna(subset=["_mes_operacional"])
    if base.empty:
        return pd.DataFrame(columns=columnas)

    resumen = (
        base.groupby("_mes_operacional", dropna=False)
        .size()
        .reset_index(name="reclamos")
        .rename(columns={"_mes_operacional": "mes"})
    )
    resumen["_orden"] = resumen["mes"].map({mes: i for i, mes in enumerate(MESES)})
    return resumen.sort_values("_orden").drop(columns="_orden")


# =========================================================
# CARGA
# =========================================================

@st.cache_data(show_spinner=False, max_entries=6)
def cargar(ruta_archivo, version_archivo):
    ruta = Path(ruta_archivo)
    ruta_parquet = ruta.with_suffix(".parquet")
    usar_parquet = ruta_parquet.exists() and (
        not ruta.exists() or ruta_parquet.stat().st_mtime_ns >= ruta.stat().st_mtime_ns
    )
    if not ruta.exists() and not usar_parquet:
        return pd.DataFrame()

    df = pd.read_parquet(ruta_parquet) if usar_parquet else pd.read_excel(ruta)
    df = corregir_region_por_ciudad(df, "Ciudad", "Estado")
    if "Estado" in df.columns:
        df["Estado"] = df["Estado"].fillna("").astype(str).str.strip().replace("", "Sin zona")
    if "Recurso" in df.columns:
        df["Recurso"] = df["Recurso"].fillna("").astype(str).str.strip()

    if "Mes" in df.columns:
        df["Mes"] = pd.Categorical(
            df["Mes"],
            categories=MESES,
            ordered=True
        )

    return df


def version_archivo(ruta_archivo):
    ruta = Path(ruta_archivo)
    info = ruta.stat()
    return f"{info.st_size}-{info.st_mtime_ns}"


def version_archivo_opcional(ruta_archivo):
    ruta = Path(ruta_archivo)
    rutas = [ruta]
    if ruta.suffix.lower() in {".xlsx", ".xlsm", ".xls"}:
        rutas.append(ruta.with_suffix(".parquet"))
    existentes = [path for path in rutas if path.exists()]
    if not existentes:
        return "missing"
    return "|".join(f"{path.name}:{version_archivo(path)}" for path in existentes)


def ruta_epa_activa(servicio=None):
    servicio_ref = servicio or SERVICIO_CONFIG
    if isinstance(servicio_ref, str):
        config = SERVICIOS_CONFIG[servicio_ref]
    else:
        config = servicio_ref
    epa_dir = APP_DIR / str(config["epa_dir"])
    epa_db = epa_dir / str(config["epa_db"])
    epa_db_legacy = epa_dir / str(config["epa_db_legacy"])
    if epa_db.exists():
        return epa_db
    if epa_db_legacy.exists():
        return epa_db_legacy
    return epa_db


DISPONIBILIDAD_COLUMNAS = [
    "cliente", "numero_ticket", "ticket_principal", "region", "zona", "ciudad",
    "coordinador", "correo_coordinador", "coordinador_tipo",
    "remitente_cecom", "asunto_solicitud", "fecha_solicitud",
    "fecha_respuesta", "minutos_habiles", "minutos_calendario",
    "cumple_kpi", "estado_kpi", "demora_respuesta", "exceso_sla_habiles",
    "exceso_sla", "tipo_solicitud", "secuencia_solicitud",
    "solicitud_caso_n", "total_solicitudes_caso", "solicitudes_en_ciclo",
    "reiteraciones_previas", "reiteraciones_hasta_respuesta", "reiteraciones_total_operacional",
    "reiteraciones_cecom_operador", "reiteraciones_supervisor_cecom",
    "intervenciones_supervisor_terreno", "interventores_supervisor_terreno",
    "intervenciones_supervisor_servicio_tecnico", "interventores_supervisor_servicio_tecnico",
    "remitentes_reiteracion", "fechas_reiteracion",
    "fecha_primera_reiteracion", "fecha_ultima_reiteracion",
    "grupo_solicitud_id", "mes", "thread_id",
    "mensaje_solicitud_id", "mensaje_respuesta_id", "fuente_pst",
    "actualizado_en", "observacion",
]

RECLAMOS_COLUMNAS = [
    "cliente", "numero_ticket", "ticket_principal", "region", "zona", "ciudad",
    "tipo_registro", "familia_reclamo", "motivo_reclamo", "severidad_reclamo",
    "reforzamiento", "proveedor_reforzado", "motivo_reforzamiento",
    "fecha_reclamo", "remitente", "destinatarios", "asunto",
    "extracto_reclamo", "fecha_programada_reclamo", "hora_programada_reclamo",
    "estado_wfm", "fecha_wfm", "ventana_wfm", "inicio_wfm", "tecnico_wfm",
    "mismo_dia_wfm", "diferencia_hora_wfm_min", "mes", "thread_id",
    "mensaje_id", "fuente_pst", "actualizado_en", "observacion",
]


def serie_texto_limpio(serie):
    return serie.fillna("").astype(str).str.strip()


def serie_bool_panel(serie):
    return (
        serie.fillna(False)
        .astype(str)
        .str.strip()
        .str.lower()
        .isin({"1", "true", "si", "sí", "s\u00ed", "yes", "y", "x", "verdadero"})
    )



def normalizar_texto_operacional(valor):
    """Normaliza texto de correos para detectar reclamos, zonas y exclusiones."""
    if pd.isna(valor):
        return ""
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = texto.encode("ascii", "ignore").decode("ascii").lower()
    return " ".join(texto.split())


RECLAMO_MALA_GESTION_KEYWORDS = [
    "reclamo", "queja", "mala gestion", "mala atencion", "mal gestionado",
    "incumplimiento", "no cumple", "no cumplio", "sin respuesta", "no responde",
    "no han respondido", "no tenemos respuesta", "respuesta pendiente", "demora",
    "demorado", "atraso", "retraso", "no llegada", "no se presenta", "no asistio",
    "sin contacto", "cliente molesto", "molestia", "escalamiento", "urgente apoyo",
    "favor gestionar", "favor regularizar", "mala coordinacion", "problema de gestion",
    "mala higiene", "higiene", "mala presentacion", "mal presentado", "desaseado",
    "sucio", "mal olor", "sin uniforme", "mal trato", "mala actitud", "grosero",
    "cierre falso", "cerrado sin atencion", "cerrado sin atender",
]

RECLAMO_FAMILIAS_PANEL = [
    (
        "No llegada tecnico",
        [
            "tecnico no llego", "tecnico no llega", "tecnico no asiste", "tecnico no asistio",
            "no se presento", "no se presenta", "no llego el tecnico", "no asistio el tecnico",
            "visita fallida", "visita no realizada por tecnico", "no concurrio", "no acudio",
            "nunca llego", "no llego nadie", "sin visita", "tecnico ausente",
        ],
        "Tecnico no llega/no se presenta en visita programada",
    ),
    (
        "Retraso o incumplimiento horario",
        [
            "retraso no informado", "atraso no informado", "llego tarde", "llega tarde",
            "fuera de horario", "sin aviso", "sin avisar", "atraso", "retraso",
            "atrasado", "atrasada", "incumplimiento horario", "incumplio horario",
            "no cumple horario", "no cumple ventana", "fuera de ventana",
        ],
        "Retraso, llegada fuera de horario o incumplimiento de ventana",
    ),
    (
        "Mala higiene o presentacion",
        [
            "mala higiene", "higiene", "falta de higiene", "mala presentacion",
            "presentacion personal", "presentacion del tecnico", "mal presentado",
            "desaseado", "sucio", "mal olor", "olor", "aseo personal",
            "ropa sucia", "uniforme sucio", "sin uniforme", "vestimenta inadecuada",
        ],
        "Tecnico reportado por higiene, presentacion personal o vestimenta",
    ),
    (
        "Mal trato al usuario",
        [
            "mal trato", "mala actitud", "trato inadecuado", "trato grosero",
            "grosero", "prepotente", "falta de respeto", "discusion con usuario",
            "discusion con cliente", "se niega a atender",
        ],
        "Trato inadecuado, falta de respeto o negativa de atencion",
    ),
    (
        "Sin herramientas o insumos",
        [
            "sin herramientas", "no llevo herramientas", "sin herramienta", "sin imagen",
            "no llevo imagen", "sin insumos", "sin insumo", "no llevo repuesto",
            "sin cable", "no cuenta con herramientas", "sin aplicaciones",
        ],
        "Tecnico asiste sin herramientas, imagen, repuestos o insumos",
    ),
    (
        "Sin contacto con usuario",
        [
            "no contacto", "sin contacto", "no llamo", "no llama", "no se contacto",
            "no contacto usuario", "sin coordinacion con usuario", "no coordino con usuario",
        ],
        "Tecnico no contacta o no coordina con usuario",
    ),
    (
        "Mala ejecucion de atencion",
        [
            "mala gestion", "mala atencion", "mal gestionado", "problema de gestion",
            "no termino", "no se termino", "trabajo incompleto", "cierre incorrecto",
            "cerrado incorrectamente", "ot incorrecta", "no resolvio", "dejo sin servicio",
            "incumplimiento", "incumplio", "no cumple", "no cumplio", "no realiza",
            "no realizo", "cierre falso", "cerrado sin atencion", "cerrado sin atender",
            "atencion deficiente", "gestion deficiente", "mala ejecucion",
        ],
        "Atencion incompleta, cierre incorrecto o gestion deficiente",
    ),
]

RECLAMO_EXCLUSION_PATTERNS = [
    r"\bbodega\b", r"\bdevolucion\b", r"\bdevoluciones\b", r"\bretorno\b", r"\bretirar equipo\b",
    r"\bentrega equipo\b", r"\btw\b", r"\bterminal wireless\b", r"\bterminal wifi\b",
    r"\bpago incorrecto\b", r"\bliquidacion\b", r"\bremuneracion\b", r"\bmarcas correspondientes\b",
    r"\bprovision y regularizacion\b", r"\bcanal para solicitudes sap\b", r"\bpedidos sin ticket\b",
    r"\bcuenta del reemplazo\b", r"\brecursos outsourcing\b",
]

REGION_TARAPACA_TERMS = ["tarapaca", "iquique", "alto hospicio", "pozo almonte"]
REGION_ANTOFAGASTA_TERMS = ["antofagasta", "calama", "mejillones", "tocopilla", "taltal", "sierra gorda"]

CLIENTES_ALIASES_PANEL = [
    ("UC CHRISTUS", ["uc christus", "christus", "servicios ambulatorios", "servicio ambulatorio", "red salud uc"]),
    ("BANCO SECURITY", ["banco security", "security"]),
    ("ACHS", ["achs", " ach ", "asoc chilena de seguridad", "asociacion chilena de seguridad", "asociacion chile de seguridad", "asociacion de seguridad"]),
    ("AFC", ["afc", "administradora de fondos de cesantia", "administradora fondos de cesantia", "fondos de cesantia"]),
    ("COPEC", ["copec", "compania de petroleos de chile", "petroleos de chile"]),
    ("CGE", ["cge", "compania general de electricidad", "general de electricidad"]),
    ("IDEMIA", ["idemia", "registro civil"]),
    ("DIBAM", ["dibam", "snpc", "serpac", "servicio nacional de patrimonio", "patrimonio cultural", "biblioteca regional gabriela mistral"]),
    ("BUPA", ["bupa", "bupa chile"]),
    ("ENTEL CHILE", ["entel cio", "entel rhh", "entel rrhh", "entel chile", "entel tiendas", "tiendas entel"]),
]
CLIENTE_NO_IDENTIFICADO = "Sin cliente WFM"
CLIENTE_SIN_DATO_EQUIVALENTES = {"", "sin dato", "cliente no identificado", CLIENTE_NO_IDENTIFICADO.lower()}
TICKET_ID_COLS_PANEL = ["ID Externo", "ID externo", "ID Ticket", "Ticket", "Ticket ID", "Numero Ticket", "Número Ticket"]
CLIENTE_COLS_ATENCION_PANEL = ["Empresa Cliente", "Cliente", "Empresa", "Nombre Cliente"]

SERVICIO_ALIAS_PANEL = {
    "IBM": [
        "ibm", "@ibm.com", "fabian trujillo", "fabian.trujillo", "heraldo", "crisostomo",
        "hcrisostomo", "p.albornoz", "patricio albornoz",
    ],
    "SAO": [
        "sao", "sao computacion", "saocomputacion", "@saocomputacion.cl",
        "d.galarce", "daniel galarce", "pia ossandon", "pia.ossandon",
        "pia.saocomputacion", "angelica fuentes", "angelicafuentes1",
    ],
}


def contiene_exclusion_reclamo(texto):
    limpio = normalizar_texto_operacional(texto)
    return any(re.search(patron, limpio) for patron in RECLAMO_EXCLUSION_PATTERNS)


def contiene_mala_gestion_ibm(texto):
    limpio = normalizar_texto_operacional(texto)
    if not limpio:
        return False
    return any(palabra in limpio for palabra in RECLAMO_MALA_GESTION_KEYWORDS)


def clasificar_reclamo_operacional_panel(texto):
    limpio = normalizar_texto_operacional(texto)
    if not limpio:
        return {"familia": "", "motivo": "", "severidad": ""}
    for familia, terminos, motivo in RECLAMO_FAMILIAS_PANEL:
        if any(normalizar_texto_operacional(termino) in limpio for termino in terminos):
            return {"familia": familia, "motivo": motivo, "severidad": "ALTA"}
    if any(palabra in limpio for palabra in ["reclamo", "queja", "cliente molesto", "escalamiento"]):
        return {
            "familia": "Reclamo explicito cliente",
            "motivo": f"Correo indica reclamo explicito asociado a {SERVICIO_TITULO}",
            "severidad": "ALTA",
        }
    return {"familia": "", "motivo": "", "severidad": ""}


@lru_cache(maxsize=8192)
def region_operacional_desde_texto(texto, region_actual=""):
    region = region_por_ciudad_o_comuna(texto, region_actual)
    return region if region else "Sin zona"


@lru_cache(maxsize=8192)
def cliente_desde_texto_panel(texto):
    limpio = normalizar_texto_operacional(texto)
    if not limpio:
        return "Sin dato"
    texto_padded = f" {limpio} "
    for cliente, aliases in CLIENTES_ALIASES_PANEL:
        for alias in aliases:
            alias_n = normalizar_texto_operacional(alias)
            if alias_n.startswith(" ") or alias_n.endswith(" "):
                if alias_n in texto_padded:
                    return cliente
            elif re.search(rf"(?<![a-z0-9]){re.escape(alias_n)}(?![a-z0-9])", limpio):
                return cliente
            elif alias_n in limpio:
                return cliente
    return "Sin dato"


@lru_cache(maxsize=32768)
def normalizar_ticket_panel(valor):
    texto = str(valor or "").strip().upper()
    if not texto or texto.lower() == "nan":
        return ""
    texto = re.sub(r"\.0$", "", texto)
    ticket_norm = re.sub(r"[^A-Z0-9]", "", texto)
    if re.fullmatch(r"[A-F0-9]{20,}", ticket_norm):
        return ""
    if len(ticket_norm) > 20 and not ticket_norm.startswith(("INC", "RITM", "WO", "REQ", "CNR")):
        return ""
    return ticket_norm


@lru_cache(maxsize=8192)
def cliente_panel_desde_valor(valor):
    texto = str(valor or "").strip()
    if not texto or texto.lower() == "nan":
        return "Sin dato"
    cliente = cliente_desde_texto_panel(texto)
    if cliente != "Sin dato":
        return cliente
    texto = " ".join(texto.upper().split())
    return texto if texto else "Sin dato"


def mapa_clientes_atenciones_panel(df_atenciones):
    mapa = {}
    if df_atenciones is None or df_atenciones.empty:
        return mapa

    ticket_cols = [col for col in TICKET_ID_COLS_PANEL if col in df_atenciones.columns]
    cliente_col = next((col for col in CLIENTE_COLS_ATENCION_PANEL if col in df_atenciones.columns), None)
    if not ticket_cols or cliente_col is None:
        return mapa

    columnas = ticket_cols + [cliente_col]
    if "servicio_tecnico" in df_atenciones.columns:
        columnas.append("servicio_tecnico")

    for _, row in df_atenciones[columnas].fillna("").iterrows():
        cliente = cliente_panel_desde_valor(row.get(cliente_col))
        if cliente == "Sin dato":
            continue
        servicio = str(row.get("servicio_tecnico") or "").strip().upper()
        for ticket_col in ticket_cols:
            ticket_norm = normalizar_ticket_panel(row.get(ticket_col))
            if not ticket_norm:
                continue
            if servicio:
                mapa.setdefault((servicio, ticket_norm), cliente)
            mapa.setdefault(("", ticket_norm), cliente)
    return mapa


def mapa_zonas_atenciones_panel(df_atenciones):
    mapa = {}
    if df_atenciones is None or df_atenciones.empty:
        return mapa

    ticket_cols = [col for col in TICKET_ID_COLS_PANEL if col in df_atenciones.columns]
    if not ticket_cols:
        return mapa

    columnas = ticket_cols[:]
    for col in ["Estado", "Ciudad"]:
        if col in df_atenciones.columns:
            columnas.append(col)
    if "servicio_tecnico" in df_atenciones.columns:
        columnas.append("servicio_tecnico")

    for _, row in df_atenciones[columnas].fillna("").iterrows():
        region_actual = str(row.get("Estado") or "").strip()
        if region_actual.lower() not in {"", "sin zona", "sin dato", "nan"}:
            region = region_actual
        else:
            region = region_operacional_desde_texto(
                str(row.get("Ciudad", "")),
                region_actual,
            )
        ciudad = str(row.get("Ciudad") or "").strip() or "Sin dato"
        if not region or region == "Sin zona":
            continue
        servicio = str(row.get("servicio_tecnico") or "").strip().upper()
        for ticket_col in ticket_cols:
            ticket_norm = normalizar_ticket_panel(row.get(ticket_col))
            if not ticket_norm:
                continue
            if servicio:
                mapa.setdefault((servicio, ticket_norm), (region, ciudad))
            mapa.setdefault(("", ticket_norm), (region, ciudad))
    return mapa


def completar_cliente_desde_atenciones_panel(df_base, df_atenciones, mapa=None):
    if df_base is None or df_base.empty or "cliente" not in df_base.columns:
        return df_base

    mapa = mapa if mapa is not None else mapa_clientes_atenciones_panel(df_atenciones)
    if not mapa:
        return df_base

    base = df_base.copy()
    ticket_cols = [col for col in ["ticket_principal", "numero_ticket"] if col in base.columns]
    if not ticket_cols:
        return base

    clientes_actuales = base["cliente"].fillna("").astype(str).str.strip()
    mask_sin_cliente = clientes_actuales.str.lower().isin(CLIENTE_SIN_DATO_EQUIVALENTES)
    if not mask_sin_cliente.any():
        return base

    for idx, row in base.loc[mask_sin_cliente].iterrows():
        servicio = str(row.get("servicio_tecnico") or "").strip().upper()
        cliente = ""
        for ticket_col in ticket_cols:
            ticket_norm = normalizar_ticket_panel(row.get(ticket_col))
            if not ticket_norm:
                continue
            cliente = mapa.get((servicio, ticket_norm)) or mapa.get(("", ticket_norm)) or ""
            if cliente:
                break
        if cliente:
            base.at[idx, "cliente"] = cliente

    base["cliente"] = base["cliente"].replace({"": CLIENTE_NO_IDENTIFICADO, "Sin dato": CLIENTE_NO_IDENTIFICADO})
    return base


def completar_zona_desde_atenciones_panel(df_base, df_atenciones, mapa=None):
    if df_base is None or df_base.empty:
        return df_base

    mapa = mapa if mapa is not None else mapa_zonas_atenciones_panel(df_atenciones)
    if not mapa:
        return df_base

    base = df_base.copy()
    for col in ["region", "zona", "ciudad"]:
        if col not in base.columns:
            base[col] = ""
    ticket_cols = [col for col in ["ticket_principal", "numero_ticket"] if col in base.columns]
    if not ticket_cols:
        return base

    regiones_actuales = base["region"].fillna("").astype(str).str.strip()
    mask_sin_zona = regiones_actuales.str.lower().isin({"", "sin zona", "sin dato", "nan"})
    if not mask_sin_zona.any():
        return base

    for idx, row in base.loc[mask_sin_zona].iterrows():
        servicio = str(row.get("servicio_tecnico") or "").strip().upper()
        zona = None
        for ticket_col in ticket_cols:
            ticket_norm = normalizar_ticket_panel(row.get(ticket_col))
            if not ticket_norm:
                continue
            zona = mapa.get((servicio, ticket_norm)) or mapa.get(("", ticket_norm))
            if zona:
                break
        if zona:
            region, ciudad = zona
            base.at[idx, "region"] = region
            base.at[idx, "zona"] = region
            if not str(row.get("ciudad") or "").strip() or str(row.get("ciudad") or "").strip() == "Sin dato":
                base.at[idx, "ciudad"] = ciudad

    base["region"] = base["region"].replace("", "Sin zona")
    base["zona"] = base["zona"].where(base["zona"].fillna("").astype(str).str.strip().ne(""), base["region"])
    base["ciudad"] = base["ciudad"].replace("", "Sin dato")
    return base


def deduplicar_reclamos_ticket_familia_panel(df_base):
    if df_base is None or df_base.empty:
        return df_base
    columnas_necesarias = {"ticket_principal", "numero_ticket", "familia_reclamo", "fecha_reclamo"}
    if not columnas_necesarias.intersection(df_base.columns):
        return df_base

    base = df_base.copy()
    ticket_serie = (
        base["ticket_principal"].fillna("").astype(str)
        if "ticket_principal" in base.columns else pd.Series("", index=base.index)
    )
    if "numero_ticket" in base.columns:
        ticket_serie = ticket_serie.where(ticket_serie.str.strip().ne(""), base["numero_ticket"].fillna("").astype(str))
    base["_ticket_reclamo_norm"] = ticket_serie.map(normalizar_ticket_panel)
    if "thread_id" in base.columns:
        base["_ticket_reclamo_norm"] = base["_ticket_reclamo_norm"].where(
            base["_ticket_reclamo_norm"].ne(""),
            base["thread_id"].fillna("").astype(str).map(normalizar_ticket_panel),
        )
    if "mensaje_id" in base.columns:
        base["_ticket_reclamo_norm"] = base["_ticket_reclamo_norm"].where(
            base["_ticket_reclamo_norm"].ne(""),
            base["mensaje_id"].fillna("").astype(str).map(normalizar_ticket_panel),
        )
    base["_familia_reclamo_norm"] = base.get("familia_reclamo", pd.Series("", index=base.index)).fillna("").astype(str).map(normalizar_texto_operacional)
    base["_familia_reclamo_norm"] = base["_familia_reclamo_norm"].replace("", "sin familia")
    base["_fecha_reclamo_orden"] = pd.to_datetime(base.get("fecha_reclamo"), errors="coerce")
    base = base.sort_values(["_ticket_reclamo_norm", "_familia_reclamo_norm", "_fecha_reclamo_orden"], kind="mergesort")
    base = base.drop_duplicates(subset=["_ticket_reclamo_norm", "_familia_reclamo_norm"], keep="first")
    return base.drop(columns=[col for col in ["_ticket_reclamo_norm", "_familia_reclamo_norm", "_fecha_reclamo_orden"] if col in base.columns])


def serie_cliente_atencion_panel(df_base):
    if df_base is None or df_base.empty:
        return pd.Series(dtype="object")
    texto_partes = []
    for col in ["Empresa Cliente", "Cliente", "Descripción Detallada", "Descripcion Detallada", "Motivo"]:
        if col in df_base.columns:
            texto_partes.append(df_base[col].fillna("").astype(str))
    if not texto_partes:
        return pd.Series("Sin dato", index=df_base.index, dtype="object")
    texto_total = texto_partes[0].copy()
    for parte in texto_partes[1:]:
        texto_total = texto_total + " | " + parte
    return texto_total.map(cliente_panel_desde_valor)


def filtrar_atenciones_reclamos_panel(df_base, clientes_sel, clientes_todos, zonas_sel, zonas_todas):
    if df_base is None or df_base.empty:
        return pd.DataFrame() if df_base is None else df_base

    base = df_base.copy()
    clientes_sel_set = set(map(str, clientes_sel or []))
    clientes_todos_set = set(map(str, clientes_todos or []))
    if clientes_sel_set and clientes_todos_set and clientes_sel_set != clientes_todos_set:
        base["_cliente_ratio_reclamo"] = serie_cliente_atencion_panel(base)
        base = base.loc[base["_cliente_ratio_reclamo"].astype(str).isin(clientes_sel_set)].copy()

    zonas_sel_set = set(map(str, zonas_sel or []))
    zonas_todas_set = set(map(str, zonas_todas or []))
    if zonas_sel_set and zonas_todas_set and zonas_sel_set != zonas_todas_set:
        if "Estado" in base.columns:
            zonas_base = base["Estado"].map(lambda valor: region_operacional_desde_texto("", valor))
        elif "Ciudad" in base.columns:
            zonas_base = base["Ciudad"].map(lambda valor: region_operacional_desde_texto(valor, ""))
        else:
            zonas_base = pd.Series("Sin zona", index=base.index)
        base = base.loc[zonas_base.astype(str).isin(zonas_sel_set)].copy()

    return base.drop(columns=[col for col in ["_cliente_ratio_reclamo"] if col in base.columns])


def contiene_alias_servicio_panel(texto, servicio):
    limpio = normalizar_texto_operacional(texto)
    for alias in SERVICIO_ALIAS_PANEL.get(str(servicio or "").upper(), []):
        alias_n = normalizar_texto_operacional(alias)
        if not alias_n:
            continue
        if alias_n in {"ibm", "sao"}:
            if re.search(rf"(?<![a-z0-9]){re.escape(alias_n)}(?![a-z0-9])", limpio):
                return True
        elif alias_n in limpio:
            return True
    return False


def reclamo_corresponde_servicio_panel(texto, servicio):
    servicio = str(servicio or "").upper()
    if servicio not in {"IBM", "SAO"}:
        return True
    otro = "SAO" if servicio == "IBM" else "IBM"
    tiene_servicio = contiene_alias_servicio_panel(texto, servicio)
    tiene_otro = contiene_alias_servicio_panel(texto, otro)
    return not (tiene_otro and not tiene_servicio)


def completar_cliente_panel(df_base, columnas_texto):
    if df_base is None or df_base.empty or "cliente" not in df_base.columns:
        return df_base
    base = df_base.copy()
    columnas = [col for col in columnas_texto if col in base.columns]
    if not columnas:
        base["cliente"] = base["cliente"].replace({"": CLIENTE_NO_IDENTIFICADO, "Sin dato": CLIENTE_NO_IDENTIFICADO})
        return base

    texto_total = base[columnas].fillna("").astype(str).agg(" | ".join, axis=1)
    clientes_actuales = base["cliente"].fillna("").astype(str).str.strip()
    clientes_inferidos = texto_total.map(cliente_desde_texto_panel)
    mask_sin_cliente = clientes_actuales.str.lower().isin(CLIENTE_SIN_DATO_EQUIVALENTES)
    mask_inferido = clientes_inferidos.ne("Sin dato")
    base.loc[mask_sin_cliente & mask_inferido, "cliente"] = clientes_inferidos.loc[mask_sin_cliente & mask_inferido]
    base["cliente"] = base["cliente"].replace({"": CLIENTE_NO_IDENTIFICADO, "Sin dato": CLIENTE_NO_IDENTIFICADO})
    return base


def normalizar_coordinadores_sao_panel(df_base):
    if df_base is None or df_base.empty or "coordinador" not in df_base.columns:
        return df_base
    base = df_base.copy()
    if "correo_coordinador" not in base.columns:
        base["correo_coordinador"] = ""
    servicio_serie = base["servicio_tecnico"].astype(str).str.upper() if "servicio_tecnico" in base.columns else pd.Series("SAO", index=base.index)
    mask_sao = servicio_serie.eq("SAO")
    if not mask_sao.any():
        return base
    base.loc[mask_sao, "coordinador"] = [
        nombre_coordinador_sao(nombre, correo) or nombre
        for nombre, correo in zip(
            base.loc[mask_sao, "coordinador"].fillna(""),
            base.loc[mask_sao, "correo_coordinador"].fillna(""),
        )
    ]
    return base


def depurar_reclamos_ibm(df_rec, servicio=None):
    """
    Mantiene reclamos IBM por mala gestion aunque el extractor no haya llenado familia/motivo.
    Excluye correos de bodega, devolucion y TW porque no corresponden al KPI operacional.
    """
    if df_rec is None or df_rec.empty:
        return df_rec

    servicio_label = servicio or SERVICIO_TITULO
    base = df_rec.copy()
    columnas_texto = [
        col for col in [
            "familia_reclamo", "motivo_reclamo", "severidad_reclamo", "remitente", "destinatarios",
            "asunto", "extracto_reclamo", "observacion", "cliente", "region", "zona", "ciudad",
        ]
        if col in base.columns
    ]
    if not columnas_texto:
        return base

    texto_total = base[columnas_texto].fillna("").astype(str).agg(" | ".join, axis=1)
    servicio_codigo = str(servicio or "").upper()
    if servicio_codigo in {"IBM", "SAO"}:
        columnas_servicio = [
            col for col in [
                "remitente", "destinatarios", "asunto", "extracto_reclamo",
                "cliente", "region", "zona", "ciudad",
            ]
            if col in base.columns
        ]
        texto_servicio = base[columnas_servicio].fillna("").astype(str).agg(" | ".join, axis=1) if columnas_servicio else texto_total
        mask_servicio = texto_servicio.map(lambda texto: reclamo_corresponde_servicio_panel(texto, servicio_codigo))
        base = base.loc[mask_servicio].copy()
        texto_total = texto_total.loc[base.index]

    mask_excluir = texto_total.map(contiene_exclusion_reclamo)
    base = base.loc[~mask_excluir].copy()
    texto_total = texto_total.loc[base.index]
    mask_mala_gestion = texto_total.map(contiene_mala_gestion_ibm)
    clasificacion_operacional = texto_total.map(clasificar_reclamo_operacional_panel)
    mask_reclamo_operacional = clasificacion_operacional.map(lambda item: bool(item.get("familia")))

    if "familia_reclamo" in base.columns:
        familia_actual = base["familia_reclamo"].fillna("").astype(str).str.strip()
        familia_generica = familia_actual.eq("") | familia_actual.str.lower().str.contains("mala gestion|sin clasificar", na=False)
        for idx, item in clasificacion_operacional.loc[mask_reclamo_operacional & familia_generica].items():
            base.at[idx, "familia_reclamo"] = item["familia"]
        base.loc[mask_mala_gestion & familia_actual.eq(""), "familia_reclamo"] = f"Mala gestion {servicio_label}"

    if "motivo_reclamo" in base.columns:
        motivo_vacio = base["motivo_reclamo"].fillna("").astype(str).str.strip().eq("")
        for idx, item in clasificacion_operacional.loc[mask_reclamo_operacional & motivo_vacio].items():
            base.at[idx, "motivo_reclamo"] = item["motivo"]
        base.loc[mask_mala_gestion & motivo_vacio, "motivo_reclamo"] = base.loc[mask_mala_gestion & motivo_vacio, "motivo_reclamo"].replace("", "Reclamo por mala gestion operacional")

    if "severidad_reclamo" in base.columns:
        severidad_vacia = base["severidad_reclamo"].fillna("").astype(str).str.strip().eq("")
        base.loc[(mask_mala_gestion | mask_reclamo_operacional) & severidad_vacia, "severidad_reclamo"] = "ALTA"

    if "region" in base.columns:
        base["region"] = [
            region_operacional_desde_texto(texto, region_actual)
            for texto, region_actual in zip(texto_total, base["region"].fillna(""))
        ]
    if "zona" in base.columns and "region" in base.columns:
        base["zona"] = base["zona"].where(base["zona"].fillna("").astype(str).str.strip().ne(""), base["region"])

    if "observacion" in base.columns:
        obs = base["observacion"].fillna("").astype(str)
        marca = f"Detectado como reclamo {servicio_label} por mala gestion operacional"
        base.loc[mask_mala_gestion & ~obs.str.contains("mala gestion", case=False, na=False), "observacion"] = (
            obs.loc[mask_mala_gestion & ~obs.str.contains("mala gestion", case=False, na=False)]
            .map(lambda x: f"{x} | {marca}".strip(" |"))
        )

    return base


def serie_numero_segura(df_base, columna):
    if columna in df_base.columns:
        return pd.to_numeric(df_base[columna], errors="coerce").fillna(0)
    return pd.Series(0, index=df_base.index, dtype="float64")


def calcular_reiteraciones_total_operacional(df_base):
    """
    Regla simplificada: toda re-insistencia por disponibilidad cuenta como reiteracion,
    independiente de si la hace CECOM, PRODRIGUEZA, NPEREZC o RRODRIGUEZB.

    Para no duplicar cuando el CSV ya trae un total, se toma el mayor valor entre:
    - reiteraciones_hasta_respuesta
    - suma de componentes separados: agente CECOM + supervisor CECOM + intervenciones
    """
    if df_base is None or df_base.empty:
        return pd.Series(dtype="float64")

    total_base = pd.concat([
        serie_numero_segura(df_base, "reiteraciones_hasta_respuesta"),
        serie_numero_segura(df_base, "reiteraciones_total_operacional"),
    ], axis=1).max(axis=1).fillna(0)
    componentes = (
        serie_numero_segura(df_base, "reiteraciones_cecom_operador")
        + serie_numero_segura(df_base, "reiteraciones_supervisor_cecom")
        + serie_numero_segura(df_base, "intervenciones_supervisor_servicio_tecnico")
        + serie_numero_segura(df_base, "intervenciones_supervisor_terreno")
    )
    return pd.concat([total_base, componentes], axis=1).max(axis=1).fillna(0)


def aplicar_reiteraciones_total_operacional(df_base):
    if df_base is None or df_base.empty:
        return df_base
    df_base = df_base.copy()
    df_base["reiteraciones_total_operacional"] = calcular_reiteraciones_total_operacional(df_base)
    return df_base


@st.cache_data(show_spinner=False, max_entries=4)
def cargar_disponibilidad(ruta_cache, version_cache):
    ruta = Path(ruta_cache)
    if not ruta.exists():
        return pd.DataFrame(columns=DISPONIBILIDAD_COLUMNAS)

    try:
        if ruta.suffix.lower() in {".xlsx", ".xlsm", ".xls"}:
            df_disp = pd.read_excel(ruta)
        else:
            df_disp = pd.read_csv(ruta, encoding="utf-8-sig")
    except Exception:
        return pd.DataFrame(columns=DISPONIBILIDAD_COLUMNAS)

    for col in DISPONIBILIDAD_COLUMNAS:
        if col not in df_disp.columns:
            df_disp[col] = pd.NA

    for col in ["fecha_solicitud", "fecha_respuesta", "fecha_primera_reiteracion", "fecha_ultima_reiteracion", "actualizado_en"]:
        df_disp[col] = pd.to_datetime(df_disp[col], errors="coerce")

    for col in [
        "minutos_habiles", "minutos_calendario", "exceso_sla_habiles",
        "secuencia_solicitud", "solicitud_caso_n", "total_solicitudes_caso",
        "solicitudes_en_ciclo", "reiteraciones_previas", "reiteraciones_hasta_respuesta",
        "reiteraciones_total_operacional", "reiteraciones_cecom_operador", "reiteraciones_supervisor_cecom",
        "intervenciones_supervisor_terreno", "intervenciones_supervisor_servicio_tecnico",
    ]:
        df_disp[col] = pd.to_numeric(df_disp[col], errors="coerce")

    texto_cumple = serie_texto_limpio(df_disp["cumple_kpi"]).str.lower()
    df_disp["cumple_kpi"] = texto_cumple.isin({"true", "1", "si", "sí", "cumple", "ok"})

    for col in [
        "cliente", "numero_ticket", "ticket_principal", "region", "zona", "ciudad",
        "coordinador", "correo_coordinador", "coordinador_tipo", "remitente_cecom",
        "asunto_solicitud", "estado_kpi", "demora_respuesta", "exceso_sla",
        "tipo_solicitud", "interventores_supervisor_terreno", "interventores_supervisor_servicio_tecnico", "remitentes_reiteracion",
        "fechas_reiteracion", "grupo_solicitud_id", "thread_id", "fuente_pst", "observacion",
    ]:
        df_disp[col] = serie_texto_limpio(df_disp[col])

    region_respaldo = df_disp["region"].where(df_disp["region"].ne(""), df_disp["zona"])
    df_disp["region"] = [
        region_por_ciudad_o_comuna(ciudad, region)
        for ciudad, region in zip(df_disp["ciudad"], region_respaldo)
    ]
    df_disp["zona"] = df_disp["region"]

    df_disp = completar_cliente_panel(
        df_disp,
        [
            "cliente", "asunto_solicitud", "observacion", "remitente_cecom",
            "numero_ticket", "ticket_principal", "region", "zona", "ciudad",
        ],
    )
    df_disp["region"] = df_disp["region"].where(df_disp["region"].ne(""), df_disp["zona"])
    df_disp["zona"] = df_disp["zona"].where(df_disp["zona"].ne(""), df_disp["region"])
    df_disp["ticket_principal"] = df_disp["ticket_principal"].where(df_disp["ticket_principal"].ne(""), df_disp["numero_ticket"])
    df_disp["coordinador"] = df_disp["coordinador"].replace("", "Sin respuesta")
    df_disp["tipo_solicitud"] = df_disp["tipo_solicitud"].replace("", "Solicitud inicial")
    df_disp["exceso_sla"] = df_disp["exceso_sla"].replace("", "Sin exceso")
    df_disp["reiteraciones_previas"] = df_disp["reiteraciones_previas"].fillna(0)
    df_disp["reiteraciones_hasta_respuesta"] = df_disp["reiteraciones_hasta_respuesta"].fillna(0)
    for col in ["solicitud_caso_n", "total_solicitudes_caso", "solicitudes_en_ciclo", "reiteraciones_total_operacional", "reiteraciones_cecom_operador", "reiteraciones_supervisor_cecom", "intervenciones_supervisor_terreno", "intervenciones_supervisor_servicio_tecnico"]:
        df_disp[col] = df_disp[col].fillna(0)
    df_disp["intervenciones_supervisor_servicio_tecnico"] = df_disp["intervenciones_supervisor_servicio_tecnico"].where(
        df_disp["intervenciones_supervisor_servicio_tecnico"].ne(0),
        df_disp["intervenciones_supervisor_terreno"],
    )
    df_disp["interventores_supervisor_servicio_tecnico"] = df_disp["interventores_supervisor_servicio_tecnico"].where(
        df_disp["interventores_supervisor_servicio_tecnico"].ne(""),
        df_disp["interventores_supervisor_terreno"],
    )
    df_disp = aplicar_reiteraciones_total_operacional(df_disp)
    df_disp["region"] = df_disp["region"].replace("", "Sin zona")
    df_disp["zona"] = df_disp["zona"].replace("", "Sin zona")
    df_disp["ciudad"] = df_disp["ciudad"].replace("", "Sin dato")
    df_disp["cliente"] = df_disp["cliente"].replace({"": CLIENTE_NO_IDENTIFICADO, "Sin dato": CLIENTE_NO_IDENTIFICADO})

    desde_2026 = pd.Timestamp("2026-01-01")
    if "fecha_solicitud" in df_disp.columns:
        df_disp = df_disp.loc[df_disp["fecha_solicitud"].isna() | df_disp["fecha_solicitud"].ge(desde_2026)].copy()

    df_disp["mes"] = serie_mes_operacional(df_disp, "fecha_solicitud", "mes")
    df_disp["mes"] = pd.Categorical(df_disp["mes"], categories=MESES, ordered=True)

    return df_disp[DISPONIBILIDAD_COLUMNAS].copy()


@st.cache_data(show_spinner=False, max_entries=4)
def cargar_reclamos(ruta_cache, version_cache, servicio=None):
    ruta = Path(ruta_cache)
    if not ruta.exists():
        return pd.DataFrame(columns=RECLAMOS_COLUMNAS)

    try:
        df_rec = pd.read_csv(ruta, encoding="utf-8-sig")
    except Exception:
        return pd.DataFrame(columns=RECLAMOS_COLUMNAS)

    for col in RECLAMOS_COLUMNAS:
        if col not in df_rec.columns:
            df_rec[col] = pd.NA

    for col in ["fecha_reclamo", "fecha_programada_reclamo", "fecha_wfm", "actualizado_en"]:
        df_rec[col] = pd.to_datetime(df_rec[col], errors="coerce")

    df_rec["diferencia_hora_wfm_min"] = pd.to_numeric(df_rec["diferencia_hora_wfm_min"], errors="coerce")

    for col in [
        "cliente", "numero_ticket", "ticket_principal", "region", "zona", "ciudad",
        "tipo_registro", "familia_reclamo", "motivo_reclamo", "severidad_reclamo",
        "proveedor_reforzado", "motivo_reforzamiento", "remitente",
        "destinatarios", "asunto", "extracto_reclamo", "hora_programada_reclamo",
        "estado_wfm", "ventana_wfm", "inicio_wfm", "tecnico_wfm", "mismo_dia_wfm",
        "mes", "thread_id", "mensaje_id", "fuente_pst", "observacion",
    ]:
        df_rec[col] = serie_texto_limpio(df_rec[col])
    df_rec["reforzamiento"] = serie_bool_panel(df_rec["reforzamiento"])
    df_rec["tipo_registro"] = df_rec["tipo_registro"].where(
        df_rec["tipo_registro"].ne(""),
        df_rec["reforzamiento"].map({True: "Reforzamiento", False: "Reclamo"}),
    )

    df_rec = completar_cliente_panel(
        df_rec,
        [
            "cliente", "asunto", "extracto_reclamo", "observacion",
            "remitente", "destinatarios", "numero_ticket", "ticket_principal",
            "region", "zona", "ciudad",
        ],
    )
    df_rec["region"] = df_rec["region"].replace("", "Sin zona")
    df_rec["zona"] = df_rec["zona"].where(df_rec["zona"].ne(""), df_rec["region"])
    df_rec["ticket_principal"] = df_rec["ticket_principal"].where(df_rec["ticket_principal"].ne(""), df_rec["numero_ticket"])

    df_rec = depurar_reclamos_ibm(df_rec, servicio)
    df_rec["cliente"] = df_rec["cliente"].replace({"": CLIENTE_NO_IDENTIFICADO, "Sin dato": CLIENTE_NO_IDENTIFICADO})

    desde_2026 = pd.Timestamp("2026-01-01")
    df_rec = df_rec.loc[df_rec["fecha_reclamo"].isna() | df_rec["fecha_reclamo"].ge(desde_2026)].copy()
    df_rec["mes"] = serie_mes_operacional(df_rec, "fecha_reclamo", "mes")
    df_rec["mes"] = pd.Categorical(df_rec["mes"], categories=MESES, ordered=True)

    return df_rec[RECLAMOS_COLUMNAS].copy()


@st.cache_data(show_spinner=False, max_entries=6)
def cargar_epa(ruta_db, version_db):
    ruta = Path(ruta_db)
    columnas = [
        "proveedor", "atencion_id", "public_token", "atencion_creada",
        "cliente", "region", "st", "ticket", "tecnico", "fecha_atencion", "canal",
        "contacto", "servicio", "observacion_interna", "respondida",
        "respuesta_id", "respuesta_creada", "q1", "q2", "q3", "q4", "q5",
        "promedio", "comentario",
    ]

    if not ruta.exists():
        return pd.DataFrame(columns=columnas)

    try:
        with sqlite3.connect(ruta) as con:
            tablas = pd.read_sql_query(
                "SELECT name FROM sqlite_master WHERE type='table'",
                con
            )["name"].tolist()

            if "atenciones" not in tablas:
                return pd.DataFrame(columns=columnas)

            columnas_atenciones = set(
                pd.read_sql_query("PRAGMA table_info(atenciones)", con)["name"].tolist()
            )
            region_expr = "a.region" if "region" in columnas_atenciones else "'' AS region"

            base_epa = pd.read_sql_query(
                f"""
                SELECT
                    a.proveedor,
                    a.id AS atencion_id,
                    a.public_token,
                    a.created_at AS atencion_creada,
                    a.cliente,
                    {region_expr},
                    a.st,
                    a.ticket,
                    a.tecnico,
                    a.fecha_atencion,
                    a.canal,
                    a.contacto,
                    a.servicio,
                    a.observacion_interna,
                    CASE WHEN r.id IS NULL THEN 0 ELSE 1 END AS respondida,
                    r.id AS respuesta_id,
                    r.created_at AS respuesta_creada,
                    r.q1,
                    r.q2,
                    r.q3,
                    r.q4,
                    r.q5,
                    ROUND((r.q1 + r.q2 + r.q3 + r.q4 + r.q5) / 5.0, 2) AS promedio,
                    r.comentario
                FROM atenciones a
                LEFT JOIN respuestas r ON r.atencion_id = a.id
                ORDER BY a.created_at DESC
                """,
                con,
            )
            if "region" in base_epa.columns:
                base_epa["region"] = base_epa["region"].map(normalizar_region_chile).replace("", "Sin zona")
            if "tecnico" in base_epa.columns:
                base_epa["tecnico"] = base_epa["tecnico"].fillna("").astype(str).str.strip()
            return base_epa
    except Exception:
        return pd.DataFrame(columns=columnas)


def concatenar_frames_servicio(frames):
    frames_validos = [frame for frame in frames if frame is not None and not frame.empty]
    if not frames_validos:
        return pd.DataFrame()
    return pd.concat(frames_validos, ignore_index=True, sort=False)


def cargar_atenciones_servicios(servicios):
    frames = []
    for servicio in servicios:
        config = SERVICIOS_CONFIG[servicio]
        ruta = APP_DIR / str(config["archivo"])
        base = cargar(str(ruta), version_archivo_opcional(ruta))
        if not base.empty:
            base["servicio_tecnico"] = servicio
            frames.append(base)
    return concatenar_frames_servicio(frames)


def cargar_epa_servicios(servicios):
    frames = []
    for servicio in servicios:
        ruta = ruta_epa_activa(servicio)
        base = cargar_epa(str(ruta), version_archivo_opcional(ruta))
        if not base.empty:
            base["servicio_tecnico"] = servicio
            frames.append(base)
    return concatenar_frames_servicio(frames)


def cargar_disponibilidad_servicios(servicios):
    frames = []
    for servicio in servicios:
        config = SERVICIOS_CONFIG[servicio]
        if not config.get("participa_disponibilidad", True) or not config.get("disponibilidad"):
            continue
        ruta = APP_DIR / str(config["disponibilidad"])
        base = cargar_disponibilidad(str(ruta), version_archivo_opcional(ruta))
        if not base.empty:
            base["servicio_tecnico"] = servicio
            frames.append(base)
    return concatenar_frames_servicio(frames)


def cargar_reclamos_servicios(servicios):
    frames = []
    for servicio in servicios:
        config = SERVICIOS_CONFIG[servicio]
        if not config.get("participa_reclamos", True) or not config.get("reclamos"):
            continue
        ruta = APP_DIR / str(config["reclamos"])
        base = cargar_reclamos(str(ruta), version_archivo_opcional(ruta), servicio)
        if not base.empty:
            base["servicio_tecnico"] = servicio
            frames.append(base)
    return concatenar_frames_servicio(frames)


def existe_cache_disponibilidad(servicios):
    return any(
        SERVICIOS_CONFIG[servicio].get("participa_disponibilidad", True)
        and bool(SERVICIOS_CONFIG[servicio].get("disponibilidad"))
        and (APP_DIR / str(SERVICIOS_CONFIG[servicio]["disponibilidad"])).exists()
        for servicio in servicios
    )


@st.cache_data(show_spinner=False, ttl=600)
def crear_excel_filtrado(df_export, filtros_export, sheet_name="Datos filtrados", titulo="Vista filtrada dashboard operaciones"):
    salida = BytesIO()
    df_excel = df_export.copy()

    for col in df_excel.select_dtypes(include=["category"]).columns:
        df_excel[col] = df_excel[col].astype(str)

    control = pd.DataFrame(
        [
            ["Propiedad", APP_OWNER],
            ["Firma", APP_SIGNATURE],
            ["Generado", datetime.now().strftime("%d-%m-%Y %H:%M:%S")],
            ["Regiones", ", ".join(filtros_export.get("regiones", []))],
            ["Tecnicos", ", ".join(filtros_export.get("tecnicos", []))],
            ["Meses", ", ".join(filtros_export.get("meses", []))],
            ["Clientes", ", ".join(filtros_export.get("clientes", []))],
            ["Zonas", ", ".join(filtros_export.get("zonas", []))],
            ["Registros exportados", len(df_excel)],
        ],
        columns=["Campo", "Valor"]
    )

    with pd.ExcelWriter(salida, engine="xlsxwriter") as writer:
        df_excel.to_excel(writer, sheet_name=sheet_name, index=False)
        control.to_excel(writer, sheet_name="Control interno", index=False)

        libro = writer.book
        libro.set_properties({
            "author": APP_OWNER,
            "title": titulo,
            "subject": APP_SIGNATURE,
        })

        hoja = writer.sheets[sheet_name]
        hoja.freeze_panes(1, 0)
        if len(df_excel.columns):
            hoja.autofilter(0, 0, len(df_excel), len(df_excel.columns) - 1)

        for indice, columna in enumerate(df_excel.columns):
            encabezado = str(columna)
            ancho = min(max(len(encabezado) + 4, 12), 42)
            hoja.set_column(indice, indice, ancho)

        hoja_control = writer.sheets["Control interno"]
        hoja_control.hide()

    salida.seek(0)
    return salida.getvalue()


def preparar_export_epa(df_epa_base):
    vista_epa = df_epa_base.copy()
    if "respondida" in vista_epa.columns:
        vista_epa["Estado EPA"] = vista_epa["respondida"].fillna(0).astype(int).map({1: "Respondida", 0: "Pendiente"})

    columnas_epa = [
        "Estado EPA", "servicio_tecnico", "cliente", "region", "st", "ticket", "tecnico", "fecha_atencion",
        "promedio", "q1", "q2", "q3", "q4", "q5", "comentario", "respuesta_creada",
    ]
    columnas_epa = [col for col in columnas_epa if col in vista_epa.columns]
    vista_epa = vista_epa[columnas_epa] if columnas_epa else vista_epa
    return vista_epa.rename(columns={"servicio_tecnico": "Servicio tecnico"})


def preparar_export_disponibilidad(df_disp_base):
    vista = df_disp_base.copy()
    if "cumple_kpi" in vista.columns:
        vista["Cumple KPI"] = vista["cumple_kpi"].fillna(False).astype(bool).map({True: "Si", False: "No"})

    columnas = [
        "servicio_tecnico", "cliente", "numero_ticket", "ticket_principal", "region", "ciudad", "coordinador",
        "correo_coordinador", "coordinador_tipo", "remitente_cecom",
        "asunto_solicitud", "fecha_solicitud", "fecha_respuesta",
        "minutos_habiles", "minutos_calendario", "demora_respuesta",
        "exceso_sla_habiles", "exceso_sla", "tipo_solicitud",
        "solicitud_caso_n", "total_solicitudes_caso", "solicitudes_en_ciclo",
        "reiteraciones_total_operacional", "reiteraciones_hasta_respuesta", "reiteraciones_cecom_operador",
        "reiteraciones_supervisor_cecom", "intervenciones_supervisor_servicio_tecnico",
        "interventores_supervisor_servicio_tecnico", "remitentes_reiteracion",
        "fechas_reiteracion", "fecha_primera_reiteracion", "fecha_ultima_reiteracion",
        "Cumple KPI", "estado_kpi",
        "observacion", "thread_id", "grupo_solicitud_id",
    ]
    columnas = [col for col in columnas if col in vista.columns]
    vista = vista[columnas] if columnas else vista
    return vista.rename(columns={
        "servicio_tecnico": "Servicio tecnico",
        "cliente": "Cliente",
        "numero_ticket": "Numero ticket",
        "ticket_principal": "Ticket principal",
        "region": "Region",
        "ciudad": "Ciudad",
        "coordinador": f"Respondedor {SERVICIO_TITULO}",
        "correo_coordinador": "Correo respondedor",
        "coordinador_tipo": "Rol respondedor",
        "remitente_cecom": "Solicitante CECOM",
        "asunto_solicitud": "Asunto correo",
        "fecha_solicitud": "Fecha hora solicitud CECOM",
        "fecha_respuesta": f"Fecha hora respuesta {SERVICIO_TITULO}",
        "minutos_habiles": "Minutos habiles respuesta",
        "minutos_calendario": "Minutos calendario",
        "demora_respuesta": "Demora respuesta",
        "exceso_sla_habiles": "Exceso SLA habiles",
        "exceso_sla": "Exceso SLA",
        "tipo_solicitud": "Tipo solicitud",
        "solicitud_caso_n": "Solicitud caso N",
        "total_solicitudes_caso": "Total solicitudes caso",
        "solicitudes_en_ciclo": "Correos solicitud en ciclo",
        "reiteraciones_total_operacional": "Reiteraciones totales",
        "reiteraciones_hasta_respuesta": "Reiteraciones base",
        "reiteraciones_cecom_operador": "Reiteraciones agente CECOM",
        "reiteraciones_supervisor_cecom": "Reiteraciones supervisor CECOM",
        "intervenciones_supervisor_servicio_tecnico": "Intervenciones Supervisor Servicio Tecnico",
        "interventores_supervisor_servicio_tecnico": "Supervisor Servicio Tecnico involucrado",
        "remitentes_reiteracion": "Remitentes reiteracion",
        "fechas_reiteracion": "Fechas reiteracion",
        "fecha_primera_reiteracion": "Primera reiteracion",
        "fecha_ultima_reiteracion": "Ultima reiteracion",
        "estado_kpi": "Estado KPI",
        "observacion": "Observacion",
        "thread_id": "Thread correo",
        "grupo_solicitud_id": "Grupo solicitud",
    })


def preparar_export_reclamos(df_rec_base):
    vista = df_rec_base.copy()
    columnas = [
        "servicio_tecnico", "fecha_reclamo", "cliente", "numero_ticket", "ticket_principal", "region", "ciudad",
        "tipo_registro", "familia_reclamo", "motivo_reclamo", "severidad_reclamo",
        "reforzamiento", "proveedor_reforzado", "motivo_reforzamiento", "remitente",
        "destinatarios", "asunto", "extracto_reclamo", "fecha_programada_reclamo",
        "hora_programada_reclamo", "estado_wfm", "fecha_wfm", "ventana_wfm",
        "inicio_wfm", "tecnico_wfm", "mismo_dia_wfm", "diferencia_hora_wfm_min",
        "observacion", "thread_id",
    ]
    columnas = [col for col in columnas if col in vista.columns]
    vista = vista[columnas] if columnas else vista
    return vista.rename(columns={
        "servicio_tecnico": "Servicio tecnico",
        "fecha_reclamo": "Fecha hora reclamo",
        "cliente": "Cliente",
        "numero_ticket": "Numero ticket",
        "ticket_principal": "Ticket principal",
        "region": "Region",
        "ciudad": "Ciudad",
        "tipo_registro": "Tipo señal",
        "familia_reclamo": "Familia reclamo",
        "motivo_reclamo": "Motivo reclamo",
        "severidad_reclamo": "Severidad",
        "reforzamiento": "Reforzamiento",
        "proveedor_reforzado": "ST reforzado",
        "motivo_reforzamiento": "Motivo reforzamiento",
        "remitente": "Remitente",
        "destinatarios": "Destinatarios",
        "asunto": "Asunto",
        "extracto_reclamo": "Extracto reclamo",
        "fecha_programada_reclamo": "Fecha programada reclamo",
        "hora_programada_reclamo": "Hora programada reclamo",
        "estado_wfm": "Estado WFM",
        "fecha_wfm": "Fecha WFM",
        "ventana_wfm": "Ventana WFM",
        "inicio_wfm": "Inicio WFM",
        "tecnico_wfm": "Tecnico WFM",
        "mismo_dia_wfm": "Mismo dia WFM",
        "diferencia_hora_wfm_min": "Diferencia hora WFM min",
        "observacion": "Observacion",
        "thread_id": "Thread correo",
    })


@st.cache_data(show_spinner=False, max_entries=2)
def cargar_uso_herramienta(ruta_archivo, version_archivo):
    ruta = Path(ruta_archivo)
    columnas = [
        "folio_ot", "ticket", "cliente", "ciudad", "region_atendida", "fecha_atencion",
        "tecnico", "st", "puntaje_total", "estado_calidad", "score_detalle",
        "score_equipos", "score_activo_fijo", "score_redaccion", "requiere_retiro",
        "requiere_instalacion", "cliente_cge", "activo_fijo_detectado", "hallazgos",
    ]
    if not ruta.exists():
        return pd.DataFrame(columns=columnas)
    try:
        df_uso = pd.read_csv(ruta, encoding="utf-8-sig")
    except UnicodeDecodeError:
        df_uso = pd.read_csv(ruta, encoding="latin1")
    for col in columnas:
        if col not in df_uso.columns:
            df_uso[col] = ""
    for col in ["puntaje_total", "score_detalle", "score_equipos", "score_activo_fijo", "score_redaccion"]:
        df_uso[col] = pd.to_numeric(df_uso[col], errors="coerce")
    if "puntaje_pct" in df_uso.columns:
        df_uso["puntaje_pct"] = pd.to_numeric(df_uso["puntaje_pct"], errors="coerce")
        df_uso["puntaje_pct"] = df_uso["puntaje_pct"].where(df_uso["puntaje_pct"].notna(), df_uso["puntaje_total"].map(pct_desde_nota_uso))
    else:
        df_uso["puntaje_pct"] = df_uso["puntaje_total"].map(pct_desde_nota_uso)
    df_uso["puntaje_total"] = df_uso["puntaje_total"].map(nota_uso_desde_pct)
    df_uso["st"] = df_uso["st"].fillna("Sin clasificar").astype(str).str.strip().str.upper().replace({"": "Sin clasificar"})
    df_uso["servicio_tecnico"] = df_uso["st"]
    if "region_atendida" in df_uso.columns:
        ciudades = df_uso["ciudad"] if "ciudad" in df_uso.columns else pd.Series("", index=df_uso.index)
        df_uso["region_atendida"] = [
            region_por_ciudad_o_comuna(ciudad, region)
            for ciudad, region in zip(ciudades.fillna(""), df_uso["region_atendida"].fillna(""))
        ]
        df_uso["region_atendida"] = df_uso["region_atendida"].fillna("").astype(str).str.strip().replace("", "Sin zona")
    if "tecnico" in df_uso.columns:
        df_uso["tecnico"] = df_uso["tecnico"].fillna("").astype(str).str.strip()
    return df_uso


def cargar_uso_herramienta_servicios(servicios):
    ruta = APP_DIR / "USO_HERRAMIENTA_OT_2026.csv"
    base = cargar_uso_herramienta(str(ruta), version_archivo_opcional(ruta))
    if base.empty or "st" not in base.columns:
        return base
    servicios_validos = {
        servicio for servicio in servicios
        if SERVICIOS_CONFIG[servicio].get("participa_uso_herramienta", True)
    }
    return base.loc[base["st"].isin(servicios_validos)].copy()


def versiones_bases_panel(servicios):
    rutas = [APP_DIR / "USO_HERRAMIENTA_OT_2026.csv"]
    for servicio in servicios:
        config = SERVICIOS_CONFIG[servicio]
        rutas.append(APP_DIR / str(config["archivo"]))
        if config.get("disponibilidad"):
            rutas.append(APP_DIR / str(config["disponibilidad"]))
        if config.get("reclamos"):
            rutas.append(APP_DIR / str(config["reclamos"]))
        rutas.append(ruta_epa_activa(servicio))
    return tuple((str(ruta), version_archivo_opcional(ruta)) for ruta in rutas)


@st.cache_resource(show_spinner=False, max_entries=4)
def cargar_bases_preparadas(servicios, versiones):
    del versiones  # solo invalida el cache cuando cambia una fuente
    servicios = list(servicios)
    atenciones = cargar_atenciones_servicios(servicios)
    epa = cargar_epa_servicios(servicios)
    disponibilidad = cargar_disponibilidad_servicios(servicios)
    disponibilidad = normalizar_coordinadores_sao_panel(disponibilidad)
    reclamos = cargar_reclamos_servicios(servicios)
    mapa_clientes = mapa_clientes_atenciones_panel(atenciones)
    mapa_zonas = mapa_zonas_atenciones_panel(atenciones)
    disponibilidad = completar_cliente_desde_atenciones_panel(disponibilidad, atenciones, mapa_clientes)
    reclamos = completar_cliente_desde_atenciones_panel(reclamos, atenciones, mapa_clientes)
    disponibilidad = completar_zona_desde_atenciones_panel(disponibilidad, atenciones, mapa_zonas)
    reclamos = completar_zona_desde_atenciones_panel(reclamos, atenciones, mapa_zonas)
    reclamos = deduplicar_reclamos_ticket_familia_panel(reclamos)
    uso_herramienta = cargar_uso_herramienta_servicios(servicios)
    return atenciones, epa, disponibilidad, reclamos, uso_herramienta


def filtrar_base_por_servicios(base, servicios):
    if base is None or base.empty or "servicio_tecnico" not in base.columns:
        return base
    servicios_validos = set(servicios)
    return base.loc[base["servicio_tecnico"].isin(servicios_validos)].copy()


def preparar_export_uso_herramienta(df_uso_base):
    vista = df_uso_base.copy()
    columnas = [
        "servicio_tecnico", "folio_ot", "ticket", "cliente", "ciudad", "region_atendida",
        "fecha_atencion", "hora_inicio", "hora_termino", "tecnico", "puntaje_total", "puntaje_pct",
        "estado_calidad", "score_identificacion", "score_detalle", "score_equipos",
        "score_activo_fijo", "score_redaccion", "score_firmas", "requiere_retiro",
        "requiere_instalacion", "cliente_cge", "activo_fijo_detectado", "hallazgos",
        "fortalezas", "descripcion", "archivo_pdf", "correo_asunto", "fecha_correo",
        "fuente_clasificacion", "match_score",
    ]
    columnas = [col for col in columnas if col in vista.columns]
    vista = vista[columnas] if columnas else vista
    return vista.rename(columns={
        "servicio_tecnico": "Servicio tecnico",
        "folio_ot": "Folio OT",
        "ticket": "Ticket",
        "cliente": "Cliente",
        "ciudad": "Ciudad",
        "region_atendida": "Region atendida",
        "fecha_atencion": "Fecha atencion",
        "hora_inicio": "Hora inicio",
        "hora_termino": "Hora termino",
        "tecnico": "Tecnico",
        "puntaje_total": "Nota OT",
        "puntaje_pct": "Puntaje equivalente %",
        "estado_calidad": "Clasificacion",
        "score_identificacion": "Score identificacion",
        "score_detalle": "Score detalle",
        "score_equipos": "Score equipos",
        "score_activo_fijo": "Score activo fijo",
        "score_redaccion": "Score redaccion",
        "score_firmas": "Score firmas",
        "requiere_retiro": "Requiere retiro",
        "requiere_instalacion": "Requiere instalacion",
        "cliente_cge": "Cliente CGE",
        "activo_fijo_detectado": "Activo fijo detectado",
        "hallazgos": "Hallazgos",
        "fortalezas": "Fortalezas",
        "descripcion": "Descripcion OT",
        "archivo_pdf": "Archivo PDF",
        "correo_asunto": "Asunto correo",
        "fecha_correo": "Fecha correo",
        "fuente_clasificacion": "Fuente clasificacion",
        "match_score": "Score match tecnico",
    })


def preparar_vista_reclamos_limpia(df_reclamos_export):
    columnas = [
        "Servicio tecnico", "Fecha hora reclamo", "Cliente", "Numero ticket", "Ticket principal",
        "Tipo señal", "Familia reclamo", "Motivo reclamo", "Severidad", "ST reforzado", "Region", "Ciudad",
    ]
    columnas = [col for col in columnas if col in df_reclamos_export.columns]
    return df_reclamos_export[columnas].copy() if columnas else df_reclamos_export.copy()


def render_boton_revisitas(df_revisitas, filtros_export):
    nombre_archivo = f"revisitas_filtradas_entel_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    st.download_button(
        "Descargar revisitas",
        data=lambda: crear_excel_filtrado(df_revisitas, filtros_export),
        file_name=nombre_archivo,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="descargar_revisitas_filtradas",
        help="Descargar revisitas filtradas",
        on_click="ignore",
        type="tertiary",
        icon=":material/download:",
        width="stretch",
    )


def render_boton_exportar_epa_revision(df_epa_export, filtros_export):
    nombre_archivo = f"epa_filtrada_entel_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    st.download_button(
        "Descargar EPA",
        data=lambda: crear_excel_filtrado(
            df_epa_export,
            filtros_export,
            "EPA filtrada",
            "Vista filtrada EPA Entel",
        ),
        file_name=nombre_archivo,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="descargar_epa_revision",
        help="Descargar EPA filtrada",
        on_click="ignore",
        type="tertiary",
        icon=":material/download:",
        width="stretch",
    )


def render_boton_exportar_datos(df_export, filtros_export, modo="datos"):
    es_epa = modo == "epa"
    es_disponibilidad = modo == "disponibilidad"
    es_reclamos = modo == "reclamos"
    es_uso_herramienta = modo == "uso_herramienta"
    nombre_archivo = (
        f"epa_filtrada_entel_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        if es_epa else
        f"disponibilidad_filtrada_entel_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        if es_disponibilidad else
        f"reclamos_filtrados_entel_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        if es_reclamos else
        f"uso_herramienta_ot_filtrado_entel_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        if es_uso_herramienta else
        f"vista_filtrada_entel_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    )
    sheet_name = "EPA filtrada" if es_epa else "Disponibilidad" if es_disponibilidad else "Reclamos" if es_reclamos else "KPI Uso Herramienta" if es_uso_herramienta else "Datos filtrados"
    titulo_excel = (
        "Vista filtrada EPA Entel" if es_epa else
        f"KPI Disponibilidad {SERVICIO_TITULO}" if es_disponibilidad else
        f"KPI Reclamos {SERVICIO_TITULO}" if es_reclamos else
        f"KPI Uso correcto de herramienta {SERVICIO_TITULO}" if es_uso_herramienta else
        "Vista filtrada dashboard operaciones"
    )
    titulo_link = "Exportar EPA filtrada" if es_epa else "Exportar disponibilidad filtrada" if es_disponibilidad else "Exportar reclamos filtrados" if es_reclamos else "Exportar auditoria OT filtrada" if es_uso_herramienta else "Exportar datos filtrados"
    kicker = "EPA filtrada" if es_epa else "KPI Disponibilidad" if es_disponibilidad else "KPI Reclamos" if es_reclamos else "KPI Uso Herramienta" if es_uso_herramienta else "Datos filtrados"
    texto_boton = "Exportar EPA" if es_epa else "Exportar disponibilidad" if es_disponibilidad else "Exportar reclamos" if es_reclamos else "Exportar OT" if es_uso_herramienta else "Exportar datos"
    st.download_button(
        f"{kicker} · {texto_boton}",
        data=lambda: crear_excel_filtrado(df_export, filtros_export, sheet_name, titulo_excel),
        file_name=nombre_archivo,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"exportar_panel_{modo}",
        help=titulo_link,
        on_click="ignore",
        type="primary",
        icon=":material/download:",
        width="stretch",
    )

SERVICIOS_CARGA = tuple(SERVICIOS_CONFIG) if MODO_GERENCIAL else tuple(SERVICIOS_ACTIVOS)
(
    df,
    df_epa,
    df_disponibilidad,
    df_reclamos,
    df_uso_herramienta,
) = cargar_bases_preparadas(
    SERVICIOS_CARGA,
    versiones_bases_panel(SERVICIOS_CARGA),
)
if set(SERVICIOS_ACTIVOS) != set(SERVICIOS_CARGA):
    df = filtrar_base_por_servicios(df, SERVICIOS_ACTIVOS)
    df_epa = filtrar_base_por_servicios(df_epa, SERVICIOS_ACTIVOS)
    df_disponibilidad = filtrar_base_por_servicios(df_disponibilidad, SERVICIOS_ACTIVOS)
    df_reclamos = filtrar_base_por_servicios(df_reclamos, SERVICIOS_ACTIVOS)
    df_uso_herramienta = filtrar_base_por_servicios(df_uso_herramienta, SERVICIOS_ACTIVOS)
EPA_DB_ACTIVA = ruta_epa_activa(SERVICIOS_ACTIVOS[0])

KPI_INICIO = "KPI Inicio Actividad"
KPI_EPA = "KPI EPA Satisfacci\u00f3n"
KPI_USO_HERRAMIENTA = "KPI Uso correcto de herramienta"
KPI_DISPONIBILIDAD = "KPI Disponibilidad"
KPI_RECLAMOS = "KPI Reclamos"
KPI_OPCIONES = [KPI_INICIO, KPI_EPA, KPI_USO_HERRAMIENTA, KPI_DISPONIBILIDAD, KPI_RECLAMOS]
DEMO_TECH_KEYWORDS = ("DEMO", "PRUEBA", "TEST")
CLIENTE_EPA_EXCLUIR_EXACTO = {"CLIENTE VISUAL"}
CLIENTE_EPA_EXCLUIR_KEYWORDS = ("DEMO", "PRUEBA", "TEST")


def es_tecnico_demo(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = texto.encode("ascii", "ignore").decode("ascii").upper()
    return any(keyword in texto for keyword in DEMO_TECH_KEYWORDS)


def es_cliente_epa_no_real(valor):
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = texto.encode("ascii", "ignore").decode("ascii").upper()
    texto = " ".join(texto.split())
    if texto in CLIENTE_EPA_EXCLUIR_EXACTO:
        return True
    return any(keyword in texto for keyword in CLIENTE_EPA_EXCLUIR_KEYWORDS)


if "cliente" in df_epa.columns:
    cliente_real_mask = df_epa["cliente"].map(es_cliente_epa_no_real).fillna(False).astype(bool)
    df_epa = df_epa.loc[~cliente_real_mask].copy()

if st.session_state.get("kpi_activo") not in KPI_OPCIONES:
    st.session_state["kpi_activo"] = KPI_INICIO

pagina_epa_activa = st.session_state.get("kpi_activo") == KPI_EPA
pagina_uso_herramienta_activa = st.session_state.get("kpi_activo") == KPI_USO_HERRAMIENTA
pagina_disponibilidad_activa = st.session_state.get("kpi_activo") == KPI_DISPONIBILIDAD
pagina_reclamos_activa = st.session_state.get("kpi_activo") == KPI_RECLAMOS
pagina_disp_rec_activa = pagina_disponibilidad_activa or pagina_reclamos_activa
disponibilidad_no_aplica_servicio = (not SERVICIO_COMPARATIVO) and (not SERVICIOS_CONFIG.get(SERVICIO_ACTUAL, {}).get("participa_disponibilidad", True))
reclamos_no_aplica_servicio = (not SERVICIO_COMPARATIVO) and (not SERVICIOS_CONFIG.get(SERVICIO_ACTUAL, {}).get("participa_reclamos", True))
pagina_kpi_no_aplica_servicio = (
    (pagina_disponibilidad_activa and disponibilidad_no_aplica_servicio)
    or (pagina_reclamos_activa and reclamos_no_aplica_servicio)
)
if pagina_kpi_no_aplica_servicio:
    pagina_disp_rec_activa = False

# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:

    df_filtros_base = df
    if pagina_uso_herramienta_activa and not df_uso_herramienta.empty:
        df_filtros_base = df_uso_herramienta.rename(columns={"region_atendida": "Estado", "tecnico": "Recurso"}).copy()

    regiones = sorted(
        df_filtros_base["Estado"].dropna().astype(str).str.strip().replace("", pd.NA).dropna().unique()
    ) if "Estado" in df_filtros_base.columns else []
    tecnicos = sorted({
        str(t).strip() for t in df_filtros_base["Recurso"].dropna().unique()
        if str(t).strip() and not es_tecnico_demo(t)
    }) if "Recurso" in df_filtros_base.columns else []
    clientes_epa = sorted(
        c for c in df_epa["cliente"].dropna().astype(str).str.strip().replace("", pd.NA).dropna().unique()
        if not es_cliente_epa_no_real(c)
    ) if "cliente" in df_epa.columns else []
    clientes_reclamos = sorted(
        c for c in df_reclamos["cliente"].dropna().astype(str).str.strip().replace("", pd.NA).dropna().unique()
    ) if "cliente" in df_reclamos.columns else []
    clientes_disponibilidad = sorted(set(
        c for c in df_disponibilidad["cliente"].dropna().astype(str).str.strip().replace("", pd.NA).dropna().unique()
    ) | set(clientes_reclamos)) if "cliente" in df_disponibilidad.columns else clientes_reclamos
    zonas_reclamos = sorted(
        z for z in df_reclamos["region"].dropna().astype(str).str.strip().replace("", pd.NA).dropna().unique()
    ) if "region" in df_reclamos.columns else []
    zonas_atenciones = sorted(
        z for z in df["Estado"].dropna().astype(str).str.strip().replace("", pd.NA).dropna().unique()
    ) if "Estado" in df.columns else []
    zonas_disponibilidad = sorted(set(
        z for z in df_disponibilidad["region"].dropna().astype(str).str.strip().replace("", pd.NA).dropna().unique()
    ) | set(zonas_reclamos) | set(zonas_atenciones)) if "region" in df_disponibilidad.columns else sorted(set(zonas_reclamos) | set(zonas_atenciones))
    coordinadores_disponibilidad = []
    if SERVICIO_ACTUAL == "SAO" and "coordinador" in df_disponibilidad.columns:
        base_coord = df_disponibilidad.copy()
        if "correo_coordinador" not in base_coord.columns:
            base_coord["correo_coordinador"] = ""
        if "fecha_respuesta" in base_coord.columns:
            base_coord = base_coord.loc[base_coord["fecha_respuesta"].notna()].copy()
        base_coord["_coord_email_norm"] = base_coord["correo_coordinador"].map(correo_limpio_panel)
        base_coord["_coord_nombre_email_norm"] = base_coord["coordinador"].map(correo_limpio_panel)
        base_coord["_coord_nombre_norm"] = base_coord["coordinador"].map(normalizar_texto_operacional)
        base_coord = base_coord.loc[
            base_coord["_coord_email_norm"].isin(SAO_COORDINADORES_AUDITADOS.keys())
            | base_coord["_coord_nombre_email_norm"].isin(SAO_COORDINADORES_AUDITADOS.keys())
            | base_coord["_coord_nombre_norm"].isin(SAO_COORDINADORES_NOMBRES.keys())
        ].copy()
        base_coord["coordinador"] = [
            nombre_coordinador_sao(nombre, correo)
            for nombre, correo in zip(base_coord["coordinador"], base_coord["correo_coordinador"])
        ]
        coordinadores_disponibilidad = sorted(
            c for c in base_coord["coordinador"].dropna().astype(str).str.strip().replace("", pd.NA).dropna().unique()
            if c != "Sin respuesta"
        )

    for r in regiones:
        if f"reg_{r}" not in st.session_state:
            st.session_state[f"reg_{r}"] = True

    for t in tecnicos:
        if f"tec_{t}" not in st.session_state:
            st.session_state[f"tec_{t}"] = True

    for m in MESES:
        if f"mes_{m}" not in st.session_state:
            st.session_state[f"mes_{m}"] = m in MESES_HASTA_HOY
        elif m not in MESES_HASTA_HOY:
            st.session_state[f"mes_{m}"] = False

    for c in clientes_epa:
        if f"cli_{c}" not in st.session_state:
            st.session_state[f"cli_{c}"] = True

    for c in clientes_disponibilidad:
        if f"disp_cli_{c}" not in st.session_state:
            st.session_state[f"disp_cli_{c}"] = True

    for z in zonas_disponibilidad:
        if f"disp_zona_{z}" not in st.session_state:
            st.session_state[f"disp_zona_{z}"] = True

    for c in coordinadores_disponibilidad:
        if f"disp_coord_{c}" not in st.session_state:
            st.session_state[f"disp_coord_{c}"] = True

    for estado in DISPONIBILIDAD_ESTADOS:
        if f"disp_estado_{estado}" not in st.session_state:
            st.session_state[f"disp_estado_{estado}"] = True

    def boton_toggle_filtro(items, prefijo, key, texto_activar, texto_limpiar):
        todos_activos = bool(items) and all(
            st.session_state.get(f"{prefijo}_{item}", False)
            for item in items
        )
        etiqueta = texto_limpiar if todos_activos else texto_activar

        def aplicar_toggle():
            kpi_en_curso = st.session_state.get("kpi_activo", KPI_INICIO)
            nuevo_estado = not todos_activos
            for item in items:
                st.session_state[f"{prefijo}_{item}"] = nuevo_estado
            st.session_state[f"{key}_empty_intent"] = not nuevo_estado
            if kpi_en_curso in KPI_OPCIONES:
                st.session_state["kpi_activo"] = kpi_en_curso

        st.button(
            etiqueta,
            width="stretch",
            key=key,
            on_click=aplicar_toggle,
        )

    def asegurar_filtro_con_seleccion(items, prefijo, key_toggle, permitir_vacio=True):
        if not items:
            return False
        hay_activo = any(st.session_state.get(f"{prefijo}_{item}", False) for item in items)
        if hay_activo or (permitir_vacio and st.session_state.get(f"{key_toggle}_empty_intent", False)):
            return False
        for item in items:
            st.session_state[f"{prefijo}_{item}"] = True
        st.session_state[f"{key_toggle}_empty_intent"] = False
        return True

    def inicializar_pills_filtro(items, key):
        items_lista = list(items)
        if st.session_state.get(f"{key}_force_all", False):
            st.session_state[key] = items_lista
            st.session_state[f"{key}_force_all"] = False

        seleccion = st.session_state.get(key, items_lista)
        if seleccion is None:
            seleccion = []
        if not isinstance(seleccion, list):
            seleccion = [seleccion]
        seleccion = [item for item in seleccion if item in items_lista]
        if not seleccion and not st.session_state.get(f"{key}_empty_intent", False):
            seleccion = items_lista
        if st.session_state.get(key) != seleccion:
            st.session_state[key] = seleccion
        return seleccion

    def boton_seleccionar_todo_pills(items, key, key_boton):
        items_lista = list(items)
        seleccion = list(st.session_state.get(key, items_lista))
        todos_activos = bool(items_lista) and set(seleccion) == set(items_lista)
        etiqueta = "Vaciar todo" if todos_activos else "Seleccionar todo"

        def aplicar_toggle():
            kpi_en_curso = st.session_state.get("kpi_activo", KPI_INICIO)
            st.session_state[key] = [] if todos_activos else items_lista
            st.session_state[f"{key}_empty_intent"] = todos_activos
            if kpi_en_curso in KPI_OPCIONES:
                st.session_state["kpi_activo"] = kpi_en_curso

        st.button(
            etiqueta,
            width="stretch",
            key=key_boton,
            on_click=aplicar_toggle,
        )

    def proteger_pills_vacios(seleccion, key):
        if seleccion:
            st.session_state[f"{key}_empty_intent"] = False
            return list(seleccion)
        if st.session_state.get(f"{key}_empty_intent", False):
            return []
        kpi_en_curso = st.session_state.get("kpi_activo", KPI_INICIO)
        st.session_state[f"{key}_force_all"] = True
        if kpi_en_curso in KPI_OPCIONES:
            st.session_state["kpi_activo"] = kpi_en_curso
        st.rerun()

    def fechas_periodo_pagina():
        if pagina_disponibilidad_activa and not df_disponibilidad.empty:
            return df_disponibilidad.get("fecha_solicitud")
        if pagina_reclamos_activa and not df_reclamos.empty:
            return df_reclamos.get("fecha_reclamo")
        if pagina_uso_herramienta_activa and not df_uso_herramienta.empty:
            return df_uso_herramienta.get("fecha_atencion")
        if pagina_epa_activa and not df_epa.empty:
            fecha_atencion = fechas_calendario(df_epa.get("fecha_atencion"))
            fecha_respuesta = fechas_calendario(df_epa.get("respuesta_creada"))
            return fecha_atencion.fillna(fecha_respuesta)
        return df.get("Fecha de Agendamiento")

    def render_filtro_semanas(meses_seleccionados, key, key_boton):
        opciones = semanas_calendario_disponibles(fechas_periodo_pagina(), meses_seleccionados)
        if not opciones:
            st.markdown('<div class="filter-mini-note">Sin semanas con fecha para el periodo seleccionado</div>', unsafe_allow_html=True)
            return [], []
        inicializar_pills_filtro(opciones, key)
        st.markdown('<div class="filter-subheading">SEMANAS DEL AÑO</div>', unsafe_allow_html=True)
        boton_seleccionar_todo_pills(opciones, key, key_boton)
        seleccion = st.pills(
            "Semanas del año",
            opciones,
            selection_mode="multi",
            format_func=etiqueta_semana_calendario,
            key=key,
            label_visibility="collapsed",
            width="stretch",
        )
        return proteger_pills_vacios(seleccion, key), opciones

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    region = list(regiones)
    tecnico = list(tecnicos)
    meses_sel = list(MESES_HASTA_HOY)
    semanas_sel = []
    semanas_disponibles = []
    clientes_sel = clientes_epa
    disp_clientes_sel = clientes_disponibilidad
    disp_coordinadores_sel = []
    disp_zonas_sel = zonas_disponibilidad
    disp_estados_sel = list(DISPONIBILIDAD_ESTADOS)

    if pagina_disp_rec_activa:
        inicializar_pills_filtro(clientes_disponibilidad, "disp_cli_pills")
        inicializar_pills_filtro(zonas_disponibilidad, "disp_zona_pills")
        inicializar_pills_filtro(MESES_HASTA_HOY, "disp_mes_pills")
        if pagina_disponibilidad_activa:
            inicializar_pills_filtro(DISPONIBILIDAD_ESTADOS, "disp_estado_pills")

        disp_clientes_sel = []
        with st.expander("CLIENTE", expanded=False):
            st.markdown('<span class="filter-anchor filter-anchor-client"></span>', unsafe_allow_html=True)
            boton_seleccionar_todo_pills(
                clientes_disponibilidad,
                "disp_cli_pills",
                "toggle_clientes_disponibilidad_pills"
            )
            st.markdown(f'<div class="filter-mini-note">Mostrando {len(clientes_disponibilidad)} clientes con solicitudes o reclamos</div>', unsafe_allow_html=True)
            disp_clientes_sel = st.pills(
                "Clientes disponibilidad",
                clientes_disponibilidad,
                selection_mode="multi",
                key="disp_cli_pills",
                label_visibility="collapsed",
                width="stretch"
            )
            disp_clientes_sel = proteger_pills_vacios(disp_clientes_sel, "disp_cli_pills")

        disp_zonas_sel = []
        with st.expander("ZONAS", expanded=False):
            st.markdown('<span class="filter-anchor filter-anchor-region"></span>', unsafe_allow_html=True)
            boton_seleccionar_todo_pills(
                zonas_disponibilidad,
                "disp_zona_pills",
                "toggle_zonas_disponibilidad_pills"
            )
            st.markdown(f'<div class="filter-mini-note">Mostrando {len(zonas_disponibilidad)} zonas con solicitudes o reclamos</div>', unsafe_allow_html=True)
            disp_zonas_sel = st.pills(
                "Zonas disponibilidad",
                zonas_disponibilidad,
                selection_mode="multi",
                key="disp_zona_pills",
                label_visibility="collapsed",
                width="stretch"
            )
            disp_zonas_sel = proteger_pills_vacios(disp_zonas_sel, "disp_zona_pills")

        disp_coordinadores_sel = []

        if pagina_disponibilidad_activa:
            disp_estados_sel = []
            with st.expander("ESTADO", expanded=False):
                st.markdown('<span class="filter-anchor filter-anchor-status"></span>', unsafe_allow_html=True)
                boton_seleccionar_todo_pills(
                    DISPONIBILIDAD_ESTADOS,
                    "disp_estado_pills",
                    "toggle_estados_disponibilidad_pills"
                )
                st.markdown('<div class="filter-mini-note">Vista SLA de disponibilidad</div>', unsafe_allow_html=True)
                disp_estados_sel = st.pills(
                    "Estado disponibilidad",
                    DISPONIBILIDAD_ESTADOS,
                    selection_mode="multi",
                    key="disp_estado_pills",
                    label_visibility="collapsed",
                    width="stretch"
                )
                disp_estados_sel = proteger_pills_vacios(disp_estados_sel, "disp_estado_pills")

        meses_sel=[]
        with st.expander("PERIODO", expanded=False):
            st.markdown('<span class="filter-anchor filter-anchor-period"></span>', unsafe_allow_html=True)
            boton_seleccionar_todo_pills(
                MESES_HASTA_HOY,
                "disp_mes_pills",
                "toggle_meses_disponibilidad_pills"
            )
            meses_sel = st.pills(
                "Periodo disponibilidad",
                MESES_HASTA_HOY,
                selection_mode="multi",
                format_func=lambda m: MESES_CORTOS.get(m, m),
                key="disp_mes_pills",
                label_visibility="collapsed",
                width="stretch"
            )
            meses_sel = proteger_pills_vacios(meses_sel, "disp_mes_pills")
            st.markdown(
                f'<div class="filter-mini-note">Disponible hasta {MES_ACTUAL_CORTO} {ANIO_PANEL}; los meses futuros se habilitan solos.</div>',
                unsafe_allow_html=True,
            )
            semanas_sel, semanas_disponibles = render_filtro_semanas(
                meses_sel,
                "disp_semana_pills",
                "toggle_semanas_disponibilidad_pills",
            )

    else:
        region=[]
        with st.expander("REGIÓN", expanded=False):
            st.markdown('<span class="filter-anchor filter-anchor-region"></span>', unsafe_allow_html=True)
            boton_toggle_filtro(
                regiones,
                "reg",
                "toggle_regiones",
                "Seleccionar todo",
                "Vaciar todo"
            )
            st.markdown('<div class="filter-mini-note">Zonas incluidas en la vista</div>', unsafe_allow_html=True)

            for r in regiones:
                if st.checkbox(r, key=f"reg_{r}"):
                    region.append(r)

        if region and "Estado" in df_filtros_base.columns and "Recurso" in df_filtros_base.columns:
            tecnicos_filtro = sorted({
                str(t).strip()
                for t in df_filtros_base.loc[df_filtros_base["Estado"].isin(region), "Recurso"].dropna().unique()
                if str(t).strip() and not es_tecnico_demo(t)
            })
            tecnico_contexto = f"de {region[0]}" if len(region) == 1 else f"de {len(region)} zonas seleccionadas"
        else:
            tecnicos_filtro = []
            tecnico_contexto = "porque no hay zonas seleccionadas"

        tecnico=[]
        with st.expander("TÉCNICO", expanded=False):
            st.markdown('<span class="filter-anchor filter-anchor-tech"></span>', unsafe_allow_html=True)

            boton_toggle_filtro(
                tecnicos_filtro,
                "tec",
                "toggle_tecnicos",
                "Seleccionar todo",
                "Vaciar todo"
            )
            st.markdown(f'<div class="filter-mini-note">Mostrando {len(tecnicos_filtro)} técnicos {tecnico_contexto}</div>', unsafe_allow_html=True)

            for t in tecnicos_filtro:
                st.checkbox(t, key=f"tec_{t}")

            tecnico = [t for t in tecnicos_filtro if st.session_state.get(f"tec_{t}", False)]

        meses_sel=[]
        with st.expander("PERIODO", expanded=False):
            st.markdown('<span class="filter-anchor filter-anchor-period"></span>', unsafe_allow_html=True)
            boton_toggle_filtro(
                MESES_HASTA_HOY,
                "mes",
                "toggle_meses",
                "Seleccionar todo",
                "Vaciar todo"
            )
            st.markdown(
                f'<div class="filter-mini-note">Acumulado hasta {MES_ACTUAL_CORTO} {ANIO_PANEL}; sin meses futuros.</div>',
                unsafe_allow_html=True,
            )

            c1,c2=st.columns(2)
            mitad_meses = (len(MESES_HASTA_HOY) + 1) // 2
            for i,m in enumerate(MESES_HASTA_HOY):
                with (c1 if i < mitad_meses else c2):
                    st.checkbox(MESES_CORTOS.get(m, m), key=f"mes_{m}")
                    if st.session_state[f"mes_{m}"]:
                        meses_sel.append(m)
            semanas_sel, semanas_disponibles = render_filtro_semanas(
                meses_sel,
                "semana_pills",
                "toggle_semanas_pills",
            )

        clientes_sel = clientes_epa
        if pagina_epa_activa:
            clientes_sel = []
            with st.expander("CLIENTE", expanded=False):
                st.markdown('<span class="filter-anchor filter-anchor-client"></span>', unsafe_allow_html=True)

                boton_toggle_filtro(
                    clientes_epa,
                    "cli",
                    "toggle_clientes_epa",
                    "Seleccionar todo",
                    "Vaciar todo"
                )
                st.markdown(f'<div class="filter-mini-note">Mostrando {len(clientes_epa)} clientes EPA</div>', unsafe_allow_html=True)

                for c in clientes_epa:
                    st.checkbox(c, key=f"cli_{c}")

                clientes_sel = [c for c in clientes_epa if st.session_state.get(f"cli_{c}", False)]
    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)

semanas_filtro_activo = bool(semanas_disponibles)

VISTA_TECNICO_SOLICITADA = bool(
    not pagina_disp_rec_activa
    and tecnico
    and "tecnicos_filtro" in locals()
    and set(map(str, tecnico)) != set(map(str, tecnicos_filtro))
)

# =========================================================
# FILTROS
# =========================================================

df_f = df.copy()

if "Estado" in df_f.columns:
    df_f = df_f.loc[df_f["Estado"].isin(region)]

    if "Recurso" in df_f.columns and not df_f.empty:
        tecnico_demo_mask = df_f["Recurso"].map(es_tecnico_demo).fillna(False).astype(bool)
        df_f = df_f.loc[~tecnico_demo_mask]
        if tecnico:
            df_f = df_f.loc[df_f["Recurso"].isin(tecnico)]
        else:
            df_f = df_f.iloc[0:0]

if "Mes" in df_f.columns:
    df_f = df_f.loc[df_f["Mes"].isin(meses_sel)]

if semanas_filtro_activo and "Fecha de Agendamiento" in df_f.columns:
    if semanas_sel:
        df_f = df_f.loc[serie_semana_iso(df_f["Fecha de Agendamiento"]).isin(set(semanas_sel))]
    else:
        df_f = df_f.iloc[0:0]

filtros_export = {
    "regiones": region,
    "tecnicos": tecnico,
    "meses": meses_sel,
    "semanas": [etiqueta_semana_calendario(semana) for semana in semanas_sel],
    "clientes": disp_clientes_sel if pagina_disp_rec_activa else clientes_sel,
    "zonas": disp_zonas_sel,
    "estados": disp_estados_sel if pagina_disponibilidad_activa else [],
    "servicio_tecnico": SERVICIOS_ACTIVOS,
}

df_epa_f = df_epa.copy()

if not df_epa_f.empty:
    for col in ["respondida", "q1", "q2", "q3", "q4", "q5", "promedio"]:
        if col in df_epa_f.columns:
            df_epa_f[col] = pd.to_numeric(df_epa_f[col], errors="coerce")

    if region and len(region) < len(regiones) and "region" in df_epa_f.columns:
        regiones_disponibles_epa = set(df_epa_f["region"].dropna().astype(str))
        regiones_seleccionadas = set(map(str, region))
        if regiones_disponibles_epa & regiones_seleccionadas:
            df_epa_f = df_epa_f[df_epa_f["region"].astype(str).isin(regiones_seleccionadas)]

    if tecnico and "tecnico" in df_epa_f.columns:
        tecnicos_disponibles_epa = set(df_epa_f["tecnico"].dropna().astype(str))
        tecnicos_seleccionados = set(map(str, tecnico))
        if tecnicos_disponibles_epa & tecnicos_seleccionados:
            df_epa_f = df_epa_f[df_epa_f["tecnico"].astype(str).isin(tecnicos_seleccionados)]

    if pagina_epa_activa and clientes_epa and "cliente" in df_epa_f.columns:
        clientes_seleccionados = set(map(str, clientes_sel))
        df_epa_f = df_epa_f[df_epa_f["cliente"].fillna("").astype(str).isin(clientes_seleccionados)]

    fecha_atencion_epa = pd.to_datetime(df_epa_f.get("fecha_atencion"), errors="coerce")
    fecha_respuesta_epa = pd.to_datetime(df_epa_f.get("respuesta_creada"), errors="coerce", utc=True)
    if hasattr(fecha_respuesta_epa, "dt"):
        fecha_respuesta_epa = fecha_respuesta_epa.dt.tz_localize(None)

    df_epa_f["_fecha_epa"] = fecha_atencion_epa.fillna(fecha_respuesta_epa)

    if meses_sel and len(meses_sel) < len(MESES):
        mes_epa = df_epa_f["_fecha_epa"].dt.month.map(lambda mes: MESES[mes - 1] if pd.notna(mes) else None)
        df_epa_f = df_epa_f[mes_epa.isin(meses_sel) | df_epa_f["_fecha_epa"].isna()]
    if semanas_filtro_activo:
        if semanas_sel:
            df_epa_f = df_epa_f.loc[serie_semana_iso(df_epa_f["_fecha_epa"]).isin(set(semanas_sel))]
        else:
            df_epa_f = df_epa_f.iloc[0:0]

df_epa_respondidas = df_epa_f[df_epa_f.get("respondida", pd.Series(dtype=float)).fillna(0).astype(int).eq(1)].copy()
epa_total_atenciones = len(df_epa_f)
epa_total_respuestas = len(df_epa_respondidas)
epa_pendientes = max(epa_total_atenciones - epa_total_respuestas, 0)
epa_promedio = float(df_epa_respondidas["promedio"].dropna().mean()) if epa_total_respuestas and "promedio" in df_epa_respondidas.columns else 0
epa_satisfechas = int(df_epa_respondidas["promedio"].ge(4).sum()) if epa_total_respuestas and "promedio" in df_epa_respondidas.columns else 0
epa_satisfaccion = round(epa_satisfechas / max(epa_total_respuestas, 1) * 100, 1)
epa_recomendacion = float(df_epa_respondidas["q5"].dropna().mean()) if epa_total_respuestas and "q5" in df_epa_respondidas.columns else 0
df_epa_export = preparar_export_epa(df_epa_f)

df_disp_f = df_disponibilidad.copy()
if not df_disp_f.empty:
    if clientes_disponibilidad and "cliente" in df_disp_f.columns:
        df_disp_f = df_disp_f.loc[df_disp_f["cliente"].astype(str).isin(set(map(str, disp_clientes_sel)))]

    if zonas_disponibilidad and "region" in df_disp_f.columns:
        df_disp_f = df_disp_f.loc[df_disp_f["region"].astype(str).isin(set(map(str, disp_zonas_sel)))]

    if meses_sel:
        mes_disp_f = serie_mes_operacional(df_disp_f, "fecha_solicitud", "mes")
        df_disp_f = df_disp_f.loc[mes_disp_f.isin(set(map(str, meses_sel)))]
    else:
        df_disp_f = df_disp_f.iloc[0:0]

    if semanas_filtro_activo:
        if semanas_sel and "fecha_solicitud" in df_disp_f.columns:
            df_disp_f = df_disp_f.loc[serie_semana_iso(df_disp_f["fecha_solicitud"]).isin(set(semanas_sel))]
        else:
            df_disp_f = df_disp_f.iloc[0:0]

    estados_sla = set(disp_estados_sel) & {"Cumple", "No cumple"}
    if estados_sla and "cumple_kpi" in df_disp_f.columns:
        cumple_mask = df_disp_f["cumple_kpi"].fillna(False).astype(bool)
        if "estado_kpi" in df_disp_f.columns:
            cumple_mask = cumple_mask | df_disp_f["estado_kpi"].astype(str).str.strip().str.lower().eq("cumple")
        estado_mask = pd.Series(False, index=df_disp_f.index)
        if "Cumple" in estados_sla:
            estado_mask = estado_mask | cumple_mask
        if "No cumple" in estados_sla:
            estado_mask = estado_mask | ~cumple_mask
        df_disp_f = df_disp_f.loc[estado_mask]
    elif pagina_disponibilidad_activa:
        df_disp_f = df_disp_f.iloc[0:0]

df_reclamos_f = df_reclamos.copy()
if not df_reclamos_f.empty:
    if clientes_disponibilidad and "cliente" in df_reclamos_f.columns:
        df_reclamos_f = df_reclamos_f.loc[df_reclamos_f["cliente"].astype(str).isin(set(map(str, disp_clientes_sel)))]

    if zonas_disponibilidad and "region" in df_reclamos_f.columns:
        df_reclamos_f = df_reclamos_f.loc[df_reclamos_f["region"].astype(str).isin(set(map(str, disp_zonas_sel)))]

    if meses_sel:
        mes_reclamos_f = serie_mes_operacional(df_reclamos_f, "fecha_reclamo", "mes")
        df_reclamos_f = df_reclamos_f.loc[mes_reclamos_f.isin(set(map(str, meses_sel)))]
    else:
        df_reclamos_f = df_reclamos_f.iloc[0:0]

    if semanas_filtro_activo:
        if semanas_sel and "fecha_reclamo" in df_reclamos_f.columns:
            df_reclamos_f = df_reclamos_f.loc[serie_semana_iso(df_reclamos_f["fecha_reclamo"]).isin(set(semanas_sel))]
        else:
            df_reclamos_f = df_reclamos_f.iloc[0:0]

    if pagina_disponibilidad_activa and "Reclamo" not in set(disp_estados_sel):
        df_reclamos_f = df_reclamos_f.iloc[0:0]

df_atenciones_reclamos_f = filtrar_atenciones_reclamos_panel(
    df_f,
    disp_clientes_sel if pagina_disp_rec_activa else [],
    clientes_disponibilidad if pagina_disp_rec_activa else [],
    disp_zonas_sel if pagina_disp_rec_activa else [],
    zonas_disponibilidad if pagina_disp_rec_activa else [],
)

disp_total = len(df_disp_f)
disp_cumple = int(df_disp_f["cumple_kpi"].fillna(False).astype(bool).sum()) if disp_total and "cumple_kpi" in df_disp_f.columns else 0
disp_no_cumple = max(disp_total - disp_cumple, 0)
disp_sin_respuesta = int(df_disp_f["fecha_respuesta"].isna().sum()) if disp_total and "fecha_respuesta" in df_disp_f.columns else 0
disp_pct = round(disp_cumple / max(disp_total, 1) * 100, 1)
disp_promedio_min = float(df_disp_f["minutos_habiles"].dropna().mean()) if disp_total and "minutos_habiles" in df_disp_f.columns else 0
reiteraciones_operacionales_serie = calcular_reiteraciones_total_operacional(df_disp_f) if disp_total else pd.Series(dtype="float64")
disp_reiteraciones = int(reiteraciones_operacionales_serie.sum()) if disp_total else 0
disp_tickets_reiterados = int(df_disp_f.loc[reiteraciones_operacionales_serie.gt(0), "numero_ticket"].replace("", pd.NA).dropna().nunique()) if disp_total and "numero_ticket" in df_disp_f.columns else 0
disp_solicitudes_reiteradas = int(reiteraciones_operacionales_serie.gt(0).sum()) if disp_total else 0
disp_intervenciones_servicio = int(pd.to_numeric(df_disp_f["intervenciones_supervisor_servicio_tecnico"], errors="coerce").fillna(0).sum()) if disp_total and "intervenciones_supervisor_servicio_tecnico" in df_disp_f.columns else 0
disp_intervenciones_terreno = disp_intervenciones_servicio
disp_reit_cecom_operador = int(pd.to_numeric(df_disp_f["reiteraciones_cecom_operador"], errors="coerce").fillna(0).sum()) if disp_total and "reiteraciones_cecom_operador" in df_disp_f.columns else 0
disp_reit_supervisor_cecom = int(pd.to_numeric(df_disp_f["reiteraciones_supervisor_cecom"], errors="coerce").fillna(0).sum()) if disp_total and "reiteraciones_supervisor_cecom" in df_disp_f.columns else 0
disp_reit_cecom_total = disp_reit_cecom_operador + disp_reit_supervisor_cecom
disp_casos_multi_solicitud = int(df_disp_f.loc[pd.to_numeric(df_disp_f["total_solicitudes_caso"], errors="coerce").fillna(0).gt(1), "ticket_principal"].replace("", pd.NA).dropna().nunique()) if disp_total and {"total_solicitudes_caso", "ticket_principal"}.issubset(df_disp_f.columns) else 0
disp_brecha_meta = round(disp_pct - DISPONIBILIDAD_META_PCT, 1)
df_disp_export = preparar_export_disponibilidad(df_disp_f)
reclamos_total = len(df_reclamos_f)
reclamos_reforzamientos = int(serie_bool_panel(df_reclamos_f["reforzamiento"]).sum()) if reclamos_total and "reforzamiento" in df_reclamos_f.columns else 0
reclamos_reclamos_duros = max(reclamos_total - reclamos_reforzamientos, 0)
reclamos_alta = int(df_reclamos_f["severidad_reclamo"].astype(str).str.upper().eq("ALTA").sum()) if reclamos_total and "severidad_reclamo" in df_reclamos_f.columns else 0
reclamos_tickets = int(
    df_reclamos_f["ticket_principal"]
    .fillna("")
    .astype(str)
    .map(normalizar_ticket_panel)
    .replace("", pd.NA)
    .dropna()
    .nunique()
) if reclamos_total and "ticket_principal" in df_reclamos_f.columns else 0
reclamos_clientes = int(df_reclamos_f["cliente"].replace("", pd.NA).dropna().nunique()) if reclamos_total and "cliente" in df_reclamos_f.columns else 0
reclamos_motivo_top = df_reclamos_f["familia_reclamo"].replace("", pd.NA).dropna().mode().iloc[0] if reclamos_total and "familia_reclamo" in df_reclamos_f.columns and not df_reclamos_f["familia_reclamo"].replace("", pd.NA).dropna().empty else "Sin reclamos"
reclamos_motivo_top_count = int(df_reclamos_f["familia_reclamo"].astype(str).eq(str(reclamos_motivo_top)).sum()) if reclamos_total and "familia_reclamo" in df_reclamos_f.columns else 0
reclamos_cliente_counts = (
    df_reclamos_f["cliente"].fillna("").astype(str).str.strip().replace("", pd.NA).dropna().value_counts()
    if reclamos_total and "cliente" in df_reclamos_f.columns
    else pd.Series(dtype="int64")
)
reclamos_cliente_top = str(reclamos_cliente_counts.index[0]) if not reclamos_cliente_counts.empty else "Sin cliente"
reclamos_cliente_top_count = int(reclamos_cliente_counts.iloc[0]) if not reclamos_cliente_counts.empty else 0
reclamos_proveedor_reforzado_counts = (
    df_reclamos_f.loc[
        serie_bool_panel(df_reclamos_f["reforzamiento"]) if "reforzamiento" in df_reclamos_f.columns else pd.Series(False, index=df_reclamos_f.index),
        "proveedor_reforzado",
    ].fillna("").astype(str).str.strip().replace("", pd.NA).dropna().value_counts()
    if reclamos_reforzamientos and "proveedor_reforzado" in df_reclamos_f.columns
    else pd.Series(dtype="int64")
)
reclamos_proveedor_reforzado_top = str(reclamos_proveedor_reforzado_counts.index[0]) if not reclamos_proveedor_reforzado_counts.empty else "Sin reforzar"
reclamos_proveedor_reforzado_top_count = int(reclamos_proveedor_reforzado_counts.iloc[0]) if not reclamos_proveedor_reforzado_counts.empty else 0
if reclamos_total and reclamos_cliente_top_count and {"cliente", "ticket_principal"}.issubset(df_reclamos_f.columns):
    mask_cliente_foco = df_reclamos_f["cliente"].fillna("").astype(str).str.strip().eq(reclamos_cliente_top)
    reclamos_cliente_top_tickets = int(
        df_reclamos_f.loc[mask_cliente_foco, "ticket_principal"]
        .fillna("")
        .astype(str)
        .map(normalizar_ticket_panel)
        .replace("", pd.NA)
        .dropna()
        .nunique()
    )
else:
    reclamos_cliente_top_tickets = 0
atenciones_asignadas_reclamos = len(df_atenciones_reclamos_f)
reclamos_ratio_incumplimiento = round(reclamos_total / max(atenciones_asignadas_reclamos, 1) * 100, 1) if atenciones_asignadas_reclamos else 0
reclamos_cumplimiento_ajustado = round(max(0, 100 - reclamos_ratio_incumplimiento), 1)
reclamos_brecha_meta = round(reclamos_cumplimiento_ajustado - RECLAMOS_META_CUMPLIMIENTO_PCT, 1)
df_reclamos_export = preparar_export_reclamos(df_reclamos_f)

df_uso_f = df_uso_herramienta.copy()
if not df_uso_f.empty:
    if region and "region_atendida" in df_uso_f.columns:
        df_uso_f = df_uso_f.loc[df_uso_f["region_atendida"].astype(str).isin(set(map(str, region)))]

    if tecnico and "tecnico" in df_uso_f.columns:
        df_uso_f = df_uso_f.loc[df_uso_f["tecnico"].astype(str).isin(set(map(str, tecnico)))]

    fecha_uso = pd.to_datetime(df_uso_f.get("fecha_atencion"), format="mixed", dayfirst=True, errors="coerce")
    df_uso_f["_fecha_uso"] = fecha_uso
    if meses_sel:
        mes_uso = fecha_uso.dt.month.map(lambda mes: MESES[int(mes) - 1] if pd.notna(mes) and 1 <= int(mes) <= 12 else None)
        df_uso_f = df_uso_f.loc[mes_uso.isin(set(map(str, meses_sel))) | fecha_uso.isna()]
    else:
        df_uso_f = df_uso_f.iloc[0:0]
    if semanas_filtro_activo:
        if semanas_sel:
            df_uso_f = df_uso_f.loc[serie_semana_iso(df_uso_f["_fecha_uso"]).isin(set(semanas_sel))]
        else:
            df_uso_f = df_uso_f.iloc[0:0]

uso_total = len(df_uso_f)
uso_promedio = float(df_uso_f["puntaje_total"].dropna().mean()) if uso_total and "puntaje_total" in df_uso_f.columns else 0
uso_excelentes = int(df_uso_f["estado_calidad"].astype(str).eq("Excelente").sum()) if uso_total and "estado_calidad" in df_uso_f.columns else 0
uso_buenas = int(df_uso_f["estado_calidad"].astype(str).eq("Bueno").sum()) if uso_total and "estado_calidad" in df_uso_f.columns else 0
uso_regulares = int(df_uso_f["estado_calidad"].astype(str).eq("Regular").sum()) if uso_total and "estado_calidad" in df_uso_f.columns else 0
uso_criticas = int(df_uso_f["estado_calidad"].astype(str).eq("Critico").sum()) if uso_total and "estado_calidad" in df_uso_f.columns else 0
uso_ok = uso_excelentes + uso_buenas
uso_pct_ok = round(uso_ok / max(uso_total, 1) * 100, 1) if uso_total else 0
uso_retiros_incompletos = int(
    df_uso_f["hallazgos"].fillna("").astype(str).str.contains("Retiro sin declarar", case=False, na=False).sum()
) if uso_total and "hallazgos" in df_uso_f.columns else 0
uso_detalle_incompleto = int(
    df_uso_f["hallazgos"].fillna("").astype(str).str.contains(
        "detalle de equipo|equipo intervenido|serie|maquina|máquina|marca/modelo|activo fijo",
        case=False,
        na=False,
    ).sum()
) if uso_total and "hallazgos" in df_uso_f.columns else 0
uso_cge_sin_activo = int(
    (
        df_uso_f["cliente_cge"].fillna("").astype(str).str.upper().eq("SI")
        & ~df_uso_f["activo_fijo_detectado"].fillna("").astype(str).str.upper().eq("SI")
    ).sum()
) if uso_total and {"cliente_cge", "activo_fijo_detectado"}.issubset(df_uso_f.columns) else 0
uso_tecnicos = int(df_uso_f["tecnico"].replace("", pd.NA).dropna().nunique()) if uso_total and "tecnico" in df_uso_f.columns else 0
uso_brecha_meta = round(uso_promedio - USO_HERRAMIENTA_META_NOTA, 1) if uso_total else 0
df_uso_export = preparar_export_uso_herramienta(df_uso_f)


def resumen_comparativo_disponibilidad_proveedor(df_base):
    if not SERVICIO_COMPARATIVO or df_base is None or df_base.empty or "servicio_tecnico" not in df_base.columns:
        return ""
    base = df_base.copy()
    base["_cumple"] = base["cumple_kpi"].fillna(False).astype(bool) if "cumple_kpi" in base.columns else False
    base["_sin_respuesta"] = base["fecha_respuesta"].isna() if "fecha_respuesta" in base.columns else False
    base["_reiteraciones"] = calcular_reiteraciones_total_operacional(base)
    resumen = (
        base.groupby("servicio_tecnico", dropna=False)
        .agg(
            solicitudes=("_cumple", "size"),
            cumple=("_cumple", "sum"),
            sin_respuesta=("_sin_respuesta", "sum"),
            reiteraciones=("_reiteraciones", "sum"),
        )
        .reset_index()
    )
    if resumen.empty:
        return ""
    resumen["pct"] = (resumen["cumple"] / resumen["solicitudes"].clip(lower=1) * 100).round(1)
    resumen["fuera"] = resumen["solicitudes"] - resumen["cumple"]
    resumen = resumen.sort_values("pct", ascending=True)
    return "; ".join(
        f"{row.servicio_tecnico}: {row.pct:.1f}% ({int(row.fuera)} fuera SLA, {int(row.sin_respuesta)} sin respuesta, {int(row.reiteraciones)} reiteraciones)"
        for row in resumen.itertuples(index=False)
    )


def resumen_comparativo_reclamos_proveedor(df_rec_base, df_atenciones_base):
    if not SERVICIO_COMPARATIVO:
        return ""
    if df_atenciones_base is None or df_atenciones_base.empty or "servicio_tecnico" not in df_atenciones_base.columns:
        return ""

    atenciones = (
        df_atenciones_base.copy()
        .assign(servicio_tecnico=lambda tmp: tmp["servicio_tecnico"].fillna("Sin dato").astype(str).str.strip().replace({"": "Sin dato"}))
        .groupby("servicio_tecnico", dropna=False)
        .size()
        .reset_index(name="atenciones")
    )
    if df_rec_base is not None and not df_rec_base.empty and "servicio_tecnico" in df_rec_base.columns:
        rec = df_rec_base.copy()
        rec["servicio_tecnico"] = rec["servicio_tecnico"].fillna("Sin dato").astype(str).str.strip().replace({"": "Sin dato"})
        rec["_alta"] = rec["severidad_reclamo"].astype(str).str.upper().eq("ALTA") if "severidad_reclamo" in rec.columns else False
        rec["_reforzamiento"] = serie_bool_panel(rec["reforzamiento"]) if "reforzamiento" in rec.columns else False
        reclamos = (
            rec.groupby("servicio_tecnico", dropna=False)
            .agg(reclamos=("servicio_tecnico", "size"), alta=("_alta", "sum"), reforzamientos=("_reforzamiento", "sum"))
            .reset_index()
        )
    else:
        reclamos = pd.DataFrame(columns=["servicio_tecnico", "reclamos", "alta", "reforzamientos"])

    resumen = atenciones.merge(reclamos, on="servicio_tecnico", how="left")
    resumen[["reclamos", "alta", "reforzamientos"]] = resumen[["reclamos", "alta", "reforzamientos"]].fillna(0)
    resumen["ratio"] = (resumen["reclamos"] / resumen["atenciones"].replace(0, pd.NA) * 100).fillna(0).round(1)
    resumen["cumplimiento"] = (100 - resumen["ratio"]).clip(lower=0).round(1)
    resumen = resumen.sort_values("cumplimiento", ascending=True)
    return "; ".join(
        f"{row.servicio_tecnico}: {int(row.reclamos)} señales ({int(row.reforzamientos)} ref.)/{int(row.atenciones)} atenciones, {row.ratio:.1f}% incumplimiento, {row.cumplimiento:.1f}% cumplimiento"
        for row in resumen.itertuples(index=False)
    )


def resumen_comparativo_uso_herramienta_proveedor(df_uso_base):
    if not SERVICIO_COMPARATIVO or df_uso_base is None or df_uso_base.empty or "servicio_tecnico" not in df_uso_base.columns:
        return ""
    base = df_uso_base.copy()
    base["servicio_tecnico"] = base["servicio_tecnico"].fillna("Sin dato").astype(str).str.strip().replace({"": "Sin dato"})
    base["_ok"] = base["estado_calidad"].astype(str).isin(["Excelente", "Bueno"]) if "estado_calidad" in base.columns else False
    resumen = (
        base.groupby("servicio_tecnico", dropna=False)
        .agg(
            ots=("servicio_tecnico", "size"),
            nota=("puntaje_total", "mean"),
            ok=("_ok", "sum"),
        )
        .reset_index()
    )
    if resumen.empty:
        return ""
    resumen["nota"] = resumen["nota"].fillna(0).round(1)
    resumen["pct_ok"] = (resumen["ok"] / resumen["ots"].clip(lower=1) * 100).round(1)
    resumen = resumen.sort_values(["nota", "pct_ok"], ascending=[True, True])
    return "; ".join(
        f"{row.servicio_tecnico}: nota {row.nota:.1f}/7, {row.pct_ok:.1f}% excelente/bueno en {int(row.ots)} OT"
        for row in resumen.itertuples(index=False)
    )


comparativo_disponibilidad_proveedor = resumen_comparativo_disponibilidad_proveedor(df_disp_f)
comparativo_reclamos_proveedor = resumen_comparativo_reclamos_proveedor(df_reclamos_f, df_atenciones_reclamos_f)
comparativo_uso_herramienta_proveedor = resumen_comparativo_uso_herramienta_proveedor(df_uso_f)

# =========================================================
# CALCULO CUMPLE: INICIO <= VENTANA + 15 MIN
# =========================================================

def hora_operativa_a_timedelta(serie):
    texto = serie.astype(str).str.strip()
    texto = texto.str.replace(",", ".", regex=False)

    hora_extraida = texto.str.extract(r"(\d{1,2}:\d{2}(?::\d{2})?)", expand=False)
    texto = hora_extraida.fillna(texto)
    texto = texto.where(texto.str.count(":").ge(2), texto + ":00")

    tiempo = pd.to_timedelta(texto, errors="coerce")

    numero = pd.to_numeric(serie, errors="coerce")
    tiempo_excel = pd.Series(pd.NaT, index=serie.index, dtype="timedelta64[ns]")
    numero_valido = numero.between(0, 1)
    if numero_valido.any():
        tiempo_excel.loc[numero_valido] = pd.to_timedelta(numero.loc[numero_valido], unit="D")

    return tiempo.fillna(tiempo_excel)

if "Ventana de entrega" in df_f.columns and "Inicio" in df_f.columns:

    ventana_td = hora_operativa_a_timedelta(df_f["Ventana de entrega"])
    inicio_td = hora_operativa_a_timedelta(df_f["Inicio"])

    # Cumple si inicia antes de la ventana o hasta 15 minutos despues.
    df_f["Dif"] = (inicio_td - ventana_td).dt.total_seconds() / 60
    df_f["Cumple"] = ventana_td.notna() & inicio_td.notna() & df_f["Dif"].le(15)

else:

    df_f["Cumple"] = False

# =========================================================
# KPIS
# =========================================================


def texto_normalizado(serie):
    return serie.fillna("").astype(str).map(
        lambda texto: unicodedata.normalize("NFKD", texto)
        .encode("ascii", "ignore")
        .decode("ascii")
        .upper()
    )


def motivo_no_realizado_estandar(valor):
    if pd.isna(valor):
        return "Otros"

    texto = unicodedata.normalize("NFKD", str(valor).strip())
    texto = texto.encode("ascii", "ignore").decode("ascii").upper()
    texto = "".join(caracter if caracter.isalnum() or caracter.isspace() else " " for caracter in texto)
    texto = " ".join(texto.split())

    if not texto or texto in {"NAN", "NONE", "NULL", "SIN INFORMACION"}:
        return "Otros"

    tokens = set(texto.split())

    if "USUARIO" in tokens and any(palabra.startswith("COORDIN") for palabra in tokens):
        return "Usuario coordina"

    if "USUARIO" in tokens and "ENCUENTRA" in tokens and ("NO" in tokens or "UBICA" in tokens):
        return "Usuario no se encuentra"

    if "USUARIO" in tokens and any(palabra.startswith("RECHAZ") for palabra in tokens):
        return "Usuario rechaza visita"

    if "SUCURSAL" in tokens and any(palabra.startswith("PROBLEMA") for palabra in tokens):
        return "Problema de sucursal"

    if "FUERZA" in tokens and "MAYOR" in tokens:
        return "Fuerza mayor"

    return texto.lower().capitalize()


def consolidar_motivos_no_realizado(serie):
    return serie.map(motivo_no_realizado_estandar).value_counts()


TICKET_ID_COLS = ["ID Externo", "ID externo", "ID Ticket", "Ticket", "Ticket ID", "Numero Ticket", "Número Ticket"]


def preparar_visitas_ticket(df_base, estado_col_base=None):
    id_col = next((c for c in TICKET_ID_COLS if c in df_base.columns), None)
    if not id_col:
        return None

    columnas = [id_col]
    if estado_col_base and estado_col_base in df_base.columns:
        columnas.append(estado_col_base)

    base = df_base[columnas].copy()
    base["_idx_original"] = df_base.index
    base["_id_ticket_original"] = base[id_col].fillna("").astype(str).str.strip()
    base["_id_ticket_orden"] = base["_id_ticket_original"]

    sin_id = base["_id_ticket_orden"].eq("")
    base.loc[sin_id, "_id_ticket_orden"] = "__SIN_ID__" + base.loc[sin_id, "_idx_original"].astype(str)

    if "Fecha de Agendamiento" in df_base.columns:
        base["_fecha_orden"] = pd.to_datetime(df_base["Fecha de Agendamiento"], format="mixed", dayfirst=True, errors="coerce")
    else:
        base["_fecha_orden"] = pd.NaT

    if "Inicio" in df_base.columns:
        hora_texto = df_base["Inicio"].astype(str).str.strip()
        hora_texto = hora_texto.where(hora_texto.str.count(":").ge(2), hora_texto + ":00")
        base["_hora_orden"] = pd.to_timedelta(hora_texto, errors="coerce")
    else:
        base["_hora_orden"] = pd.NaT

    base = base.sort_values(["_id_ticket_orden", "_fecha_orden", "_hora_orden", "_idx_original"])
    base["_numero_visita_ticket"] = base.groupby("_id_ticket_orden").cumcount().add(1)
    return base


def numero_visita_ticket(df_base):
    numero_visita = pd.Series(1, index=df_base.index, dtype="int64")
    base = preparar_visitas_ticket(df_base)

    if base is None:
        return numero_visita

    numero_visita.loc[base["_idx_original"]] = base["_numero_visita_ticket"].astype("int64").to_numpy()
    return numero_visita


def detectar_revisitas(df_base):
    estado_col_base = next(
        (c for c in ["Estado de actividad", "Estado Actividad"] if c in df_base.columns),
        None
    )

    base = preparar_visitas_ticket(df_base, estado_col_base)

    if base is not None and estado_col_base:
        base["_estado_norm"] = texto_normalizado(base[estado_col_base])
        base["_no_realizado"] = base["_estado_norm"].str.contains("NO REALIZAD|NO FINALIZAD", na=False)
        no_realizado_previo = (
            base.groupby("_id_ticket_orden")["_no_realizado"]
                .cummax()
                .groupby(base["_id_ticket_orden"])
                .shift(fill_value=False)
        )

        revisita_ordenada = (
            base["_numero_visita_ticket"].ge(3)
            & no_realizado_previo
            & base["_id_ticket_original"].ne("")
        )
        revisita_mask = pd.Series(False, index=df_base.index)
        revisita_mask.loc[base["_idx_original"]] = revisita_ordenada.to_numpy()
        return revisita_mask

    revisita_cols = [c for c in df_base.columns if "revis" in str(c).lower()]

    if revisita_cols:
        serie = df_base[revisita_cols[0]]
        if pd.api.types.is_numeric_dtype(serie):
            valores = pd.to_numeric(serie, errors="coerce").fillna(0)
            return valores > 0

        texto = texto_normalizado(serie)
        return texto.str.contains(r"\b(SI|TRUE|VERDADERO|1)\b|REVIS", regex=True, na=False)

    texto_cols = [
        c for c in [
            "Tipo de actividad", "Tipo Actividad", "Actividad", "Trabajo",
            "Resultado", "Acción Realizada", "Accion Realizada",
            "Observación", "Observacion"
        ]
        if c in df_base.columns
    ]

    revisita_mask = pd.Series(False, index=df_base.index)
    for col in texto_cols:
        texto = texto_normalizado(df_base[col])
        revisita_mask |= texto.str.contains(r"REVIS|TERCERA VISITA|3RA VISITA|3ERA VISITA|VISITA 3", regex=True, na=False)

    return revisita_mask


def contar_revisitas(df_base):
    return int(detectar_revisitas(df_base).sum())


total = len(df_f)

cumple = int(df_f["Cumple"].sum())

pct = round(
    (cumple / total) * 100,
    2
) if total else 0

estado_col = next(
    (c for c in ["Estado de actividad", "Estado Actividad", "Estado"] if c in df_f.columns),
    None
)

estado = df_f[estado_col].astype(str).str.upper() if estado_col else pd.Series(["FINAL"] * len(df_f), index=df_f.index)
estado_final_mask = estado.str.contains("FINAL", na=False)
numero_visita_global = numero_visita_ticket(df)
numero_visita = numero_visita_global.reindex(df_f.index).fillna(1).astype("int64")
revisita_mask_global = detectar_revisitas(df)
revisita_mask = revisita_mask_global.reindex(df_f.index).fillna(False).astype(bool)

finalizadas = int(estado_final_mask.sum())
no_finalizadas = total - finalizadas
total_atenciones = total
pct_fin = round(finalizadas / max(total_atenciones, 1) * 100, 1)
pct_no_fin = round(no_finalizadas / max(total_atenciones, 1) * 100, 1)
revisitas = int(revisita_mask.sum())
pct_revisitas = round(revisitas / max(total_atenciones, 1) * 100, 1)
finalizadas_primera_visita = int((estado_final_mask & numero_visita.eq(1)).sum())
pct_primera_visita = round(finalizadas_primera_visita / max(total_atenciones, 1) * 100, 1)

comparativo_inicio_proveedor = ""
if SERVICIO_COMPARATIVO and total_atenciones and "servicio_tecnico" in df_f.columns:
    base_inicio_comp = df_f.copy()
    base_inicio_comp["_cumple_inicio"] = df_f["Cumple"].fillna(False).astype(bool)
    base_inicio_comp["_revisita"] = revisita_mask.reindex(df_f.index).fillna(False).astype(bool)
    base_inicio_comp["_finalizada_primera"] = (estado_final_mask & numero_visita.eq(1)).reindex(df_f.index).fillna(False).astype(bool)
    resumen_inicio_comp = (
        base_inicio_comp.assign(servicio_tecnico=lambda tmp: tmp["servicio_tecnico"].fillna("Sin ST").astype(str).str.strip().replace({"": "Sin ST"}))
        .groupby("servicio_tecnico", dropna=False)
        .agg(
            atenciones=("servicio_tecnico", "size"),
            cumple=("_cumple_inicio", "sum"),
            primera=("_finalizada_primera", "sum"),
            revisitas=("_revisita", "sum"),
        )
        .reset_index()
    )
    resumen_inicio_comp["pct"] = (resumen_inicio_comp["cumple"] / resumen_inicio_comp["atenciones"].clip(lower=1) * 100).round(1)
    resumen_inicio_comp["pct_revisitas"] = (resumen_inicio_comp["revisitas"] / resumen_inicio_comp["atenciones"].clip(lower=1) * 100).round(1)
    resumen_inicio_comp = resumen_inicio_comp.sort_values("pct", ascending=True)
    comparativo_inicio_proveedor = "; ".join(
        f"{row.servicio_tecnico}: {row.pct:.1f}% inicio, {int(row.revisitas)} revisitas ({row.pct_revisitas:.1f}%)"
        for row in resumen_inicio_comp.itertuples(index=False)
    )

df_export = df_f.copy()
df_export["Numero visita ticket"] = numero_visita
df_export["Estado final detectado"] = estado_final_mask.map({True: "Si", False: "No"})
df_export["Revisita detectada"] = revisita_mask.map({True: "Si", False: "No"})

df_revisitas_export = df_f.loc[revisita_mask].copy()
df_revisitas_export["Numero visita ticket"] = numero_visita.reindex(df_revisitas_export.index)
df_revisitas_export["Estado final detectado"] = estado_final_mask.reindex(df_revisitas_export.index).map({True: "Si", False: "No"})
df_revisitas_export["Revisita detectada"] = revisita_mask.reindex(df_revisitas_export.index).map({True: "Si", False: "No"})
df_revisitas_export["Regla revisita"] = "Visita 3 o superior con No Realizado previo"

with st.sidebar:
    if pagina_disponibilidad_activa and not disponibilidad_no_aplica_servicio:
        render_boton_exportar_datos(df_disp_export, filtros_export, modo="disponibilidad")
    elif pagina_reclamos_activa and not reclamos_no_aplica_servicio:
        render_boton_exportar_datos(df_reclamos_export, filtros_export, modo="reclamos")
    elif pagina_disponibilidad_activa or pagina_reclamos_activa:
        st.markdown('<div class="filter-mini-note">Sin datos exportables para este KPI.</div>', unsafe_allow_html=True)
    elif pagina_epa_activa:
        render_boton_exportar_datos(df_epa_export, filtros_export, modo="epa")
    elif pagina_uso_herramienta_activa:
        render_boton_exportar_datos(df_uso_export, filtros_export, modo="uso_herramienta")
    else:
        render_boton_exportar_datos(df_export, filtros_export)

# =========================================================
# HEADER
# =========================================================


@st.fragment(run_every=60)
def render_reloj_calendario_panel():
    ahora = datetime.now(ZONA_HORARIA_PANEL)
    fecha_actual = ahora.date().isoformat()
    fecha_anterior = st.session_state.get("_fecha_calendario_panel")
    st.session_state["_fecha_calendario_panel"] = fecha_actual
    if fecha_anterior and fecha_anterior != fecha_actual:
        st.rerun(scope="app")

    iso = ahora.isocalendar()
    dias = ("LUN", "MAR", "MIÉ", "JUE", "VIE", "SÁB", "DOM")
    meses = ("ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC")
    st.markdown(
        f"""
        <div class="calendar-header-card" title="Fecha y hora de Santiago; se actualiza automáticamente">
            <div class="calendar-header-icon"><i></i><span>{ahora.day:02d}</span></div>
            <div class="calendar-header-copy">
                <small>HOY · SANTIAGO</small>
                <strong>SEMANA {iso.week:02d}</strong>
                <p>{dias[ahora.weekday()]} {ahora.day:02d} {meses[ahora.month - 1]} · {ahora.strftime('%H:%M')}</p>
            </div>
            <b class="calendar-live-dot" aria-hidden="true"></b>
        </div>
        """,
        unsafe_allow_html=True,
    )


c1, c_calendario, c2 = st.columns([6.8,1.75,1], gap="small")

with c1:

    st.markdown("""
    <div class="titulo">
        Panel de Adherencia Entel Connect
    </div>

    <div class="linea-titulo"></div>

    <div class="subtitulo">
        Cumplimiento de KPI, adherencia operacional y desempeño del Servicio Técnico Externo.
    </div>
    """, unsafe_allow_html=True)


with c_calendario:
    render_reloj_calendario_panel()


with c2:
    if LOGO_ST_DATA:
        st.markdown(
            f"""
            <div class="brand-lockup {LOGO_ST_CLASS}">
                <img src="{LOGO_ST_DATA}" alt="{SERVICIO_ACTUAL}" draggable="false">
            </div>
            """,
            unsafe_allow_html=True
        )


KPI_METODOLOGIA = {
    KPI_INICIO: {
        "color": CELESTE,
        "titulo": "Inicio de actividad: puntualidad de la visita",
        "pregunta": "¿Qué porcentaje de las atenciones comenzó dentro del tiempo permitido?",
        "calculo": "Una atención es puntual cuando el inicio real ocurre antes de la ventana o, como máximo, 15 minutos después. KPI = puntuales ÷ atenciones con horas válidas × 100.",
        "lectura": "80% o más cumple la meta. Entre 75% y 79,9% requiere vigilancia; bajo 75% necesita un plan correctivo. Un inicio adelantado sí cumple.",
        "datos": "WFM 2026. Cambia con ST, región, técnico, mes y semana seleccionados.",
        "ejemplo": "De 100 atenciones válidas, 82 comenzaron dentro de la tolerancia: el KPI es 82% y cumple la meta.",
    },
    KPI_EPA: {
        "color": VERDE,
        "titulo": "EPA: satisfacción informada por el usuario",
        "pregunta": "¿Qué porcentaje de quienes respondieron evaluó satisfactoriamente la atención?",
        "calculo": "Se promedian Q1 a Q5 de cada encuesta. Una respuesta es satisfactoria si su promedio es 4 o más. KPI = satisfactorias ÷ encuestas respondidas × 100.",
        "lectura": "90% o más cumple la meta. Las encuestas pendientes no bajan el KPI, pero una muestra pequeña hace menos representativo el resultado.",
        "datos": "Encuestas EPA IBM, SAO y ECC, escala 1 a 5. Cambia con los filtros activos.",
        "ejemplo": "Si responden 20 usuarios y 18 obtienen promedio 4 o 5, la satisfacción es 90%. Las encuestas pendientes se informan aparte.",
    },
    KPI_USO_HERRAMIENTA: {
        "color": NARANJO,
        "titulo": "Uso de herramienta: calidad de la OT",
        "pregunta": "¿Qué tan completa y trazable quedó la orden de trabajo después de la visita?",
        "calculo": "La OT suma puntos por identificación, detalle técnico, equipos, activo fijo, redacción, firmas y evidencias. Nota = 1 + (porcentaje documental × 6).",
        "lectura": f"La escala es de 1 a 7. La meta es nota {USO_HERRAMIENTA_META_NOTA:.1f} ({USO_HERRAMIENTA_META_PCT}%). Datos faltantes o retiros sin declarar reducen la nota.",
        "datos": "PDF de OT extraídos desde PST. Cambia con ST, región, técnico, mes y semana.",
        "ejemplo": f"Una OT con {USO_HERRAMIENTA_META_PCT}% de los requisitos obtiene nota {USO_HERRAMIENTA_META_NOTA:.1f} y alcanza la meta.",
    },
    KPI_DISPONIBILIDAD: {
        "color": ROSADO,
        "titulo": "Disponibilidad: velocidad de respuesta del ST",
        "pregunta": f"¿Qué porcentaje de las solicitudes CECOM recibió respuesta del ST dentro de {DISPONIBILIDAD_SLA_MIN} minutos hábiles?",
        "calculo": f"KPI = solicitudes respondidas en {DISPONIBILIDAD_SLA_MIN} minutos o menos ÷ solicitudes medibles × 100.",
        "lectura": f"{DISPONIBILIDAD_META_PCT}% o más cumple. Una solicitud sin respuesta o respondida fuera del plazo no cumple. El reloj solo corre de lunes a viernes, 08:00 a 19:00.",
        "datos": "Correos PST clasificados. Las reiteraciones muestran fricción, pero no duplican la solicitud en el denominador.",
        "ejemplo": f"Si 90 de 100 solicitudes se responden dentro de {DISPONIBILIDAD_SLA_MIN} minutos hábiles, el KPI es 90% y cumple la meta.",
    },
    KPI_RECLAMOS: {
        "color": AZUL_CLARO,
        "titulo": "Reclamos: impacto sobre las atenciones",
        "pregunta": "¿Qué proporción de las atenciones generó una señal operacional, ya sea reclamo o reforzamiento?",
        "calculo": "Ratio de señales = señales depuradas ÷ atenciones asignadas × 100. Cumplimiento ajustado = 100 − ratio de señales, con mínimo 0%.",
        "lectura": f"Cumple si el resultado ajustado es {RECLAMOS_META_CUMPLIMIENTO_PCT}% o más; equivale a mantener las señales en {RECLAMOS_META_RATIO_INCUMPLIMIENTO_PCT}% o menos.",
        "datos": "PST + WFM. Se elimina la repetición del mismo ticket y familia para no inflar el resultado.",
        "ejemplo": "Con 8 señales depuradas sobre 100 atenciones, el ratio es 8% y el cumplimiento ajustado es 92%: cumple.",
    },
}

KPI_LECTURA_SIMPLE = {
    KPI_INICIO: {
        "mide": "Muestra cuántas visitas comenzaron a tiempo respecto de su horario agendado.",
        "meta": "Está bien cuando 8 de cada 10 atenciones comienzan dentro de la tolerancia de 15 minutos.",
        "revisar": "Si baja, mira primero la zona y luego los técnicos con más atrasos repetidos.",
    },
    KPI_EPA: {
        "mide": "Resume qué tan conformes quedaron los usuarios que respondieron la encuesta.",
        "meta": "Está bien cuando al menos 9 de cada 10 respuestas son satisfactorias.",
        "revisar": "Si baja, revisa comentarios, preguntas con menor nota y la zona donde se repite el problema.",
    },
    KPI_USO_HERRAMIENTA: {
        "mide": "Revisa si la orden de trabajo quedó completa, clara y con las evidencias necesarias.",
        "meta": f"Está bien cuando la nota llega a {USO_HERRAMIENTA_META_NOTA:.1f} o más en la escala de 1 a 7.",
        "revisar": "Si baja, identifica qué dato o evidencia falta y corrígelo con el técnico responsable.",
    },
    KPI_DISPONIBILIDAD: {
        "mide": "Muestra si el ST respondió las solicitudes CECOM dentro del tiempo acordado.",
        "meta": f"Está bien cuando al menos {DISPONIBILIDAD_META_PCT:.0f}% recibe respuesta dentro de {DISPONIBILIDAD_SLA_MIN} minutos hábiles.",
        "revisar": "Si baja, comienza por las solicitudes sin respuesta y luego por las más atrasadas de cada zona.",
    },
    KPI_RECLAMOS: {
        "mide": "Muestra cuánto afectan los reclamos y reforzamientos al total de atenciones realizadas.",
        "meta": f"Está bien cuando el cumplimiento se mantiene en {RECLAMOS_META_CUMPLIMIENTO_PCT:.0f}% o más.",
        "revisar": "Si baja, busca la causa que más se repite, la zona afectada y el responsable de corregirla.",
    },
}


def render_tarjeta_metodologia_kpi(kpi):
    metodo = KPI_METODOLOGIA[kpi]
    simple = KPI_LECTURA_SIMPLE[kpi]
    bloques = [
        ("Qué muestra", simple["mide"], "01"),
        ("Cuándo está bien", simple["meta"], "OK"),
        ("Qué revisar", simple["revisar"], "→"),
    ]
    detalle_html = "".join(
        f"""
        <div class="kpi-method-item">
            <span class="kpi-method-item-icon">{html.escape(icono)}</span>
            <div>
                <span class="kpi-method-item-label">{html.escape(etiqueta)}</span>
                <p>{html.escape(str(texto))}</p>
            </div>
        </div>
        """
        for etiqueta, texto, icono in bloques
    )
    st.markdown(
        f"""
        <section class="kpi-method-card" style="--method-accent:{metodo['color']}">
            <div class="kpi-method-heading">
                <span class="kpi-method-main-icon">i</span>
                <div>
                    <span class="kpi-method-eyebrow">Cómo se mide</span>
                    <h3>{html.escape(metodo['titulo'])}</h3>
                    <p>Explicado en simple. El resultado cambia con los filtros seleccionados.</p>
                </div>
            </div>
            <div class="kpi-method-grid">{detalle_html}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )


kpi_activo = st.radio(
    "Selector KPI",
    KPI_OPCIONES,
    horizontal=True,
    label_visibility="collapsed",
    key="kpi_activo",
)

mostrar_kpi_inicio = kpi_activo == KPI_INICIO
mostrar_kpi_epa = kpi_activo == KPI_EPA
mostrar_kpi_uso_herramienta = kpi_activo == KPI_USO_HERRAMIENTA
mostrar_kpi_disponibilidad = kpi_activo == KPI_DISPONIBILIDAD
mostrar_kpi_reclamos = kpi_activo == KPI_RECLAMOS


if mostrar_kpi_inicio:
    st.markdown('<div class="kpi-divider"></div>', unsafe_allow_html=True)
    render_tarjeta_metodologia_kpi(KPI_INICIO)

# =========================================================
# # =========================================================
# =========================================================
# NOTA: Próxima mejora: reemplazar las 4 KPI Cards HTML por indicadores Plotly.
# =========================================================

# KPI CARDS GERENCIALES ENTEL - PLOTLY PRO
# =========================================================
# Tarjetas sobrias para dashboard gerencial: iconos dibujados con
# formas Plotly, acentos corporativos, lectura ejecutiva y barra de avance.


def rgba(hex_color, alpha):
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def dibujar_icono(fig_kpi, tipo, color):
    """Iconografía ejecutiva sin emojis: barras, check, alerta y gauge."""

    # Contenedor sutil del icono
    fig_kpi.add_shape(
        type="circle",
        x0=0.065, y0=0.655, x1=0.185, y1=0.855,
        xref="paper", yref="paper",
        fillcolor=rgba(color, 0.10),
        line=dict(color=rgba(color, 0.35), width=1.3),
        layer="above"
    )

    if tipo == "total":
        # Barras ejecutivas
        barras = [
            (0.094, 0.702, 0.108, 0.765),
            (0.122, 0.702, 0.136, 0.805),
            (0.150, 0.702, 0.164, 0.745),
        ]
        for x0, y0, x1, y1 in barras:
            fig_kpi.add_shape(
                type="rect", x0=x0, y0=y0, x1=x1, y1=y1,
                xref="paper", yref="paper",
                fillcolor=color,
                line=dict(color=color, width=0),
                layer="above"
            )
        fig_kpi.add_shape(
            type="line", x0=0.088, y0=0.695, x1=0.170, y1=0.695,
            xref="paper", yref="paper",
            line=dict(color=color, width=2),
            layer="above"
        )

    elif tipo == "ok":
        # Check dibujado con línea
        fig_kpi.add_trace(go.Scatter(
            x=[0.095, 0.122, 0.165],
            y=[0.745, 0.705, 0.805],
            mode="lines",
            line=dict(color=color, width=6),
            hoverinfo="skip",
            showlegend=False
        ))

    elif tipo == "no_ok":
        # Cruz sobria
        fig_kpi.add_trace(go.Scatter(
            x=[0.102, 0.162], y=[0.705, 0.805],
            mode="lines", line=dict(color=color, width=5),
            hoverinfo="skip", showlegend=False
        ))
        fig_kpi.add_trace(go.Scatter(
            x=[0.102, 0.162], y=[0.805, 0.705],
            mode="lines", line=dict(color=color, width=5),
            hoverinfo="skip", showlegend=False
        ))

    elif tipo == "global":
        # Target / desempeño
        for radio, ancho in [(0.048, 2.2), (0.030, 2.2), (0.012, 0)]:
            fig_kpi.add_shape(
                type="circle",
                x0=0.125-radio, y0=0.755-radio,
                x1=0.125+radio, y1=0.755+radio,
                xref="paper", yref="paper",
                fillcolor=color if radio == 0.012 else "rgba(255,255,255,0)",
                line=dict(color=color, width=ancho),
                layer="above"
            )
        fig_kpi.add_shape(
            type="line", x0=0.160, y0=0.790, x1=0.182, y1=0.825,
            xref="paper", yref="paper",
            line=dict(color=color, width=3),
            layer="above"
        )

    elif tipo == "revisita":
        # Ciclo / retorno: separa visualmente la revisita de una falla operacional.
        fig_kpi.add_shape(
            type="circle",
            x0=0.092, y0=0.705, x1=0.168, y1=0.805,
            xref="paper", yref="paper",
            fillcolor="rgba(255,255,255,0)",
            line=dict(color=color, width=3),
            layer="above"
        )
        fig_kpi.add_trace(go.Scatter(
            x=[0.158, 0.178, 0.163],
            y=[0.812, 0.822, 0.840],
            mode="lines",
            line=dict(color=color, width=3),
            hoverinfo="skip",
            showlegend=False
        ))
        fig_kpi.add_trace(go.Scatter(
            x=[0.100, 0.080, 0.095],
            y=[0.698, 0.688, 0.670],
            mode="lines",
            line=dict(color=color, width=3),
            hoverinfo="skip",
            showlegend=False
        ))


def kpi_card(container, tipo_icono, titulo, valor, subtitulo, color, indicador=None, progreso=None):
    with container:
        fig_kpi = go.Figure()
        valor_x = 0.42 if indicador is not None else 0.50

        # Sombra de profundidad dentro del lienzo Plotly.
        fig_kpi.add_shape(
            type="rect",
            x0=0.042, y0=0.022, x1=0.995, y1=0.895,
            xref="paper", yref="paper",
            fillcolor="rgba(15,23,42,0.135)",
            line=dict(color="rgba(15,23,42,0)", width=0),
            layer="below"
        )
        fig_kpi.add_shape(
            type="rect",
            x0=0.024, y0=0.055, x1=0.978, y1=0.928,
            xref="paper", yref="paper",
            fillcolor=rgba(color, 0.10),
            line=dict(color="rgba(15,23,42,0)", width=0),
            layer="below"
        )

        # Fondo principal con volumen sutil.
        fig_kpi.add_shape(
            type="rect",
            x0=0.000, y0=0.085, x1=0.955, y1=0.970,
            xref="paper", yref="paper",
            fillcolor="rgba(6,18,34,0.82)",
            line=dict(color=rgba(color, 0.46), width=1.5),
            layer="below"
        )

        # Brillo superior y acento corporativo.
        fig_kpi.add_shape(
            type="rect",
            x0=0.020, y0=0.910, x1=0.935, y1=0.952,
            xref="paper", yref="paper",
            fillcolor=rgba(color, 0.14),
            line=dict(color=rgba(color, 0), width=0),
            layer="above"
        )
        fig_kpi.add_shape(
            type="rect",
            x0=0.000, y0=0.945, x1=0.955, y1=0.970,
            xref="paper", yref="paper",
            fillcolor=color,
            line=dict(color=color, width=0),
            layer="above"
        )

        # Banda lateral y halo del valor para separar lectura KPI vs gráfico.
        fig_kpi.add_shape(
            type="rect",
            x0=0.000, y0=0.085, x1=0.012, y1=0.945,
            xref="paper", yref="paper",
            fillcolor=rgba(color, 0.20),
            line=dict(color=rgba(color, 0), width=0),
            layer="above"
        )
        fig_kpi.add_shape(
            type="circle",
            x0=valor_x - 0.190, y0=0.225, x1=valor_x + 0.190, y1=0.650,
            xref="paper", yref="paper",
            fillcolor=rgba(color, 0.13),
            line=dict(color=rgba(color, 0), width=0),
            layer="above"
        )

        dibujar_icono(fig_kpi, tipo_icono, color)

        fig_kpi.add_annotation(
            x=valor_x, y=0.725,
            xref="paper", yref="paper",
            text=f"<b>{titulo}</b>",
            showarrow=False,
            align="center",
            xanchor="center",
            font=dict(size=14, color="#EAFBFF", family="Segoe UI Semibold")
        )

        # Valor principal
        fig_kpi.add_annotation(
            x=valor_x + 0.002, y=0.465,
            xref="paper", yref="paper",
            text=f"<b>{valor}</b>",
            showarrow=False,
            align="center",
            xanchor="center",
            font=dict(size=31, color="rgba(255,255,255,0.12)", family="Segoe UI Black")
        )
        fig_kpi.add_annotation(
            x=valor_x, y=0.462,
            xref="paper", yref="paper",
            text=f"<b>{valor}</b>",
            showarrow=False,
            align="center",
            xanchor="center",
            font=dict(size=31, color=color, family="Segoe UI Black")
        )

        # Indicador derecho
        if indicador is not None:
            indicador_size = 15 if len(str(indicador)) > 5 else 18
            fig_kpi.add_shape(
                type="rect",
                x0=0.690, y0=0.390, x1=0.920, y1=0.570,
                xref="paper", yref="paper",
                fillcolor=rgba(color, 0.16),
                line=dict(color=rgba(color, 0.34), width=1),
                layer="above"
            )
            fig_kpi.add_annotation(
                x=0.805, y=0.480,
                xref="paper", yref="paper",
                text=f"<b>{indicador}</b>",
                showarrow=False,
                align="center",
                xanchor="center",
                font=dict(size=indicador_size, color=color, family="Segoe UI Black")
            )

        # Subtítulo
        fig_kpi.add_annotation(
            x=valor_x, y=0.245,
            xref="paper", yref="paper",
            text=subtitulo,
            showarrow=False,
            align="center",
            xanchor="center",
            font=dict(size=10, color="#BDEFFF", family="Segoe UI Semibold")
        )

        # Barra de avance inferior
        if progreso is not None:
            prog = max(0, min(float(progreso), 100)) / 100
            fig_kpi.add_shape(
                type="rect",
                x0=0.070, y0=0.098, x1=0.890, y1=0.124,
                xref="paper", yref="paper",
                fillcolor="rgba(143,239,255,0.14)",
                line=dict(color="rgba(143,239,255,0.14)", width=0),
                layer="above"
            )
            fig_kpi.add_shape(
                type="rect",
                x0=0.070, y0=0.098, x1=0.070 + 0.82 * prog, y1=0.124,
                xref="paper", yref="paper",
                fillcolor=color,
                line=dict(color=color, width=0),
                layer="above"
            )
            fig_kpi.add_shape(
                type="rect",
                x0=0.070, y0=0.124, x1=0.070 + 0.82 * prog, y1=0.134,
                xref="paper", yref="paper",
                fillcolor=rgba(color, 0.30),
                line=dict(color=rgba(color, 0), width=0),
                layer="above"
            )

        fig_kpi.update_layout(
            height=142,
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(visible=False, range=[0, 1], fixedrange=True),
            yaxis=dict(visible=False, range=[0, 1], fixedrange=True),
            showlegend=False,
            hovermode=False
        )

        st.plotly_chart(
            fig_kpi,
            width="stretch",
            config=PLOTLY_CONFIG_SOLO_LECTURA
        )


def render_kpi_card_grid(cards):
    def card(icono, titulo, valor, subtitulo, color, badge="", progreso=None):
        valor_texto = str(valor)
        es_valor_texto = not bool(re.fullmatch(r"\s*[-+]?\d+(?:[.,]\d+)?%?\s*", valor_texto))
        clase_valor = "disp-kpi-card is-text-value" if es_valor_texto else "disp-kpi-card"
        progress_value = 0 if progreso is None else max(0, min(float(progreso), 100))
        badge_html = f'<span class="disp-kpi-badge">{badge}</span>' if badge else ""
        progress_html = (
            f'<div class="disp-kpi-progress"><div class="disp-kpi-progress-fill" style="--progress:{progress_value:.1f}%;"></div></div>'
            if progreso is not None else ""
        )
        return (
            f'<div class="{clase_valor}" style="--accent:{color};">'
            f'<div class="disp-kpi-icon">{icono}</div>'
            f'<div class="disp-kpi-title">{titulo}</div>'
            f'<div class="disp-kpi-value-row"><div class="disp-kpi-value">{valor_texto}</div>{badge_html}</div>'
            f'<div class="disp-kpi-subtitle">{subtitulo}</div>'
            f'{progress_html}'
            f'</div>'
        )

    html_cards = [
        card(
            item.get("icono", "&#9673;"),
            item.get("titulo", ""),
            item.get("valor", ""),
            item.get("subtitulo", ""),
            item.get("color", CELESTE),
            item.get("badge", ""),
            item.get("progreso"),
        )
        for item in cards
    ]
    st.markdown(f'<div class="disp-kpi-grid">{"".join(html_cards)}</div>', unsafe_allow_html=True)


def render_estado_sin_datos(titulo="No hay datos para mostrar", detalle="", etiqueta="Sin datos"):
    detalle_html = f'<div class="no-data-detail">{html.escape(str(detalle))}</div>' if detalle else ""
    st.markdown(
        f"""
        <div class="no-data-shell">
            <div class="no-data-logo-wrap">
                <img src="{LOGO_ECC_ICONO_DATA}" alt="Entel Connect" draggable="false">
            </div>
            <div class="no-data-copy">
                <div class="no-data-kicker">{html.escape(str(etiqueta))}</div>
                <div class="no-data-title">{html.escape(str(titulo))}</div>
                {detalle_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def kpi_no_aplica_servicio(servicio, kpi):
    config = SERVICIOS_CONFIG.get(servicio, {})
    if kpi == KPI_DISPONIBILIDAD:
        return not config.get("participa_disponibilidad", True)
    if kpi == KPI_RECLAMOS:
        return not config.get("participa_reclamos", True)
    return False


def render_disponibilidad_kpi_cards(color_cumplimiento, disp_pct, disp_total, disp_cumple, disp_no_cumple, disp_sin_respuesta, disp_reit_cecom_total):
    render_kpi_card_grid([
        {"icono": "&#9673;", "titulo": "Cumplimiento KPI", "valor": f"{disp_pct:.1f}%", "subtitulo": f"<= {DISPONIBILIDAD_SLA_MIN} min habiles", "color": color_cumplimiento, "badge": f"Meta {DISPONIBILIDAD_META_PCT}%", "progreso": disp_pct},
        {"icono": "&#9606;", "titulo": "Solicitudes CECOM", "valor": disp_total, "subtitulo": "Desde 01-01-2026", "color": KPI_TOTAL},
        {"icono": "&#10003;", "titulo": "Cumplen KPI", "valor": disp_cumple, "subtitulo": f"Respuesta {SERVICIO_TITULO} transversal", "color": VERDE},
        {"icono": "&#10005;", "titulo": "No cumplen", "valor": disp_no_cumple, "subtitulo": f"{disp_sin_respuesta} sin respuesta", "color": ROSADO},
        {"icono": "&#8635;", "titulo": "Reiteraciones CECOM", "valor": disp_reit_cecom_total, "subtitulo": "Insistencias antes de respuesta", "color": CELESTE if disp_reit_cecom_total else VERDE},
    ])


def recomendacion_clara(indicador, estado, titulo, lectura, accion, tono):
    return {
        "indicador": indicador,
        "estado": estado,
        "titulo": titulo,
        "lectura": lectura,
        "accion": accion,
        "tono": tono,
    }


def estado_segun_meta(valor, meta, tolerancia=5.0, menor_es_mejor=False):
    brecha = (meta - valor) if menor_es_mejor else (valor - meta)
    if brecha >= 0:
        return "Meta cumplida", "bien", brecha
    if brecha >= -abs(tolerancia):
        return "Cerca de la meta", "accion", brecha
    return "Prioridad alta", "mal", brecha


def construir_insights_disponibilidad_fallback(metricas):
    disp_total = int(metricas.get("disp_total", 0))
    disp_pct = float(metricas.get("disp_pct", 0))
    disp_cumple = int(metricas.get("disp_cumple", 0))
    disp_sin_respuesta = int(metricas.get("disp_sin_respuesta", 0))
    disp_brecha_meta = float(metricas.get("disp_brecha_meta", 0))
    disp_reiteraciones = int(metricas.get("disp_reiteraciones", 0))
    disp_tickets_reiterados = int(metricas.get("disp_tickets_reiterados", 0))
    disp_reit_cecom_total = int(metricas.get("disp_reit_cecom_total", 0))
    comparativo = str(metricas.get("comparativo_disponibilidad_proveedor", "")).strip()

    if not disp_total:
        return [recomendacion_clara(
            "Base filtrada", "Sin datos", "No hay solicitudes para evaluar",
            "Los filtros activos no contienen solicitudes medibles de disponibilidad.",
            "Revisar mes, semana, cliente y zona. Si esperabas casos nuevos, ejecutar la actualización PST.",
            "accion",
        )]

    estado_sla, tono_sla, _ = estado_segun_meta(disp_pct, DISPONIBILIDAD_META_PCT, tolerancia=5)
    brecha_texto = "sobre" if disp_brecha_meta >= 0 else "bajo"
    accion_sla = (
        "Mantener control semanal y auditar una muestra de respuestas para asegurar trazabilidad."
        if tono_sla == "bien" else
        f"Cerrar primero las {disp_sin_respuesta} solicitudes sin respuesta y después ordenar los casos sobre {DISPONIBILIDAD_SLA_MIN} minutos por zona y antigüedad."
    )
    if comparativo and tono_sla != "bien":
        accion_sla += " En la vista Todo, comenzar por el ST con menor cumplimiento."

    total_friccion = max(disp_reit_cecom_total, disp_reiteraciones)
    estado_friccion = "Sin fricción" if total_friccion == 0 else "Fricción detectada"
    tono_friccion = "bien" if total_friccion == 0 else "mal" if disp_tickets_reiterados >= 3 else "accion"

    return [
        recomendacion_clara(
            "Cumplimiento SLA", estado_sla,
            f"{abs(disp_brecha_meta):.1f} pp {brecha_texto} la meta",
            f"{disp_cumple} de {disp_total} solicitudes cumplen: {disp_pct:.1f}% frente a una meta de {DISPONIBILIDAD_META_PCT}%.",
            accion_sla,
            tono_sla,
        ),
        recomendacion_clara(
            "Reiteraciones", estado_friccion,
            "La insistencia revela espera operativa" if total_friccion else "No hay insistencias en la selección",
            f"Se observan {disp_reit_cecom_total} reiteraciones CECOM y {disp_reiteraciones} reiteraciones totales en {disp_tickets_reiterados} tickets.",
            "Ordenar los tickets por cantidad de reiteraciones, asignar dueño y registrar la respuesta comprometida." if total_friccion else "Mantener la revisión diaria y tratar la primera reiteración como alerta preventiva.",
            tono_friccion,
        ),
        recomendacion_clara(
            "Solicitudes sin respuesta", "Pendientes críticos" if disp_sin_respuesta else "Todo respondido",
            f"{disp_sin_respuesta} solicitudes requieren cierre" if disp_sin_respuesta else "No quedan solicitudes abiertas",
            f"La selección contiene {disp_sin_respuesta} solicitudes sin una respuesta válida del ST.",
            "Priorizar por antigüedad, cliente crítico y zona; no presentar el KPI como cerrado mientras existan pendientes." if disp_sin_respuesta else "Conservar evidencia y revisar semanalmente una muestra de respuestas.",
            "mal" if disp_sin_respuesta else "bien",
        ),
    ]


def render_analisis_disponibilidad(metricas):
    fallback = construir_insights_disponibilidad_fallback(metricas)
    render_analisis_hoja("KPI Disponibilidad", metricas, fallback)


def render_reclamos_kpi_cards(
    reclamos_total,
    reclamos_reclamos_duros,
    reclamos_reforzamientos,
    reclamos_alta,
    reclamos_tickets,
    reclamos_clientes,
    atenciones_asignadas_reclamos,
    reclamos_ratio_incumplimiento,
    reclamos_cumplimiento_ajustado,
    reclamos_brecha_meta,
    reclamos_cliente_top,
    reclamos_cliente_top_count,
    reclamos_cliente_top_tickets,
    reclamos_proveedor_reforzado_top,
    reclamos_proveedor_reforzado_top_count,
):
    pct_foco = round(reclamos_cliente_top_count / max(reclamos_total, 1) * 100, 1) if reclamos_total else 0
    color_cumplimiento = VERDE if reclamos_cumplimiento_ajustado >= RECLAMOS_META_CUMPLIMIENTO_PCT else ROSADO
    render_kpi_card_grid([
        {"icono": "&#9888;", "titulo": "Señales operacionales", "valor": reclamos_total, "subtitulo": f"{reclamos_reclamos_duros} reclamos | {reclamos_reforzamientos} reforzamientos", "color": NARANJO if reclamos_total else VERDE},
        {"icono": "&#9776;", "titulo": "Atenciones asignadas", "valor": atenciones_asignadas_reclamos, "subtitulo": "Denominador filtrado por periodo", "color": KPI_TOTAL},
        {"icono": "&#37;", "titulo": "Ratio incumplimiento", "valor": f"{reclamos_ratio_incumplimiento:.1f}%", "subtitulo": f"{reclamos_total}/{max(atenciones_asignadas_reclamos, 0)} señales/atenciones", "color": ROSADO if reclamos_ratio_incumplimiento > RECLAMOS_META_RATIO_INCUMPLIMIENTO_PCT else VERDE, "badge": f"Meta <= {RECLAMOS_META_RATIO_INCUMPLIMIENTO_PCT:.1f}%"},
        {"icono": "&#9673;", "titulo": "Cumplimiento ajustado", "valor": f"{reclamos_cumplimiento_ajustado:.1f}%", "subtitulo": f"Meta {RECLAMOS_META_CUMPLIMIENTO_PCT}% | brecha {reclamos_brecha_meta:+.1f} pp", "color": color_cumplimiento, "progreso": reclamos_cumplimiento_ajustado},
        {"icono": "&#9881;", "titulo": "Reforzamientos", "valor": reclamos_reforzamientos, "subtitulo": f"Foco ST: {nombre_corto_leyenda(reclamos_proveedor_reforzado_top, 18)} ({reclamos_proveedor_reforzado_top_count})", "color": CELESTE if reclamos_reforzamientos else VERDE, "badge": "Refuerzo" if reclamos_reforzamientos else "OK"},
        {"icono": "&#33;", "titulo": "Cliente a revisar", "valor": nombre_corto_leyenda(reclamos_cliente_top, 18), "subtitulo": f"{reclamos_cliente_top_count} registros | {reclamos_cliente_top_tickets} tickets distintos | {pct_foco:.1f}% del total", "color": ROSADO if reclamos_cliente_top_count else VERDE, "badge": "Foco" if reclamos_cliente_top_count else "OK"},
    ])


def construir_insights_reclamos_fallback(metricas):
    reclamos_total = int(metricas.get("reclamos_total", 0))
    reclamos_duros = int(metricas.get("reclamos_reclamos_duros", max(reclamos_total, 0)))
    reforzamientos = int(metricas.get("reclamos_reforzamientos", 0))
    reclamos_alta = int(metricas.get("reclamos_alta", 0))
    reclamos_tickets = int(metricas.get("reclamos_tickets", 0))
    reclamos_clientes = int(metricas.get("reclamos_clientes", 0))
    motivo_top = str(metricas.get("reclamos_motivo_top", "Sin reclamos"))
    motivo_top_count = int(metricas.get("reclamos_motivo_top_count", 0))
    cliente_top = str(metricas.get("reclamos_cliente_top", "Sin cliente"))
    cliente_top_count = int(metricas.get("reclamos_cliente_top_count", 0))
    atenciones = int(metricas.get("atenciones_asignadas_reclamos", 0))
    ratio_incumplimiento = float(metricas.get("reclamos_ratio_incumplimiento", 0))
    cumplimiento_ajustado = float(metricas.get("reclamos_cumplimiento_ajustado", 0))
    brecha_meta = float(metricas.get("reclamos_brecha_meta", 0))
    proveedor_ref_top = str(metricas.get("reclamos_proveedor_reforzado_top", "Sin reforzar"))
    proveedor_ref_top_count = int(metricas.get("reclamos_proveedor_reforzado_top_count", 0))
    comparativo = str(metricas.get("comparativo_reclamos_proveedor", "")).strip()

    if not atenciones:
        return [recomendacion_clara(
            "Base filtrada", "Sin datos", "No hay atenciones para calcular el ratio",
            "Sin atenciones asignadas no existe un denominador válido para medir reclamos.",
            "Revisar mes, semana, cliente y zona antes de interpretar el resultado.",
            "accion",
        )]

    estado_ajuste, tono_ajuste, brecha_ajuste = estado_segun_meta(
        cumplimiento_ajustado, RECLAMOS_META_CUMPLIMIENTO_PCT, tolerancia=3
    )
    direccion = "sobre" if brecha_meta >= 0 else "bajo"
    accion_ajuste = (
        "Mantener seguimiento preventivo y comprobar que cada señal continúe depurada por ticket y causa."
        if tono_ajuste == "bien" else
        "Revisar primero los reclamos reales, validar evidencia y convertir cada causa repetida en un compromiso con dueño y fecha."
    )
    if comparativo and tono_ajuste != "bien":
        accion_ajuste += " En la vista Todo, iniciar por el ST con peor cumplimiento ajustado."

    if reforzamientos:
        foco_estado, foco_tono = "Refuerzo concentrado", "accion"
        foco_titulo = f"{proveedor_ref_top} concentra el refuerzo"
        foco_lectura = f"Registra {proveedor_ref_top_count} de {reforzamientos} reforzamientos en la selección."
        foco_accion = "Convertir cada reforzamiento en causa, responsable, fecha de cierre y evidencia verificable."
    elif cliente_top_count:
        foco_estado, foco_tono = "Cliente a revisar", "accion"
        foco_titulo = f"{cliente_top} concentra {cliente_top_count} señales"
        foco_lectura = f"El foco principal está en {cliente_top}; validar cuántos corresponden a tickets distintos antes de escalar."
        foco_accion = "Cruzar ticket, zona, fecha y causa; luego asignar la corrección al ST responsable."
    else:
        foco_estado, foco_tono = "Sin concentración", "bien"
        foco_titulo = "No existe un foco operativo dominante"
        foco_lectura = "La selección no muestra clientes ni proveedores concentrando señales."
        foco_accion = "Mantener monitoreo y evitar acciones correctivas masivas sin evidencia nueva."

    return [
        recomendacion_clara(
            "Cumplimiento ajustado", estado_ajuste,
            f"{abs(brecha_meta):.1f} pp {direccion} la meta",
            f"Hay {reclamos_total} señales sobre {atenciones} atenciones: ratio {ratio_incumplimiento:.1f}% y cumplimiento ajustado {cumplimiento_ajustado:.1f}%.",
            accion_ajuste,
            tono_ajuste,
        ),
        recomendacion_clara("Foco operativo", foco_estado, foco_titulo, foco_lectura, foco_accion, foco_tono),
        recomendacion_clara(
            "Causa dominante", "Causa identificada" if reclamos_total else "Sin señales",
            f"{motivo_top}: {motivo_top_count} registros" if reclamos_total else "No hay una causa que priorizar",
            f"La selección reúne {reclamos_duros} reclamos, {reforzamientos} reforzamientos, {reclamos_tickets} tickets y {reclamos_clientes} clientes.",
            "Comenzar por la causa más repetida, comprobar recurrencia por zona y revisar el detalle antes de exigir un plan al contratista." if reclamos_total else "Conservar trazabilidad y actualizar PST cuando corresponda.",
            "accion" if reclamos_total else "bien",
        ),
    ]


def render_analisis_reclamos(metricas):
    render_analisis_hoja("KPI Reclamos", metricas, construir_insights_reclamos_fallback(metricas))


def render_analisis_hoja(nombre_hoja, metricas, fallback):
    insights = fallback

    colores = {"bien": VERDE, "mal": ROSADO, "accion": CELESTE}
    estados_default = {"bien": "Meta cumplida", "mal": "Prioridad alta", "accion": "Requiere atención"}
    filas = []
    for indice, insight in enumerate(insights, start=1):
        tono = insight.get("tono", "accion")
        color = colores.get(tono, CELESTE)
        estado = str(insight.get("estado") or estados_default.get(tono, "Revisar"))
        lectura = str(insight.get("lectura") or insight.get("cuerpo") or "")
        accion = str(insight.get("accion") or "Revisar el detalle filtrado antes de definir responsables.")
        filas.append(
            f'<div class="recommendation-row" style="--accent:{color};">'
            f'<div class="recommendation-number">{indice:02d}</div>'
            f'<div class="recommendation-reading">'
            f'<div class="recommendation-meta"><span>{html.escape(str(insight.get("indicador", "")))}</span><b>{html.escape(estado)}</b></div>'
            f'<h4>{html.escape(str(insight.get("titulo", "")))}</h4>'
            f'<p>{html.escape(lectura)}</p>'
            f'</div>'
            f'<div class="recommendation-next"><span>Qué hacer ahora</span><p>{html.escape(accion)}</p></div>'
            f'</div>'
        )
    st.markdown(
        f'<section class="recommendation-panel">'
        f'<div class="recommendation-heading"><div><span>RECOMENDACIÓN</span><h3>Qué conviene hacer con esta lectura</h3></div>'
        f'<p>{html.escape(nombre_hoja)} · responde a los filtros activos</p></div>'
        f'<div class="recommendation-list">{"".join(filas)}</div>'
        f'</section>',
        unsafe_allow_html=True,
    )


def construir_insights_inicio_fallback(metricas):
    total_base = int(metricas.get("total", 0))
    pct_cumplimiento = float(metricas.get("pct", 0))
    finalizadas_primera = int(metricas.get("finalizadas_primera_visita", 0))
    pct_primera = float(metricas.get("pct_primera_visita", 0))
    revisitas_total = int(metricas.get("revisitas", 0))
    pct_revisitas_valor = float(metricas.get("pct_revisitas", 0))
    no_finalizadas_total = int(metricas.get("no_finalizadas", 0))
    comparativo = str(metricas.get("comparativo_inicio_proveedor", "")).strip()

    if not total_base:
        return [recomendacion_clara(
            "Base filtrada", "Sin datos", "No hay atenciones para evaluar",
            "Los filtros activos dejaron la vista sin atenciones WFM.",
            "Revisar zona, técnico, mes y semana. Si esperabas nuevos datos, ejecutar la actualización WFM.",
            "accion",
        )]

    estado_inicio, tono_inicio, brecha_inicio = estado_segun_meta(pct_cumplimiento, 80, tolerancia=5)
    estado_primera, tono_primera, brecha_primera = estado_segun_meta(pct_primera, 70, tolerancia=5)
    estado_revisita, tono_revisita, brecha_revisita = estado_segun_meta(
        pct_revisitas_valor, 5, tolerancia=2.5, menor_es_mejor=True
    )

    accion_inicio = (
        "Mantener el control semanal y auditar una muestra de inicios para sostener el resultado."
        if tono_inicio == "bien" else
        "Comenzar por la zona con menor cumplimiento, revisar sus semanas críticas y después bajar a los técnicos de esa zona."
    )
    if comparativo and tono_inicio != "bien":
        accion_inicio += " En la vista Todo, comenzar por el ST con menor cumplimiento."

    return [
        recomendacion_clara(
            "Puntualidad", estado_inicio,
            f"Inicio {abs(brecha_inicio):.1f} pp {'sobre' if brecha_inicio >= 0 else 'bajo'} la meta",
            f"{pct_cumplimiento:.1f}% de {total_base} atenciones comenzó dentro de la tolerancia de 15 minutos; la meta es 80%.",
            accion_inicio,
            tono_inicio,
        ),
        recomendacion_clara(
            "Cierre en primera visita", estado_primera,
            f"{pct_primera:.1f}% cerró sin una visita adicional",
            f"Se cerraron {finalizadas_primera} atenciones en primera visita y quedaron {no_finalizadas_total} no finalizadas. Referencia operativa: 70%.",
            "Revisar en las no finalizadas el contacto previo, disponibilidad de repuesto y motivo de no cierre." if tono_primera != "bien" else "Mantener trazabilidad del cierre y revisar semanalmente los casos no finalizados.",
            tono_primera,
        ),
        recomendacion_clara(
            "Revisitas", estado_revisita,
            f"{pct_revisitas_valor:.1f}% de revisitas frente a referencia máxima de 5%",
            f"La selección contiene {revisitas_total} tickets con visita adicional sobre {total_base} atenciones.",
            "Revisar en la zona afectada si se repiten problemas de repuesto, contacto previo, diagnóstico o cierre; después identificar los técnicos recurrentes." if tono_revisita != "bien" else "Mantener el control por zona y verificar que el porcentaje no aumente en semanas siguientes.",
            tono_revisita,
        ),
    ]


def render_analisis_inicio(metricas):
    render_analisis_hoja("KPI Inicio Actividad", metricas, construir_insights_inicio_fallback(metricas))


def construir_insights_epa_fallback(metricas):
    total_atenciones = int(metricas.get("epa_total_atenciones", 0))
    respondidas = int(metricas.get("epa_total_respuestas", 0))
    pendientes = int(metricas.get("epa_pendientes", 0))
    satisfaccion = float(metricas.get("epa_satisfaccion", 0))
    promedio = float(metricas.get("epa_promedio", 0))
    recomendacion = float(metricas.get("epa_recomendacion", 0))
    tasa_respuesta = round(respondidas / max(total_atenciones, 1) * 100, 1) if total_atenciones else 0

    if not total_atenciones:
        return [recomendacion_clara(
            "Base EPA", "Sin encuestas", "No hay encuestas en la selección",
            "La vista no contiene invitaciones EPA para los filtros activos.",
            "Validar la carga EPA y ampliar mes, semana o cliente antes de evaluar desempeño.",
            "accion",
        )]

    estado_sat, tono_sat, brecha_sat = estado_segun_meta(satisfaccion, 90, tolerancia=5)
    estado_resp, tono_resp, brecha_resp = estado_segun_meta(tasa_respuesta, 70, tolerancia=10)
    estado_q5, tono_q5, brecha_q5 = estado_segun_meta(recomendacion, 4, tolerancia=0.3)

    return [
        recomendacion_clara(
            "Satisfacción", estado_sat,
            f"{satisfaccion:.1f}% de usuarios satisfechos",
            f"Respondieron {respondidas} usuarios; el promedio general es {promedio:.1f}/5 y la brecha frente a la meta de 90% es {brecha_sat:+.1f} pp.",
            "Leer respuestas con promedio bajo 4, agrupar comentarios por causa y reforzar la zona con menor resultado." if tono_sat != "bien" else "Mantener el estándar y revisar los comentarios negativos aunque el KPI esté en meta.",
            tono_sat,
        ),
        recomendacion_clara(
            "Cobertura de respuesta", estado_resp,
            f"Respondió {tasa_respuesta:.1f}% de los usuarios invitados",
            f"Hay {respondidas} respuestas de {total_atenciones} invitaciones y {pendientes} pendientes. Referencia de cobertura: 70%.",
            f"Recuperar los {pendientes} pendientes con contacto post atención el mismo día y seguimiento semanal por zona." if pendientes else "Conservar el proceso de contacto y vigilar que la cobertura no baje al cambiar de semana.",
            tono_resp,
        ),
        recomendacion_clara(
            "Pregunta de recomendación", estado_q5,
            f"Q5 promedia {recomendacion:.1f}/5",
            "Q5 muestra qué tan dispuesto está el usuario a recomendar el servicio; la referencia es 4,0 o más.",
            "Cruzar Q5 bajo 4 con comentarios y zona para aplicar coaching puntual." if tono_q5 != "bien" else "Usar los comentarios positivos como práctica replicable y revisar cualquier Q5 bajo 4.",
            tono_q5,
        ),
    ]


def render_analisis_epa(metricas):
    render_analisis_hoja("KPI EPA Satisfacción", metricas, construir_insights_epa_fallback(metricas))


def preparar_dispersion_epa(df_base, dimension):
    columnas_necesarias = {dimension, "promedio", "_fecha_epa"}
    if df_base.empty or not columnas_necesarias.issubset(df_base.columns):
        return pd.DataFrame()

    base = df_base[list(columnas_necesarias)].copy()
    base["promedio"] = pd.to_numeric(base["promedio"], errors="coerce")
    base["_fecha_epa"] = pd.to_datetime(base["_fecha_epa"], errors="coerce")
    base[dimension] = (
        base[dimension]
        .fillna("Sin dato")
        .astype(str)
        .str.strip()
        .replace({"": "Sin dato"})
    )
    base = base.dropna(subset=["_fecha_epa", "promedio"])

    if base.empty:
        return pd.DataFrame()

    base["_periodo_orden"] = base["_fecha_epa"].dt.to_period("M").dt.to_timestamp()
    base["_periodo_label"] = base["_periodo_orden"].map(
        lambda fecha: f"{MESES_CORTOS.get(MESES[fecha.month - 1], fecha.strftime('%m'))} {fecha.year}"
    )
    resumen = (
        base.groupby(["_periodo_orden", "_periodo_label", dimension], as_index=False)
        .agg(promedio=("promedio", "mean"), respuestas=("promedio", "size"))
        .sort_values(["_periodo_orden", "promedio"], ascending=[True, False])
    )
    resumen["promedio"] = resumen["promedio"].round(2)
    resumen["brecha_minima"] = (resumen["promedio"] - 4).round(2)
    return resumen


def nombre_corto_leyenda(valor, largo=30):
    texto = str(valor)
    return texto if len(texto) <= largo else texto[:largo - 3] + "..."


def grafico_dispersion_epa(resumen, dimension, titulo):
    fig_disp = go.Figure()
    categorias_periodo = []
    tickvals_periodo = None

    fig_disp.add_hrect(
        y0=4,
        y1=5,
        fillcolor=rgba(VERDE, 0.10),
        line_width=0,
        layer="below"
    )
    fig_disp.add_hline(
        y=4,
        line_dash="dot",
        line_width=2.6,
        line_color=ROSADO,
        annotation_text="M\u00ednimo 4",
        annotation_position="top left",
        annotation_font=dict(size=12, color=ROSADO, family="Segoe UI Black")
    )
    fig_disp.add_hline(
        y=5,
        line_width=1.8,
        line_color=VERDE,
        annotation_text="Objetivo 5",
        annotation_position="bottom right",
        annotation_font=dict(size=12, color=VERDE, family="Segoe UI Black")
    )

    if len(resumen):
        colores_neon = [CELESTE, VERDE, ROSADO, AZUL_CLARO, NARANJO, "#8FA7FF", "#F7D154", "#B96CFF"]
        max_respuestas = max(int(resumen["respuestas"].max()), 1)
        periodo_orden = resumen[["_periodo_orden", "_periodo_label"]].drop_duplicates().sort_values("_periodo_orden")
        categorias_periodo = periodo_orden["_periodo_label"].tolist()
        if categorias_periodo:
            max_ticks = 10
            if len(categorias_periodo) > max_ticks:
                paso = max(1, -(-len(categorias_periodo) // max_ticks))
                tickvals_periodo = [
                    etiqueta
                    for indice, etiqueta in enumerate(categorias_periodo)
                    if indice % paso == 0 or indice == len(categorias_periodo) - 1
                ]
            else:
                tickvals_periodo = categorias_periodo
        for idx, nombre in enumerate(resumen[dimension].drop_duplicates()):
            datos = resumen[resumen[dimension].eq(nombre)].copy()
            color = colores_neon[idx % len(colores_neon)]
            tamanos = 13 + (datos["respuestas"] / max_respuestas * 18)
            borde = [VERDE if valor >= 4 else ROSADO for valor in datos["promedio"]]
            customdata = datos[[dimension, "respuestas", "brecha_minima"]].to_numpy()

            fig_disp.add_trace(
                go.Scatter(
                    x=datos["_periodo_label"],
                    y=datos["promedio"],
                    mode="markers",
                    marker=dict(
                        size=tamanos + 18,
                        color=rgba(color, 0.20),
                        line=dict(color=rgba(color, 0.34), width=1),
                    ),
                    hoverinfo="skip",
                    showlegend=False,
                )
            )
            fig_disp.add_trace(
                go.Scatter(
                    x=datos["_periodo_label"],
                    y=datos["promedio"],
                    mode="markers",
                    name=nombre_corto_leyenda(nombre),
                    marker=dict(
                        size=tamanos,
                        color=rgba(color, 0.86),
                        line=dict(color=borde, width=2.3),
                        symbol="circle",
                    ),
                    customdata=customdata,
                    hovertemplate=(
                        "<b>%{customdata[0]}</b><br>"
                        "Periodo: %{x}<br>"
                        "Promedio EPA: <b>%{y:.2f}</b><br>"
                        "Respuestas: <b>%{customdata[1]}</b><br>"
                        "Brecha vs 4: <b>%{customdata[2]:+.2f}</b>"
                        "<extra></extra>"
                    ),
                    showlegend=True,
                )
            )

    fig_disp.update_layout(
        title=dict(
            text=f"<b>{titulo}</b><br><span style='font-size:12px;color:#BDEFFF'>Meta 90%: promedios con nota 4 o superior; objetivo ideal 5</span>",
            x=0.02,
            xanchor="left",
            font=dict(size=17, color="#DDFBFF", family="Segoe UI Semibold")
        ),
        height=390,
        margin=dict(l=48, r=190, t=86, b=48),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(6,18,34,0.74)",
        legend=dict(
            title=dict(text=dimension.capitalize(), font=dict(size=12, color="#DDFBFF", family="Segoe UI Black")),
            orientation="v",
            x=1.02,
            xanchor="left",
            y=0.98,
            yanchor="top",
            bgcolor="rgba(6,18,34,0.82)",
            bordercolor="rgba(46,203,242,0.38)",
            borderwidth=1,
            font=dict(size=11, color="#EAFBFF", family="Segoe UI Semibold"),
        ),
        hoverlabel=dict(
            bgcolor="rgba(6,18,34,0.96)",
            bordercolor="rgba(46,203,242,0.40)",
            font=dict(size=12, family="Segoe UI", color="#EAFBFF")
        ),
    )
    fig_disp.update_xaxes(
        title=None,
        type="category",
        categoryorder="array",
        categoryarray=categorias_periodo if categorias_periodo else None,
        tickmode="array" if tickvals_periodo else "auto",
        tickvals=tickvals_periodo,
        tickangle=-18,
        showgrid=True,
        gridcolor="rgba(143,239,255,0.12)",
        zeroline=False,
        automargin=True,
        tickfont=dict(size=12, color="#BDEFFF", family="Segoe UI Semibold")
    )
    fig_disp.update_yaxes(
        title=None,
        range=[1, 5.15],
        dtick=0.5,
        showgrid=True,
        gridcolor="rgba(143,239,255,0.14)",
        zeroline=False,
        tickfont=dict(size=12, color="#BDEFFF", family="Segoe UI Semibold")
    )
    return fig_disp


def etiqueta_mes_fecha(fecha):
    if pd.isna(fecha):
        return "Sin fecha"
    return f"{MESES_CORTOS.get(MESES[int(fecha.month) - 1], fecha.strftime('%m'))} {int(fecha.year)}"


def preparar_resumen_mensual_disponibilidad(df_base):
    if df_base.empty or "fecha_solicitud" not in df_base.columns:
        return pd.DataFrame()

    base = df_base.copy()
    base["fecha_solicitud"] = pd.to_datetime(base["fecha_solicitud"], errors="coerce")
    base = base.dropna(subset=["fecha_solicitud"])
    if base.empty:
        return pd.DataFrame()

    base["cumple_kpi"] = base["cumple_kpi"].fillna(False).astype(bool)
    base["_sin_respuesta"] = base["fecha_respuesta"].isna() if "fecha_respuesta" in base.columns else False
    base["_reiteraciones"] = calcular_reiteraciones_total_operacional(base)
    base["_periodo_orden"] = base["fecha_solicitud"].dt.to_period("M").dt.to_timestamp()
    base["_periodo_label"] = base["_periodo_orden"].map(etiqueta_mes_fecha)
    resumen = (
        base.groupby(["_periodo_orden", "_periodo_label"], as_index=False)
        .agg(
            solicitudes=("cumple_kpi", "size"),
            cumple=("cumple_kpi", "sum"),
            sin_respuesta=("_sin_respuesta", "sum"),
            reiteraciones=("_reiteraciones", "sum"),
            promedio_min=("minutos_habiles", "mean"),
        )
        .sort_values("_periodo_orden")
    )
    resumen["no_cumple"] = resumen["solicitudes"] - resumen["cumple"]
    resumen["cumplimiento_pct"] = (resumen["cumple"] / resumen["solicitudes"].clip(lower=1) * 100).round(1)
    resumen["promedio_min"] = resumen["promedio_min"].round(1)
    return resumen


def grafico_disponibilidad_mensual(resumen):
    fig_disp = go.Figure()
    categorias = resumen["_periodo_label"].tolist() if len(resumen) else []

    if len(resumen):
        resumen = resumen.copy()
        resumen["promedio_min"] = resumen["promedio_min"].fillna(0)
        max_solicitudes = max(float(resumen["solicitudes"].max()), 1.0)
        resumen["_marker_size"] = 16 + (resumen["solicitudes"] / max_solicitudes * 18)
        colores = [VERDE if valor >= DISPONIBILIDAD_META_PCT else ROSADO for valor in resumen["cumplimiento_pct"]]
        fig_disp.add_trace(go.Scatter(
            x=resumen["_periodo_label"],
            y=resumen["cumplimiento_pct"],
            mode="lines+markers+text",
            name="Cumplimiento KPI",
            fill="tozeroy",
            fillcolor=rgba(CELESTE, 0.13),
            line=dict(color=CELESTE, width=4.2, shape="spline", smoothing=0.7),
            marker=dict(
                size=resumen["_marker_size"],
                color=colores,
                line=dict(color="#EAFBFF", width=2.2),
                opacity=0.92,
            ),
            text=[f"{v:.1f}%" for v in resumen["cumplimiento_pct"]],
            textposition="top center",
            textfont=dict(size=12, color=CELESTE, family="Segoe UI Black"),
            customdata=resumen[["solicitudes", "cumple", "no_cumple", "sin_respuesta", "reiteraciones", "promedio_min"]].to_numpy(),
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Cumplimiento KPI: <b>%{y:.1f}%</b><br>"
                "Solicitudes: <b>%{customdata[0]}</b><br>"
                "Cumplen KPI: <b>%{customdata[1]}</b><br>"
                "No cumplen: <b>%{customdata[2]}</b><br>"
                "Sin respuesta: <b>%{customdata[3]}</b><br>"
                "Reiteraciones: <b>%{customdata[4]}</b><br>"
                "Promedio habiles: <b>%{customdata[5]:.1f} min</b>"
                "<extra></extra>"
            ),
        ))
        fig_disp.add_trace(go.Scatter(
            x=resumen["_periodo_label"],
            y=[DISPONIBILIDAD_META_PCT] * len(resumen),
            mode="lines",
            name=f"Meta KPI {DISPONIBILIDAD_META_PCT}%",
            line=dict(color=VERDE, width=2.5, dash="dot"),
            hovertemplate=f"<b>%{{x}}</b><br>Meta KPI: <b>{DISPONIBILIDAD_META_PCT}%</b><extra></extra>",
        ))

    fig_disp.add_annotation(
        xref="paper",
        x=1,
        yref="y",
        y=DISPONIBILIDAD_META_PCT,
        xanchor="right",
        yanchor="bottom",
        text=f"<b>Meta {DISPONIBILIDAD_META_PCT}% <= {DISPONIBILIDAD_SLA_MIN} min habiles</b>",
        showarrow=False,
        font=dict(size=12, color=VERDE, family="Segoe UI Black"),
        bgcolor="rgba(6,18,34,0.82)",
        bordercolor=rgba(VERDE, 0.42),
        borderwidth=1,
        borderpad=4,
    )
    fig_disp.update_layout(
        title=dict(
            text=f"<b>Cumplimiento mensual de disponibilidad {SERVICIO_TITULO}</b><br><span style='font-size:12px;color:#BDEFFF'>Solicitudes CECOM respondidas por {SERVICIO_TITULO} dentro de {DISPONIBILIDAD_SLA_MIN} minutos habiles</span>",
            x=0.02,
            xanchor="left",
            font=dict(size=18, color="#DDFBFF", family="Segoe UI Semibold")
        ),
        height=390,
        margin=dict(l=54, r=70, t=88, b=52),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(6,18,34,0.74)",
        legend=dict(
            orientation="h",
            x=0.5,
            xanchor="center",
            y=1.04,
            yanchor="bottom",
            bgcolor="rgba(6,18,34,0.82)",
            bordercolor="rgba(46,203,242,0.38)",
            borderwidth=1,
            font=dict(size=12, color="#EAFBFF", family="Segoe UI Semibold"),
        ),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="rgba(6,18,34,0.96)", bordercolor="rgba(46,203,242,0.40)", font=dict(size=12, family="Segoe UI", color="#EAFBFF")),
        transition=dict(duration=0),
    )
    fig_disp.update_xaxes(
        title=None,
        type="category",
        categoryorder="array",
        categoryarray=categorias,
        tickangle=-14,
        showgrid=False,
        zeroline=False,
        automargin=True,
        tickfont=dict(size=12, color="#BDEFFF", family="Segoe UI Semibold")
    )
    fig_disp.update_yaxes(
        title=dict(text="% cumplimiento KPI", font=dict(size=12, color="#BDEFFF", family="Segoe UI Semibold")),
        range=[0, 105],
        ticksuffix="%",
        showgrid=True,
        gridcolor="rgba(143,239,255,0.14)",
        zeroline=False,
        tickfont=dict(size=12, color="#BDEFFF", family="Segoe UI Semibold")
    )
    return fig_disp


def preparar_resumen_mensual_disponibilidad_servicio(df_base):
    if df_base.empty or "fecha_solicitud" not in df_base.columns or "servicio_tecnico" not in df_base.columns:
        return pd.DataFrame()

    base = df_base.copy()
    base["fecha_solicitud"] = pd.to_datetime(base["fecha_solicitud"], errors="coerce")
    base = base.dropna(subset=["fecha_solicitud"])
    if base.empty:
        return pd.DataFrame()

    base["servicio_tecnico"] = base["servicio_tecnico"].fillna("Sin dato").astype(str).str.strip().replace({"": "Sin dato"})
    base["cumple_kpi"] = base["cumple_kpi"].fillna(False).astype(bool)
    base["_periodo_orden"] = base["fecha_solicitud"].dt.to_period("M").dt.to_timestamp()
    base["_periodo_label"] = base["_periodo_orden"].map(etiqueta_mes_fecha)
    resumen = (
        base.groupby(["_periodo_orden", "_periodo_label", "servicio_tecnico"], as_index=False)
        .agg(
            solicitudes=("cumple_kpi", "size"),
            cumple=("cumple_kpi", "sum"),
        )
        .sort_values(["_periodo_orden", "servicio_tecnico"])
    )
    resumen["no_cumple"] = resumen["solicitudes"] - resumen["cumple"]
    resumen["cumplimiento_pct"] = (resumen["cumple"] / resumen["solicitudes"].clip(lower=1) * 100).round(1)
    return resumen


def grafico_disponibilidad_mensual_servicio(resumen):
    if resumen.empty:
        return figura_disponibilidad_vacia("Disponibilidad comparativa", "No hay solicitudes para comparar por contratista")

    fig = go.Figure()
    categorias = (
        resumen[["_periodo_orden", "_periodo_label"]]
        .drop_duplicates()
        .sort_values("_periodo_orden")["_periodo_label"]
        .tolist()
    )
    colores_servicio = {"IBM": CELESTE, "SAO": ROSADO, "ECC": NARANJO}
    for servicio, datos in resumen.groupby("servicio_tecnico", dropna=False):
        datos = datos.sort_values("_periodo_orden")
        color = colores_servicio.get(str(servicio).upper(), "#8FA7FF")
        fig.add_trace(go.Scatter(
            x=datos["_periodo_label"],
            y=datos["cumplimiento_pct"],
            mode="lines+markers+text",
            name=str(servicio),
            line=dict(color=color, width=3.8, shape="spline", smoothing=0.65),
            marker=dict(size=13, color=color, line=dict(color="#EAFBFF", width=1.8)),
            text=[f"{v:.0f}%" for v in datos["cumplimiento_pct"]],
            textposition="top center",
            textfont=dict(size=11, color=color, family="Segoe UI Black"),
            customdata=datos[["solicitudes", "cumple", "no_cumple"]].to_numpy(),
            hovertemplate=(
                "%{fullData.name}<br><b>%{x}</b><br>"
                "Cumplimiento: <b>%{y:.1f}%</b><br>"
                "Solicitudes: <b>%{customdata[0]}</b><br>"
                "Cumplen: <b>%{customdata[1]}</b><br>"
                "No cumplen: <b>%{customdata[2]}</b><extra></extra>"
            ),
        ))
    fig.add_hline(
        y=DISPONIBILIDAD_META_PCT,
        line_dash="dot",
        line_width=2.6,
        line_color=VERDE,
        annotation_text=f"Meta {DISPONIBILIDAD_META_PCT}%",
        annotation_position="top left",
        annotation_font=dict(size=12, color=VERDE, family="Segoe UI Black"),
    )
    fig.update_layout(
        title=dict(
            text=f"<b>Disponibilidad comparativa por contratista</b><br><span style='font-size:12px;color:#BDEFFF'>Vista Todo: cada linea mide su propio cumplimiento SLA; ECC no aplica por operar directo con centro de comando</span>",
            x=0.02,
            xanchor="left",
            font=dict(size=18, color="#DDFBFF", family="Segoe UI Semibold"),
        ),
        height=400,
        margin=dict(l=54, r=78, t=92, b=54),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(6,18,34,0.74)",
        legend=dict(
            orientation="h",
            x=0.5,
            xanchor="center",
            y=1.04,
            yanchor="bottom",
            bgcolor="rgba(6,18,34,0.82)",
            bordercolor="rgba(46,203,242,0.38)",
            borderwidth=1,
            font=dict(size=12, color="#EAFBFF", family="Segoe UI Semibold"),
        ),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="rgba(6,18,34,0.96)", bordercolor="rgba(46,203,242,0.40)", font=dict(size=12, family="Segoe UI", color="#EAFBFF")),
        transition=dict(duration=0),
    )
    fig.update_xaxes(
        title=None,
        type="category",
        categoryorder="array",
        categoryarray=categorias,
        tickangle=-14,
        showgrid=False,
        zeroline=False,
        automargin=True,
        tickfont=dict(size=12, color="#BDEFFF", family="Segoe UI Semibold"),
    )
    fig.update_yaxes(
        title=dict(text="% cumplimiento KPI", font=dict(size=12, color="#BDEFFF", family="Segoe UI Semibold")),
        range=[0, 105],
        ticksuffix="%",
        showgrid=True,
        gridcolor="rgba(143,239,255,0.14)",
        zeroline=False,
        tickfont=dict(size=12, color="#BDEFFF", family="Segoe UI Semibold"),
    )
    return fig


def grafico_disponibilidad_servicio(df_base):
    if df_base.empty or "servicio_tecnico" not in df_base.columns or "cumple_kpi" not in df_base.columns:
        return figura_disponibilidad_vacia("Comparativo por servicio tecnico")

    base = df_base.copy()
    base["servicio_tecnico"] = base["servicio_tecnico"].fillna("Sin dato").astype(str).str.strip().replace({"": "Sin dato"})
    base["_cumple_bool"] = base["cumple_kpi"].fillna(False).astype(bool)
    if "fecha_respuesta" in base.columns:
        fecha_respuesta = pd.to_datetime(base["fecha_respuesta"], errors="coerce")
    else:
        fecha_respuesta = pd.Series(pd.NaT, index=base.index)

    resumen = (
        base.groupby("servicio_tecnico", dropna=False)
        .agg(
            solicitudes=("servicio_tecnico", "size"),
            cumple=("_cumple_bool", "sum"),
            sin_respuesta=("servicio_tecnico", lambda s: int(fecha_respuesta.loc[s.index].isna().sum())),
        )
        .reset_index()
    )
    if resumen.empty:
        return figura_disponibilidad_vacia("Comparativo por servicio tecnico")

    resumen["cumplimiento_pct"] = (resumen["cumple"] / resumen["solicitudes"].replace(0, pd.NA) * 100).fillna(0)
    resumen["fuera_sla"] = resumen["solicitudes"] - resumen["cumple"]
    resumen = resumen.sort_values(["cumplimiento_pct", "solicitudes"], ascending=[True, False])
    colores = [VERDE if pct >= DISPONIBILIDAD_META_PCT else ROSADO for pct in resumen["cumplimiento_pct"]]

    fig_servicio = go.Figure(go.Bar(
        x=resumen["cumplimiento_pct"],
        y=resumen["servicio_tecnico"],
        orientation="h",
        marker=dict(color=colores, line=dict(color="rgba(255,255,255,.45)", width=1)),
        text=[
            f"{pct:.1f}% | {int(total)} sol. | {int(fuera)} fuera SLA"
            for pct, total, fuera in zip(resumen["cumplimiento_pct"], resumen["solicitudes"], resumen["fuera_sla"])
        ],
        textposition="outside",
        cliponaxis=False,
        customdata=resumen[["solicitudes", "cumple", "fuera_sla", "sin_respuesta"]].to_numpy(),
        hovertemplate=(
            "%{y}<br>Cumplimiento: <b>%{x:.1f}%</b><br>"
            "Solicitudes: <b>%{customdata[0]}</b><br>"
            "Cumplen: <b>%{customdata[1]}</b><br>"
            "Fuera SLA: <b>%{customdata[2]}</b><br>"
            "Sin respuesta: <b>%{customdata[3]}</b><extra></extra>"
        ),
    ))
    fig_servicio.add_shape(
        type="line",
        x0=DISPONIBILIDAD_META_PCT,
        x1=DISPONIBILIDAD_META_PCT,
        y0=-0.5,
        y1=max(len(resumen) - 0.5, 0.5),
        line=dict(color=VERDE, width=2, dash="dot"),
    )
    fig_servicio.add_annotation(
        x=DISPONIBILIDAD_META_PCT,
        y=max(len(resumen) - 0.5, 0.5),
        text=f"Meta {DISPONIBILIDAD_META_PCT}%",
        showarrow=False,
        xanchor="left",
        yanchor="bottom",
        font=dict(size=11, color=VERDE, family="Segoe UI Semibold"),
    )
    fig_servicio.update_layout(
        template="plotly_dark",
        height=280,
        margin=dict(l=78, r=120, t=80, b=44),
        paper_bgcolor="rgba(2,8,23,0)",
        plot_bgcolor="rgba(2,8,23,.34)",
        title=dict(
            text="<b>Comparativo de disponibilidad por contratista</b><br><span style='font-size:12px;color:#BDEFFF'>Visible al seleccionar Todo: quien responde mejor y quien concentra fuera de SLA</span>",
            font=dict(size=18, color="#EAFBFF", family="Segoe UI Semibold"),
            x=0.02,
        ),
        xaxis=dict(
            title=dict(text="% cumplimiento KPI", font=dict(size=12, color="#BDEFFF")),
            range=[0, max(100, float(resumen["cumplimiento_pct"].max()) + 14)],
            ticksuffix="%",
            gridcolor="rgba(189,239,255,.12)",
            zeroline=False,
            fixedrange=True,
        ),
        yaxis=dict(title=None, fixedrange=True),
        showlegend=False,
    )
    return fig_servicio


def grafico_disponibilidad_dimension(df_base, dimension, titulo):
    if df_base.empty or dimension not in df_base.columns:
        return go.Figure()

    base = df_base.copy()
    base[dimension] = base[dimension].fillna("Sin dato").astype(str).str.strip().replace({"": "Sin dato"})
    base["cumple_kpi"] = base["cumple_kpi"].fillna(False).astype(bool)
    resumen = (
        base.groupby(dimension, dropna=False)
        .agg(
            solicitudes=("cumple_kpi", "size"),
            cumple=("cumple_kpi", "sum"),
            promedio_min=("minutos_habiles", "mean"),
        )
        .reset_index()
    )
    resumen["cumplimiento_pct"] = (resumen["cumple"] / resumen["solicitudes"].clip(lower=1) * 100).round(1)
    resumen["no_cumple"] = resumen["solicitudes"] - resumen["cumple"]
    resumen["promedio_min"] = resumen["promedio_min"].fillna(0).round(1)
    resumen = resumen.sort_values(["cumplimiento_pct", "solicitudes"], ascending=[True, False]).head(10)
    resumen = resumen.sort_values("cumplimiento_pct", ascending=True)
    colores = [VERDE if valor >= DISPONIBILIDAD_META_PCT else ROSADO for valor in resumen["cumplimiento_pct"]]
    max_solicitudes = max(float(resumen["solicitudes"].max()), 1.0)
    marker_sizes = 16 + (resumen["solicitudes"] / max_solicitudes * 22)

    fig_dim = go.Figure(go.Scatter(
        x=resumen["cumplimiento_pct"],
        y=resumen[dimension].map(lambda valor: nombre_corto_leyenda(valor, 34)),
        mode="markers+text",
        marker=dict(
            size=marker_sizes,
            color=[rgba(color, 0.86) for color in colores],
            line=dict(color=colores, width=2.2),
            symbol="circle",
            opacity=0.94,
        ),
        text=[f"{pct:.1f}% | {int(total)} sol." for pct, total in zip(resumen["cumplimiento_pct"], resumen["solicitudes"])],
        textposition="middle right",
        textfont=dict(size=11, color="#EAFBFF", family="Segoe UI Semibold"),
        customdata=resumen[["solicitudes", "cumple", "no_cumple", "promedio_min"]].to_numpy(),
        hovertemplate=(
            "%{y}<br>"
            "Cumplimiento KPI: <b>%{x:.1f}%</b><br>"
            "Solicitudes: <b>%{customdata[0]}</b><br>"
            "Cumplen KPI: <b>%{customdata[1]}</b><br>"
            "No cumplen: <b>%{customdata[2]}</b><br>"
            "Promedio habiles: <b>%{customdata[3]:.1f} min</b>"
            "<extra></extra>"
        ),
        showlegend=False,
    ))
    fig_dim.add_vline(x=DISPONIBILIDAD_META_PCT, line=dict(color=VERDE, width=2.2, dash="dot"))
    fig_dim.update_layout(
        title=dict(
            text=f"<b>{titulo}</b><br><span style='font-size:12px;color:#BDEFFF'>Top critico filtrado por menor cumplimiento | meta {DISPONIBILIDAD_META_PCT}%</span>",
            x=0.02,
            xanchor="left",
            font=dict(size=17, color="#DDFBFF", family="Segoe UI Semibold")
        ),
        height=340,
        margin=dict(l=158, r=52, t=82, b=42),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(6,18,34,0.74)",
        hoverlabel=dict(bgcolor="rgba(6,18,34,0.96)", bordercolor="rgba(46,203,242,0.40)", font=dict(size=12, family="Segoe UI", color="#EAFBFF")),
    )
    fig_dim.update_xaxes(
        title=None,
        range=[0, 110],
        ticksuffix="%",
        showgrid=True,
        gridcolor="rgba(143,239,255,0.14)",
        zeroline=False,
        tickfont=dict(size=12, color="#BDEFFF", family="Segoe UI Semibold")
    )
    fig_dim.update_yaxes(
        title=None,
        automargin=True,
        tickfont=dict(size=11, color="#EAFBFF", family="Segoe UI Semibold")
    )
    return fig_dim


def grafico_disponibilidad_region_operacional(df_base):
    if df_base.empty or not {"region", "cumple_kpi"}.issubset(df_base.columns):
        return figura_disponibilidad_vacia("Cumplimiento por region operacional")

    orden_regiones = ["Region de Tarapaca", "Region de Antofagasta"]
    base = df_base.copy()
    base["region"] = base["region"].fillna("").astype(str).str.strip()
    if SERVICIO_ACTUAL == "IBM":
        base = base.loc[base["region"].isin(orden_regiones)].copy()
    else:
        base = base.loc[base["region"].ne("") & base["region"].ne("Sin zona")].copy()
    if base.empty:
        return figura_disponibilidad_vacia("Cumplimiento por region operacional")

    base["_cumple"] = base["cumple_kpi"].fillna(False).astype(bool)
    base["_sin_respuesta"] = base["fecha_respuesta"].isna() if "fecha_respuesta" in base.columns else False
    base["_reiteraciones"] = calcular_reiteraciones_total_operacional(base)

    resumen = (
        base.groupby("region", dropna=False)
        .agg(
            solicitudes=("_cumple", "size"),
            cumple=("_cumple", "sum"),
            sin_respuesta=("_sin_respuesta", "sum"),
            reiteraciones=("_reiteraciones", "sum"),
        )
        .reset_index()
    )
    resumen["no_cumple"] = resumen["solicitudes"] - resumen["cumple"]
    resumen["cumplimiento_pct"] = (resumen["cumple"] / resumen["solicitudes"].clip(lower=1) * 100).round(1)
    resumen["brecha_meta"] = (resumen["cumplimiento_pct"] - DISPONIBILIDAD_META_PCT).round(1)
    if SERVICIO_ACTUAL == "IBM":
        regiones_presentes = [region for region in orden_regiones if region in set(resumen["region"])]
        resumen = resumen.set_index("region").loc[regiones_presentes].reset_index()
    else:
        resumen = resumen.sort_values(["cumplimiento_pct", "solicitudes"], ascending=[True, False]).head(10)

    max_total = max(float(resumen["solicitudes"].max()), 1.0)
    etiqueta_ratio = [
        f"{pct:.1f}% KPI<br>{int(total)} sol."
        for pct, total in zip(resumen["cumplimiento_pct"], resumen["solicitudes"])
    ]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Cumplen",
        x=resumen["region"],
        y=resumen["cumple"],
        marker=dict(color=rgba(VERDE, 0.82), line=dict(color=VERDE, width=1.6)),
        cliponaxis=False,
        customdata=resumen[["solicitudes", "cumplimiento_pct", "sin_respuesta", "reiteraciones", "brecha_meta"]].to_numpy(),
        hovertemplate=(
            "%{x}<br>"
            "Cumplen: <b>%{y}</b><br>"
            "Solicitudes: <b>%{customdata[0]}</b><br>"
            "Cumplimiento: <b>%{customdata[1]:.1f}%</b><br>"
            "Sin respuesta: <b>%{customdata[2]}</b><br>"
            "Reiteraciones: <b>%{customdata[3]}</b><br>"
            "Brecha meta: <b>%{customdata[4]:+.1f} pp</b>"
            "<extra></extra>"
        ),
    ))
    fig.add_trace(go.Bar(
        name="No cumplen",
        x=resumen["region"],
        y=resumen["no_cumple"],
        marker=dict(color=rgba(ROSADO, 0.82), line=dict(color=ROSADO, width=1.6)),
        cliponaxis=False,
        customdata=resumen[["solicitudes", "cumplimiento_pct", "sin_respuesta", "reiteraciones", "brecha_meta"]].to_numpy(),
        hovertemplate=(
            "%{x}<br>"
            "No cumplen: <b>%{y}</b><br>"
            "Solicitudes: <b>%{customdata[0]}</b><br>"
            "Cumplimiento: <b>%{customdata[1]:.1f}%</b><br>"
            "Sin respuesta: <b>%{customdata[2]}</b><br>"
            "Reiteraciones: <b>%{customdata[3]}</b><br>"
            "Brecha meta: <b>%{customdata[4]:+.1f} pp</b>"
            "<extra></extra>"
        ),
    ))
    fig.add_trace(go.Scatter(
        x=resumen["region"],
        y=resumen["solicitudes"] + max_total * 0.08,
        mode="text",
        text=etiqueta_ratio,
        textfont=dict(size=13, color="#EAFBFF", family="Segoe UI Semibold"),
        hoverinfo="skip",
        showlegend=False,
    ))
    fig.update_layout(
        title=dict(
            text=f"<b>Cumplimiento por region operacional</b><br><span style='font-size:12px;color:#BDEFFF'>{'Solo Tarapaca y Antofagasta' if SERVICIO_ACTUAL == 'IBM' else 'Top regiones/zona filtradas'} | meta {DISPONIBILIDAD_META_PCT}% | SLA {DISPONIBILIDAD_SLA_MIN} min habiles</span>",
            x=0.02,
            xanchor="left",
            font=dict(size=17, color="#DDFBFF", family="Segoe UI Semibold")
        ),
        barmode="stack",
        height=330,
        margin=dict(l=42, r=32, t=84, b=54),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(6,18,34,0.74)",
        legend=dict(orientation="h", y=1.15, x=0.56, xanchor="center", font=dict(size=12, color="#EAFBFF", family="Segoe UI Semibold")),
        hoverlabel=dict(bgcolor="rgba(6,18,34,0.96)", bordercolor="rgba(46,203,242,0.40)", font=dict(size=12, family="Segoe UI", color="#EAFBFF")),
        autosize=True,
    )
    fig.update_xaxes(title=None, showgrid=False, zeroline=False, tickfont=dict(size=12, color="#EAFBFF", family="Segoe UI Semibold"))
    fig.update_yaxes(
        title=dict(text="Solicitudes", font=dict(size=12, color="#BDEFFF", family="Segoe UI Semibold")),
        range=[0, max_total * 1.24],
        rangemode="tozero",
        showgrid=True,
        gridcolor="rgba(143,239,255,0.14)",
        zeroline=False,
        tickfont=dict(size=12, color="#BDEFFF", family="Segoe UI Semibold")
    )
    return fig


def preparar_ranking_coordinadores_disponibilidad(df_base):
    columnas_minimas = {"coordinador", "cumple_kpi"}
    if df_base.empty or not columnas_minimas.issubset(df_base.columns):
        return pd.DataFrame()

    base = df_base.copy()
    base["coordinador"] = (
        base["coordinador"]
        .fillna("Sin respuesta")
        .astype(str)
        .str.strip()
        .replace({"": "Sin respuesta"})
    )
    base = base.loc[base["coordinador"].ne("Sin respuesta")].copy()
    if base.empty:
        return pd.DataFrame()

    base["_cumple"] = base["cumple_kpi"].fillna(False).astype(bool)
    base["_exceso"] = serie_numero_segura(base, "exceso_sla_habiles")
    base["_minutos"] = serie_numero_segura(base, "minutos_habiles")
    base["_critico"] = (~base["_cumple"]) & base["_exceso"].gt(0)

    resumen = (
        base.groupby("coordinador", dropna=False)
        .agg(
            total_casos=("_cumple", "size"),
            dentro_sla=("_cumple", "sum"),
            demora_promedio_min=("_minutos", "mean"),
            mayor_desviacion_min=("_exceso", "max"),
            casos_criticos=("_critico", "sum"),
        )
        .reset_index()
    )
    resumen["fuera_sla"] = resumen["total_casos"] - resumen["dentro_sla"]
    resumen["cumplimiento_pct"] = (resumen["dentro_sla"] / resumen["total_casos"].clip(lower=1) * 100).round(1)
    resumen["demora_promedio_min"] = resumen["demora_promedio_min"].fillna(0).round(1)
    resumen["mayor_desviacion_min"] = resumen["mayor_desviacion_min"].fillna(0).round(1)
    return resumen.sort_values(["cumplimiento_pct", "fuera_sla", "total_casos"], ascending=[True, False, False])


def grafico_coordinadores_disponibilidad(df_base):
    resumen = preparar_ranking_coordinadores_disponibilidad(df_base)
    if resumen.empty:
        return figura_disponibilidad_vacia("Ranking coordinadores", "No hay coordinadores con gestion para los filtros seleccionados")

    vista = resumen.sort_values(["cumplimiento_pct", "total_casos"], ascending=[True, False]).head(10)
    vista = vista.sort_values("cumplimiento_pct", ascending=True)
    colores = [VERDE if pct >= DISPONIBILIDAD_META_PCT else ROSADO for pct in vista["cumplimiento_pct"]]

    fig = go.Figure(go.Bar(
        x=vista["cumplimiento_pct"],
        y=vista["coordinador"],
        orientation="h",
        marker=dict(color=[rgba(c, 0.84) for c in colores], line=dict(color=colores, width=1.4)),
        text=[f"{pct:.1f}% | {int(total)} casos" for pct, total in zip(vista["cumplimiento_pct"], vista["total_casos"])],
        textposition="outside",
        cliponaxis=False,
        customdata=vista[["total_casos", "dentro_sla", "fuera_sla", "demora_promedio_min", "mayor_desviacion_min", "casos_criticos"]].to_numpy(),
        hovertemplate=(
            "%{y}<br>"
            "Cumplimiento: <b>%{x:.1f}%</b><br>"
            "Total: <b>%{customdata[0]}</b><br>"
            "Dentro SLA: <b>%{customdata[1]}</b><br>"
            "Fuera SLA: <b>%{customdata[2]}</b><br>"
            "Demora promedio: <b>%{customdata[3]:.1f} min</b><br>"
            "Mayor desviacion: <b>%{customdata[4]:.1f} min</b><br>"
            "Casos criticos: <b>%{customdata[5]}</b>"
            "<extra></extra>"
        ),
    ))
    fig.add_vline(x=DISPONIBILIDAD_META_PCT, line_dash="dot", line_width=2.4, line_color=CELESTE)
    fig.update_layout(
        title=dict(
            text=f"<b>Ranking de coordinadores</b><br><span style='font-size:12px;color:#BDEFFF'>Ordenado de menor a mayor cumplimiento | SLA {DISPONIBILIDAD_SLA_MIN} min habiles</span>",
            x=0.02,
            xanchor="left",
            font=dict(size=17, color="#DDFBFF", family="Segoe UI Semibold")
        ),
        height=360,
        margin=dict(l=178, r=68, t=82, b=42),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(6,18,34,0.74)",
        hoverlabel=dict(bgcolor="rgba(6,18,34,0.96)", bordercolor="rgba(46,203,242,0.40)", font=dict(size=12, family="Segoe UI", color="#EAFBFF")),
    )
    fig.update_xaxes(
        title=None,
        range=[0, 110],
        ticksuffix="%",
        showgrid=True,
        gridcolor="rgba(143,239,255,0.14)",
        zeroline=False,
        tickfont=dict(size=12, color="#BDEFFF", family="Segoe UI Semibold")
    )
    fig.update_yaxes(title=None, automargin=True, tickfont=dict(size=11, color="#EAFBFF", family="Segoe UI Semibold"))
    return fig


def figura_disponibilidad_vacia(titulo, subtitulo="Sin datos para los filtros seleccionados"):
    fig = go.Figure()
    fig.add_annotation(
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        text=f"<b>{titulo}</b><br><span style='font-size:12px;color:#BDEFFF'>{subtitulo}</span>",
        showarrow=False,
        align="center",
        font=dict(size=16, color="#DDFBFF", family="Segoe UI Semibold"),
    )
    fig.update_layout(
        height=330,
        margin=dict(l=24, r=24, t=40, b=30),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(6,18,34,0.74)",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
    )
    return fig


def grafico_reclamos_motivo(df_base):
    if df_base.empty or "familia_reclamo" not in df_base.columns:
        return figura_disponibilidad_vacia(f"Motivos de reclamo {SERVICIO_TITULO}")

    base = df_base.copy()
    base["familia_reclamo"] = base["familia_reclamo"].fillna("Sin clasificar").astype(str).str.strip().replace({"": "Sin clasificar"})
    resumen = (
        base.groupby("familia_reclamo", dropna=False)
        .agg(
            reclamos=("familia_reclamo", "size"),
            tickets=("ticket_principal", pd.Series.nunique),
        )
        .reset_index()
        .sort_values(["reclamos", "tickets"], ascending=[False, False])
        .head(10)
        .sort_values("reclamos", ascending=True)
    )
    if resumen.empty:
        return figura_disponibilidad_vacia(f"Motivos de reclamo {SERVICIO_TITULO}")

    fig = go.Figure(go.Bar(
        x=resumen["reclamos"],
        y=resumen["familia_reclamo"].map(lambda valor: nombre_corto_leyenda(valor, 34)),
        orientation="h",
        marker=dict(color=rgba(NARANJO, 0.82), line=dict(color=NARANJO, width=1.6)),
        text=[f"{int(rec)} recl. | {int(tkt)} tkt" for rec, tkt in zip(resumen["reclamos"], resumen["tickets"])],
        textposition="outside",
        cliponaxis=False,
        customdata=resumen[["tickets"]].to_numpy(),
        hovertemplate="%{y}<br>Reclamos: <b>%{x}</b><br>Tickets: <b>%{customdata[0]}</b><extra></extra>",
    ))
    fig.update_layout(
        title=dict(
            text=f"<b>Motivos de reclamo {SERVICIO_TITULO}</b><br><span style='font-size:12px;color:#BDEFFF'>Clasificacion por acciones similares de terreno</span>",
            x=0.02,
            xanchor="left",
            font=dict(size=17, color="#DDFBFF", family="Segoe UI Semibold")
        ),
        height=360,
        margin=dict(l=200, r=126, t=82, b=42),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(6,18,34,0.74)",
        hoverlabel=dict(bgcolor="rgba(6,18,34,0.96)", bordercolor="rgba(46,203,242,0.40)", font=dict(size=12, family="Segoe UI", color="#EAFBFF")),
    )
    fig.update_xaxes(title=None, rangemode="tozero", showgrid=True, gridcolor="rgba(143,239,255,0.14)", zeroline=False, tickfont=dict(size=12, color="#BDEFFF", family="Segoe UI Semibold"))
    fig.update_yaxes(title=None, automargin=True, tickfont=dict(size=11, color="#EAFBFF", family="Segoe UI Semibold"))
    return fig


def grafico_reclamos_region(df_base):
    if df_base.empty or "region" not in df_base.columns:
        return figura_disponibilidad_vacia(f"Reclamos por región {SERVICIO_TITULO}")

    base = df_base.copy()
    base["region"] = base["region"].fillna("Sin zona").astype(str).str.strip().replace({"": "Sin zona"})
    base["_alta"] = base["severidad_reclamo"].astype(str).str.upper().eq("ALTA") if "severidad_reclamo" in base.columns else False
    resumen = (
        base.groupby("region", dropna=False)
        .agg(
            reclamos=("region", "size"),
            alta=("_alta", "sum"),
            tickets=("ticket_principal", pd.Series.nunique),
        )
        .reset_index()
        .sort_values(["reclamos", "alta"], ascending=[False, False])
        .head(10)
        .sort_values("reclamos", ascending=True)
    )
    if resumen.empty:
        return figura_disponibilidad_vacia(f"Reclamos por región {SERVICIO_TITULO}")

    fig = go.Figure(go.Bar(
        x=resumen["reclamos"],
        y=resumen["region"].map(lambda valor: nombre_corto_leyenda(valor, 34)),
        orientation="h",
        marker=dict(color=rgba(CELESTE, 0.80), line=dict(color=CELESTE, width=1.6)),
        text=[f"{int(rec)} señales | {int(tkt)} tkt" for rec, tkt in zip(resumen["reclamos"], resumen["tickets"])],
        textposition="outside",
        cliponaxis=False,
        customdata=resumen[["tickets", "alta"]].to_numpy(),
        hovertemplate="%{y}<br>Señales: <b>%{x}</b><br>Tickets: <b>%{customdata[0]}</b><br>Severidad alta: <b>%{customdata[1]}</b><extra></extra>",
    ))
    fig.update_layout(
        title=dict(
            text="<b>Señales operacionales por región</b><br><span style='font-size:12px;color:#BDEFFF'>Reclamos y reforzamientos agrupados por zona normalizada</span>",
            x=0.02,
            xanchor="left",
            font=dict(size=17, color="#DDFBFF", family="Segoe UI Semibold"),
        ),
        height=360,
        margin=dict(l=208, r=126, t=82, b=42),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(6,18,34,0.74)",
        hoverlabel=dict(bgcolor="rgba(6,18,34,0.96)", bordercolor="rgba(46,203,242,0.40)", font=dict(size=12, family="Segoe UI", color="#EAFBFF")),
    )
    fig.update_xaxes(title=None, rangemode="tozero", showgrid=True, gridcolor="rgba(143,239,255,0.14)", zeroline=False, tickfont=dict(size=12, color="#BDEFFF", family="Segoe UI Semibold"))
    fig.update_yaxes(title=None, automargin=True, tickfont=dict(size=11, color="#EAFBFF", family="Segoe UI Semibold"))
    return fig


def grafico_reclamos_cliente(df_base):
    if df_base.empty or "cliente" not in df_base.columns:
        return figura_disponibilidad_vacia(f"Clientes con reclamos {SERVICIO_TITULO}")

    base = df_base.copy()
    base["cliente"] = base["cliente"].fillna("Sin dato").astype(str).str.strip().replace({"": "Sin dato"})
    base["_alta"] = base["severidad_reclamo"].astype(str).str.upper().eq("ALTA") if "severidad_reclamo" in base.columns else False
    resumen = (
        base.groupby("cliente", dropna=False)
        .agg(
            reclamos=("cliente", "size"),
            alta=("_alta", "sum"),
            tickets=("ticket_principal", pd.Series.nunique),
        )
        .reset_index()
        .sort_values(["reclamos", "alta"], ascending=[False, False])
        .head(10)
        .sort_values("reclamos", ascending=True)
    )
    if resumen.empty:
        return figura_disponibilidad_vacia(f"Clientes con reclamos {SERVICIO_TITULO}")

    fig = go.Figure(go.Bar(
        x=resumen["reclamos"],
        y=resumen["cliente"].map(lambda valor: nombre_corto_leyenda(valor, 32)),
        orientation="h",
        marker=dict(color=rgba(ROSADO, 0.80), line=dict(color=ROSADO, width=1.6)),
        text=[f"{int(rec)} recl. | {int(tkt)} tkt" for rec, tkt in zip(resumen["reclamos"], resumen["tickets"])],
        textposition="outside",
        cliponaxis=False,
        customdata=resumen[["tickets", "alta"]].to_numpy(),
        hovertemplate="%{y}<br>Reclamos: <b>%{x}</b><br>Tickets: <b>%{customdata[0]}</b><br>Foco cliente: <b>%{y}</b><extra></extra>",
    ))
    fig.update_layout(
        title=dict(
            text="<b>Clientes afectados por reclamos</b><br><span style='font-size:12px;color:#BDEFFF'>Foco ejecutivo por volumen y recurrencia</span>",
            x=0.02,
            xanchor="left",
            font=dict(size=17, color="#DDFBFF", family="Segoe UI Semibold")
        ),
        height=360,
        margin=dict(l=188, r=118, t=82, b=42),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(6,18,34,0.74)",
        hoverlabel=dict(bgcolor="rgba(6,18,34,0.96)", bordercolor="rgba(46,203,242,0.40)", font=dict(size=12, family="Segoe UI", color="#EAFBFF")),
    )
    fig.update_xaxes(title=None, rangemode="tozero", showgrid=True, gridcolor="rgba(143,239,255,0.14)", zeroline=False, tickfont=dict(size=12, color="#BDEFFF", family="Segoe UI Semibold"))
    fig.update_yaxes(title=None, automargin=True, tickfont=dict(size=11, color="#EAFBFF", family="Segoe UI Semibold"))
    return fig


def grafico_reclamos_servicio(df_base, df_atenciones_base=None):
    if df_base.empty or "servicio_tecnico" not in df_base.columns:
        return figura_disponibilidad_vacia("Reclamos por servicio")

    base = df_base.copy()
    base["servicio_tecnico"] = base["servicio_tecnico"].fillna("Sin dato").astype(str).str.strip().replace({"": "Sin dato"})
    base["_alta"] = base["severidad_reclamo"].astype(str).str.upper().eq("ALTA") if "severidad_reclamo" in base.columns else False
    base["_reforzamiento"] = serie_bool_panel(base["reforzamiento"]) if "reforzamiento" in base.columns else False
    resumen = (
        base.groupby("servicio_tecnico", dropna=False)
        .agg(
            reclamos=("servicio_tecnico", "size"),
            alta=("_alta", "sum"),
            reforzamientos=("_reforzamiento", "sum"),
            tickets=("ticket_principal", pd.Series.nunique),
        )
        .reset_index()
    )
    if resumen.empty:
        return figura_disponibilidad_vacia("Reclamos por servicio")

    if df_atenciones_base is not None and not df_atenciones_base.empty and "servicio_tecnico" in df_atenciones_base.columns:
        atenciones = (
            df_atenciones_base.copy()
            .assign(servicio_tecnico=lambda df_tmp: df_tmp["servicio_tecnico"].fillna("Sin dato").astype(str).str.strip().replace({"": "Sin dato"}))
            .groupby("servicio_tecnico", dropna=False)
            .size()
            .reset_index(name="atenciones_asignadas")
        )
        resumen = resumen.merge(atenciones, on="servicio_tecnico", how="left")
    else:
        resumen["atenciones_asignadas"] = pd.NA
    resumen["atenciones_asignadas"] = pd.to_numeric(resumen["atenciones_asignadas"], errors="coerce").fillna(0).astype(int)
    resumen["reclamos_por_100"] = (
        resumen["reclamos"] / resumen["atenciones_asignadas"].replace(0, pd.NA) * 100
    ).fillna(resumen["reclamos"]).round(1)
    usar_tasa = resumen["atenciones_asignadas"].gt(0).any()
    resumen = resumen.sort_values("reclamos_por_100" if usar_tasa else "reclamos", ascending=True)

    colores = [CELESTE if servicio == "IBM" else ROSADO if servicio == "SAO" else NARANJO for servicio in resumen["servicio_tecnico"]]
    fig = go.Figure(go.Bar(
        x=resumen["reclamos_por_100"] if usar_tasa else resumen["reclamos"],
        y=resumen["servicio_tecnico"],
        orientation="h",
        marker=dict(color=[rgba(color, 0.82) for color in colores], line=dict(color=colores, width=1.8)),
        text=[
            f"{valor:.1f}/100 aten. | {int(rec)} señales"
            if usar_tasa else f"{int(rec)} señales"
            for valor, rec, alta in zip(resumen["reclamos_por_100"], resumen["reclamos"], resumen["alta"])
        ],
        textposition="outside",
        cliponaxis=False,
        customdata=resumen[["reclamos", "tickets", "alta", "atenciones_asignadas", "reforzamientos"]].to_numpy(),
        hovertemplate=(
            "%{y}<br>"
            + ("Reclamos por 100 atenciones: <b>%{x:.1f}</b><br>" if usar_tasa else "")
            + "Señales: <b>%{customdata[0]}</b><br>"
            + "Reforzamientos: <b>%{customdata[4]}</b><br>"
            + "Tickets con reclamo: <b>%{customdata[1]}</b><br>"
            + "Atenciones asignadas: <b>%{customdata[3]}</b><extra></extra>"
        ),
    ))
    fig.update_layout(
        title=dict(
            text=(
                "<b>Comparativo de reclamos por contratista</b><br>"
                "<span style='font-size:12px;color:#BDEFFF'>Reclamos + reforzamientos normalizados por 100 atenciones asignadas del periodo filtrado</span>"
            ),
            x=0.02,
            xanchor="left",
            font=dict(size=17, color="#DDFBFF", family="Segoe UI Semibold")
        ),
        height=300,
        margin=dict(l=102, r=132, t=82, b=42),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(6,18,34,0.74)",
        hoverlabel=dict(bgcolor="rgba(6,18,34,0.96)", bordercolor="rgba(46,203,242,0.40)", font=dict(size=12, family="Segoe UI", color="#EAFBFF")),
    )
    fig.update_xaxes(title="Señales por 100 atenciones" if usar_tasa else None, rangemode="tozero", showgrid=True, gridcolor="rgba(143,239,255,0.14)", zeroline=False, tickfont=dict(size=12, color="#BDEFFF", family="Segoe UI Semibold"))
    fig.update_yaxes(title=None, automargin=True, tickfont=dict(size=12, color="#EAFBFF", family="Segoe UI Semibold"))
    return fig


def grafico_reiteraciones_ticket_disponibilidad(df_base):
    if df_base.empty or "numero_ticket" not in df_base.columns:
        return figura_disponibilidad_vacia("Tickets con reiteraciones totales")

    base = df_base.copy()
    base["numero_ticket"] = base["numero_ticket"].fillna("Sin ticket").astype(str).str.strip().replace({"": "Sin ticket"})
    base["cliente"] = base["cliente"].fillna("Sin dato").astype(str).str.strip().replace({"": "Sin dato"}) if "cliente" in base.columns else "Sin dato"
    base["_reiteraciones"] = calcular_reiteraciones_total_operacional(base)
    base["_solicitud_caso_n"] = pd.to_numeric(base["solicitud_caso_n"], errors="coerce").fillna(1) if "solicitud_caso_n" in base.columns else 1
    base["_total_solicitudes_caso"] = pd.to_numeric(base["total_solicitudes_caso"], errors="coerce").fillna(1) if "total_solicitudes_caso" in base.columns else 1
    base["_cumple"] = base["cumple_kpi"].fillna(False).astype(bool) if "cumple_kpi" in base.columns else False
    base["_minutos"] = pd.to_numeric(base["minutos_habiles"], errors="coerce") if "minutos_habiles" in base.columns else pd.NA
    base["_sin_respuesta"] = base["fecha_respuesta"].isna() if "fecha_respuesta" in base.columns else False

    resumen = (
        base.groupby(["numero_ticket", "cliente"], dropna=False)
        .agg(
            solicitudes=("_cumple", "size"),
            reiteraciones=("_reiteraciones", "sum"),
            cumple=("_cumple", "sum"),
            demora_max=("_minutos", "max"),
            sin_respuesta=("_sin_respuesta", "sum"),
            solicitudes_caso=("_total_solicitudes_caso", "max"),
        )
        .reset_index()
    )
    resumen["no_cumple"] = resumen["solicitudes"] - resumen["cumple"]
    resumen["presion_total"] = resumen["reiteraciones"]
    resumen = (
        resumen.loc[resumen["presion_total"].gt(0)]
        .sort_values(["presion_total", "no_cumple", "solicitudes"], ascending=[False, False, False])
        .head(10)
        .sort_values("presion_total", ascending=True)
    )
    if resumen.empty:
        return figura_disponibilidad_vacia("Tickets con reiteraciones totales", "No se detectan re-insistencias en los filtros")

    resumen["_label"] = resumen.apply(
        lambda row: nombre_corto_leyenda(f"{row['numero_ticket']} | {row['cliente']}", 42),
        axis=1,
    )
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=resumen["presion_total"],
        y=resumen["_label"],
        name="Reiteraciones totales",
        orientation="h",
        marker=dict(color=rgba(NARANJO, 0.84), line=dict(color=NARANJO, width=1.4)),
        cliponaxis=False,
        customdata=resumen[["solicitudes", "solicitudes_caso", "no_cumple", "sin_respuesta", "demora_max", "presion_total"]].to_numpy(),
        hovertemplate=(
            "%{y}<br>"
            "Reiteraciones totales: <b>%{x}</b><br>"
            "Solicitudes medidas: <b>%{customdata[0]}</b><br>"
            "Solicitudes del caso: <b>%{customdata[1]}</b><br>"
            "No cumplen: <b>%{customdata[2]}</b><br>"
            "Sin respuesta: <b>%{customdata[3]}</b><br>"
            "Mayor demora habil: <b>%{customdata[4]:.1f} min</b>"
            "<extra></extra>"
        ),
    ))
    fig.add_trace(go.Scatter(
        x=resumen["presion_total"] + 0.08,
        y=resumen["_label"],
        mode="text",
        text=[
            f"{int(total)} gest. | {int(sol)} sol. caso"
            for total, sol in zip(resumen["presion_total"], resumen["solicitudes_caso"])
        ],
        textposition="middle right",
        textfont=dict(size=11, color="#EAFBFF", family="Segoe UI Semibold"),
        hoverinfo="skip",
        showlegend=False,
    ))
    fig.update_layout(
        title=dict(
            text=f"<b>Reiteraciones por falta de respuesta {SERVICIO_TITULO}</b><br><span style='font-size:12px;color:#BDEFFF'>Toda insistencia cuenta: CECOM, PRODRIGUEZA, NPEREZC o RRODRIGUEZB</span>",
            x=0.02,
            xanchor="left",
            font=dict(size=17, color="#DDFBFF", family="Segoe UI Semibold")
        ),
        barmode="stack",
        height=max(385, 92 + len(resumen) * 31),
        margin=dict(l=205, r=128, t=86, b=44),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(6,18,34,0.74)",
        legend=dict(orientation="h", y=1.14, x=0.58, xanchor="center", font=dict(size=12, color="#EAFBFF", family="Segoe UI Semibold")),
        hoverlabel=dict(bgcolor="rgba(6,18,34,0.96)", bordercolor="rgba(46,203,242,0.40)", font=dict(size=12, family="Segoe UI", color="#EAFBFF")),
    )
    max_x = max(float(resumen["presion_total"].max()), 1.0)
    fig.update_xaxes(title=None, range=[0, max_x + 0.95], dtick=1, showgrid=True, gridcolor="rgba(143,239,255,0.14)", zeroline=False, tickfont=dict(size=12, color="#BDEFFF", family="Segoe UI Semibold"))
    fig.update_yaxes(title=None, automargin=True, tickfont=dict(size=11, color="#EAFBFF", family="Segoe UI Semibold"))
    return fig


def color_servicio_uso(servicio):
    servicio = str(servicio or "").upper()
    if servicio == "IBM":
        return CELESTE
    if servicio == "SAO":
        return ROSADO
    if servicio == "ECC":
        return NARANJO
    return "#8FA7FF"


def render_uso_herramienta_kpi_cards():
    color_nota = VERDE if uso_promedio >= USO_HERRAMIENTA_META_NOTA else CELESTE if uso_promedio >= USO_HERRAMIENTA_NOTA_BUENA else ROSADO
    render_kpi_card_grid([
        {"icono": "&#9673;", "titulo": "Nota OT", "valor": f"{uso_promedio:.1f}", "subtitulo": "Auditoria PDF, escala 1 a 7", "color": color_nota, "badge": f"Meta {USO_HERRAMIENTA_META_NOTA}", "progreso": pct_desde_nota_uso(uso_promedio)},
        {"icono": "&#9606;", "titulo": "OT auditadas", "valor": uso_total, "subtitulo": f"{uso_tecnicos} tecnicos con evidencia", "color": KPI_TOTAL},
        {"icono": "&#10003;", "titulo": "Excelente/Bueno", "valor": f"{uso_pct_ok:.1f}%", "subtitulo": f"{uso_ok} OT con llenado aceptable", "color": VERDE if uso_pct_ok >= 80 else CELESTE, "progreso": uso_pct_ok},
        {"icono": "&#10005;", "titulo": "Criticas", "valor": uso_criticas, "subtitulo": f"{uso_regulares} regulares para corregir", "color": ROSADO if uso_criticas else VERDE},
        {"icono": "&#33;", "titulo": "Retiros incompletos", "valor": uso_retiros_incompletos, "subtitulo": "Sin cables/cargador/accesorios", "color": ROSADO if uso_retiros_incompletos else VERDE},
        {"icono": "&#9673;", "titulo": "Detalle incompleto", "valor": uso_detalle_incompleto, "subtitulo": "Equipo, serie, maquina o activo cuando aplica", "color": ROSADO if uso_detalle_incompleto else VERDE},
    ])


def preparar_ranking_uso_tecnico(df_base):
    if df_base.empty or "tecnico" not in df_base.columns:
        return pd.DataFrame()
    base = df_base.copy()
    base["tecnico"] = base["tecnico"].fillna("Sin tecnico").astype(str).str.strip().replace({"": "Sin tecnico"})
    base["servicio_tecnico"] = base.get("servicio_tecnico", base.get("st", "Sin dato")).fillna("Sin dato").astype(str).str.strip().replace({"": "Sin dato"})
    base["region_atendida"] = base.get("region_atendida", "").fillna("Sin region").astype(str).str.strip().replace({"": "Sin region"})
    base["_critico"] = base["estado_calidad"].astype(str).eq("Critico") if "estado_calidad" in base.columns else False
    base["_ok"] = base["estado_calidad"].astype(str).isin(["Excelente", "Bueno"]) if "estado_calidad" in base.columns else False
    resumen = (
        base.groupby(["servicio_tecnico", "tecnico", "region_atendida"], dropna=False)
        .agg(
            ots=("tecnico", "size"),
            nota_promedio=("puntaje_total", "mean"),
            ok=("_ok", "sum"),
            criticas=("_critico", "sum"),
        )
        .reset_index()
    )
    if resumen.empty:
        return resumen
    resumen["nota_promedio"] = resumen["nota_promedio"].fillna(0).round(1)
    resumen["pct_ok"] = (resumen["ok"] / resumen["ots"].clip(lower=1) * 100).round(1)
    resumen = resumen.sort_values(["nota_promedio", "pct_ok", "ots"], ascending=[False, False, False]).reset_index(drop=True)
    resumen["ranking_global"] = range(1, len(resumen) + 1)
    return resumen


def preparar_ranking_uso_region(df_base):
    if df_base.empty or "region_atendida" not in df_base.columns:
        return pd.DataFrame()
    base = df_base.copy()
    base["region_atendida"] = base["region_atendida"].fillna("Sin region").astype(str).str.strip().replace({"": "Sin region"})
    base["servicio_tecnico"] = base.get("servicio_tecnico", base.get("st", "Sin dato")).fillna("Sin dato").astype(str).str.strip().replace({"": "Sin dato"})
    base["_critico"] = base["estado_calidad"].astype(str).eq("Critico") if "estado_calidad" in base.columns else False
    resumen = (
        base.groupby(["servicio_tecnico", "region_atendida"], dropna=False)
        .agg(
            ots=("region_atendida", "size"),
            nota_promedio=("puntaje_total", "mean"),
            criticas=("_critico", "sum"),
        )
        .reset_index()
    )
    resumen["nota_promedio"] = resumen["nota_promedio"].fillna(0).round(1)
    return resumen.sort_values(["nota_promedio", "ots"], ascending=[False, False])


def grafico_uso_herramienta_servicio(df_base):
    if df_base.empty or "servicio_tecnico" not in df_base.columns:
        return figura_disponibilidad_vacia("Comparativo Uso de Herramienta")
    base = df_base.copy()
    base["servicio_tecnico"] = base["servicio_tecnico"].fillna("Sin dato").astype(str).str.strip().replace({"": "Sin dato"})
    base["_ok"] = base["estado_calidad"].astype(str).isin(["Excelente", "Bueno"]) if "estado_calidad" in base.columns else False
    base["_critico"] = base["estado_calidad"].astype(str).eq("Critico") if "estado_calidad" in base.columns else False
    resumen = (
        base.groupby("servicio_tecnico", dropna=False)
        .agg(
            ots=("servicio_tecnico", "size"),
            nota_promedio=("puntaje_total", "mean"),
            ok=("_ok", "sum"),
            criticas=("_critico", "sum"),
        )
        .reset_index()
    )
    if resumen.empty:
        return figura_disponibilidad_vacia("Comparativo Uso de Herramienta")
    resumen["nota_promedio"] = resumen["nota_promedio"].fillna(0).round(1)
    resumen["pct_ok"] = (resumen["ok"] / resumen["ots"].clip(lower=1) * 100).round(1)
    resumen = resumen.sort_values("nota_promedio", ascending=True)
    colores = [color_servicio_uso(servicio) for servicio in resumen["servicio_tecnico"]]
    fig = go.Figure(go.Bar(
        x=resumen["nota_promedio"],
        y=resumen["servicio_tecnico"],
        orientation="h",
        marker=dict(color=[rgba(color, 0.84) for color in colores], line=dict(color=colores, width=1.8)),
        text=[f"{nota:.1f} | {int(ots)} OT | {pct:.0f}% OK" for nota, ots, pct in zip(resumen["nota_promedio"], resumen["ots"], resumen["pct_ok"])],
        textposition="outside",
        cliponaxis=False,
        customdata=resumen[["ots", "ok", "criticas", "pct_ok"]].to_numpy(),
        hovertemplate=(
            "%{y}<br>Nota promedio: <b>%{x:.1f}</b><br>"
            "OT auditadas: <b>%{customdata[0]}</b><br>"
            "Excelente/Bueno: <b>%{customdata[1]}</b> (%{customdata[3]:.1f}%)<br>"
            "Criticas: <b>%{customdata[2]}</b><extra></extra>"
        ),
    ))
    fig.add_vline(x=USO_HERRAMIENTA_META_NOTA, line_dash="dot", line_width=2.4, line_color=VERDE)
    fig.update_layout(
        title=dict(
            text=f"<b>Performance comparado por contratista</b><br><span style='font-size:12px;color:#BDEFFF'>Escala 1 a 7 | meta {USO_HERRAMIENTA_META_NOTA} | detalle, equipo, serie, retiro y activo cuando aplica</span>",
            x=0.02,
            xanchor="left",
            font=dict(size=17, color="#DDFBFF", family="Segoe UI Semibold"),
        ),
        height=310,
        margin=dict(l=104, r=138, t=82, b=42),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(6,18,34,0.74)",
        hoverlabel=dict(bgcolor="rgba(6,18,34,0.96)", bordercolor="rgba(46,203,242,0.40)", font=dict(size=12, family="Segoe UI", color="#EAFBFF")),
    )
    fig.update_xaxes(title=None, range=[1, 7.35], showgrid=True, gridcolor="rgba(143,239,255,0.14)", zeroline=False, tickfont=dict(size=12, color="#BDEFFF", family="Segoe UI Semibold"))
    fig.update_yaxes(title=None, automargin=True, tickfont=dict(size=12, color="#EAFBFF", family="Segoe UI Semibold"))
    return fig


def grafico_uso_herramienta_dispersion_contextual(df_base, dimension="tecnico"):
    etiquetas = {
        "servicio_tecnico": ("contratista", "Dispersión por contratista"),
        "region_atendida": ("región", "Dispersión por región"),
        "tecnico": ("técnico", "Dispersión por técnico"),
    }
    etiqueta, titulo = etiquetas.get(dimension, etiquetas["tecnico"])
    subtitulo_contextual = (
        "Vista técnica solicitada mediante el filtro de técnicos"
        if dimension == "tecnico"
        else "Vista por región; cambia a técnico solo cuando reduces explícitamente ese filtro"
    )
    if df_base.empty or dimension not in df_base.columns:
        return figura_disponibilidad_vacia(titulo)

    base = df_base.copy()
    for col, default in [
        ("servicio_tecnico", "Sin dato"),
        ("region_atendida", "Sin región"),
        ("tecnico", "Sin técnico"),
        ("folio_ot", ""),
        ("ticket", ""),
        ("estado_calidad", ""),
        ("hallazgos", ""),
    ]:
        if col not in base.columns:
            base[col] = default
        base[col] = base[col].fillna(default).astype(str).str.strip().replace({"": default})

    base["_fecha_graf"] = pd.to_datetime(base.get("fecha_atencion"), format="mixed", dayfirst=True, errors="coerce")
    base["_fecha_label"] = base["_fecha_graf"].dt.strftime("%d-%m-%Y").fillna("Sin fecha")
    base["_x_label"] = base[dimension].map(lambda valor: nombre_corto_leyenda(valor, 28 if dimension == "tecnico" else 34))

    limite = 3 if dimension == "servicio_tecnico" else 8 if dimension == "region_atendida" else 12
    top_dimension = (
        base.groupby(dimension, dropna=False)
        .agg(ots=(dimension, "size"), nota=("puntaje_total", "mean"))
        .sort_values(["nota", "ots"], ascending=[True, False])
        .head(limite)
        .index.astype(str)
        .tolist()
    )
    if top_dimension:
        base = base.loc[base[dimension].astype(str).isin(top_dimension)].copy()
    if base.empty:
        return figura_disponibilidad_vacia(titulo)

    fig = go.Figure()
    for servicio, datos in base.groupby("servicio_tecnico", dropna=False):
        color = color_servicio_uso(servicio)
        fig.add_trace(go.Scatter(
            x=datos["_x_label"],
            y=datos["puntaje_total"],
            mode="markers",
            name=str(servicio),
            marker=dict(
                size=15,
                color=rgba(color, 0.82),
                line=dict(color=color, width=2),
            ),
            customdata=datos[["servicio_tecnico", "region_atendida", "tecnico", "folio_ot", "ticket", "_fecha_label", "estado_calidad", "hallazgos"]].to_numpy(),
            hovertemplate=(
                "%{x}<br>Nota OT: <b>%{y:.1f}/7</b><br>"
                "ST: <b>%{customdata[0]}</b><br>"
                "Region: <b>%{customdata[1]}</b><br>"
                "Tecnico: <b>%{customdata[2]}</b><br>"
                "Folio: <b>%{customdata[3]}</b><br>"
                "Ticket: <b>%{customdata[4]}</b><br>"
                "Fecha: <b>%{customdata[5]}</b><br>"
                "Clasificacion: <b>%{customdata[6]}</b><br>"
                "%{customdata[7]}<extra></extra>"
            ),
        ))

    fig.add_hrect(y0=USO_HERRAMIENTA_META_NOTA, y1=7, fillcolor=rgba(VERDE, 0.10), line_width=0, layer="below")
    fig.add_hline(y=USO_HERRAMIENTA_META_NOTA, line_dash="dot", line_width=2.4, line_color=VERDE, annotation_text=f"Meta {USO_HERRAMIENTA_META_NOTA}", annotation_position="top left")
    fig.add_hline(y=USO_HERRAMIENTA_NOTA_CRITICA, line_dash="dot", line_width=2, line_color=ROSADO, annotation_text=f"Critico < {USO_HERRAMIENTA_NOTA_CRITICA}", annotation_position="bottom left")
    fig.update_layout(
        title=dict(
            text=f"<b>{titulo}</b><br><span style='font-size:12px;color:#BDEFFF'>{subtitulo_contextual}</span>",
            x=0.02,
            xanchor="left",
            font=dict(size=17, color="#DDFBFF", family="Segoe UI Semibold"),
        ),
        height=420,
        margin=dict(l=56, r=126, t=86, b=118),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(6,18,34,0.74)",
        legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center", font=dict(size=12, color="#EAFBFF", family="Segoe UI Semibold")),
        hoverlabel=dict(bgcolor="rgba(6,18,34,0.96)", bordercolor="rgba(46,203,242,0.40)", font=dict(size=12, family="Segoe UI", color="#EAFBFF")),
    )
    fig.update_xaxes(title=None, tickangle=-28, showgrid=False, zeroline=False, automargin=True, tickfont=dict(size=11, color="#BDEFFF", family="Segoe UI Semibold"))
    fig.update_yaxes(title=dict(text="Nota OT (1 a 7)", font=dict(size=12, color="#BDEFFF")), range=[1, 7.25], showgrid=True, gridcolor="rgba(143,239,255,0.14)", zeroline=False, tickfont=dict(size=12, color="#BDEFFF", family="Segoe UI Semibold"))
    return fig


def grafico_uso_herramienta_region(df_base):
    resumen = preparar_ranking_uso_region(df_base)
    if resumen.empty:
        return figura_disponibilidad_vacia("Ranking por region atendida")
    resumen = resumen.sort_values(["nota_promedio", "ots"], ascending=[True, False]).head(10)
    resumen["_label"] = resumen.apply(
        lambda row: nombre_corto_leyenda(
            f"{row['region_atendida']} | {row['servicio_tecnico']}" if SERVICIO_COMPARATIVO else row["region_atendida"],
            38,
        ),
        axis=1,
    )
    colores = [color_servicio_uso(servicio) for servicio in resumen["servicio_tecnico"]]
    fig = go.Figure(go.Bar(
        x=resumen["nota_promedio"],
        y=resumen["_label"],
        orientation="h",
        marker=dict(color=[rgba(color, 0.84) for color in colores], line=dict(color=colores, width=1.6)),
        text=[f"{nota:.1f} | {int(ots)} OT" for nota, ots in zip(resumen["nota_promedio"], resumen["ots"])],
        textposition="outside",
        cliponaxis=False,
        customdata=resumen[["servicio_tecnico", "ots", "criticas"]].to_numpy(),
        hovertemplate="%{y}<br>Nota: <b>%{x:.1f}</b><br>ST: <b>%{customdata[0]}</b><br>OT: <b>%{customdata[1]}</b><br>Criticas: <b>%{customdata[2]}</b><extra></extra>",
    ))
    fig.add_vline(x=USO_HERRAMIENTA_META_NOTA, line_dash="dot", line_width=2.4, line_color=VERDE)
    fig.update_layout(
        title=dict(
            text=f"<b>Ranking por region atendida</b><br><span style='font-size:12px;color:#BDEFFF'>Escala 1 a 7 | meta {USO_HERRAMIENTA_META_NOTA} | menor nota requiere correccion documental</span>",
            x=0.02,
            xanchor="left",
            font=dict(size=17, color="#DDFBFF", family="Segoe UI Semibold"),
        ),
        height=max(360, 90 + len(resumen) * 30),
        margin=dict(l=226, r=110, t=82, b=44),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(6,18,34,0.74)",
        hoverlabel=dict(bgcolor="rgba(6,18,34,0.96)", bordercolor="rgba(46,203,242,0.40)", font=dict(size=12, family="Segoe UI", color="#EAFBFF")),
    )
    fig.update_xaxes(title=None, range=[1, 7.35], showgrid=True, gridcolor="rgba(143,239,255,0.14)", zeroline=False, tickfont=dict(size=12, color="#BDEFFF", family="Segoe UI Semibold"))
    fig.update_yaxes(title=None, automargin=True, tickfont=dict(size=11, color="#EAFBFF", family="Segoe UI Semibold"))
    return fig


def construir_insights_uso_herramienta_fallback(metricas):
    total_uso = int(metricas.get("uso_total", 0))
    promedio = float(metricas.get("uso_promedio", 0))
    pct_ok = float(metricas.get("uso_pct_ok", 0))
    criticas = int(metricas.get("uso_criticas", 0))
    retiros = int(metricas.get("uso_retiros_incompletos", 0))
    detalle_incompleto = int(metricas.get("uso_detalle_incompleto", 0))
    comparativo = str(metricas.get("comparativo_uso_herramienta_proveedor", "")).strip()

    if not total_uso:
        return [recomendacion_clara(
            "Base de OT", "Sin auditoría", "No hay OT auditadas en la selección",
            "Los filtros activos no contienen PDF de órdenes de trabajo procesados.",
            "Ampliar mes, semana o zona. Si esperabas OT nuevas, ejecutar la actualización PST OT.",
            "accion",
        )]

    estado_nota, tono_nota, brecha_nota = estado_segun_meta(
        promedio, USO_HERRAMIENTA_META_NOTA,
        tolerancia=max(USO_HERRAMIENTA_META_NOTA - USO_HERRAMIENTA_NOTA_BUENA, 0.2),
    )
    total_hallazgos = criticas + retiros + detalle_incompleto
    if criticas:
        estado_hallazgo, tono_hallazgo = "Prioridad alta", "mal"
    elif retiros or detalle_incompleto:
        estado_hallazgo, tono_hallazgo = "Corrección documental", "accion"
    else:
        estado_hallazgo, tono_hallazgo = "Sin hallazgos críticos", "bien"

    return [
        recomendacion_clara(
            "Nota documental", estado_nota,
            f"Nota {promedio:.1f}/7: {abs(brecha_nota):.1f} puntos {'sobre' if brecha_nota >= 0 else 'bajo'} la meta",
            f"Se auditaron {total_uso} OT y {pct_ok:.1f}% quedó en nivel Excelente o Bueno. La meta documental es {USO_HERRAMIENTA_META_NOTA:.1f}.",
            "Abrir la zona con menor nota, revisar primero sus OT bajo meta y después bajar a los técnicos responsables." if tono_nota != "bien" else "Mantener una muestra semanal por zona y replicar las OT mejor documentadas.",
            tono_nota,
        ),
        recomendacion_clara(
            "Hallazgos", estado_hallazgo,
            f"{total_hallazgos} alertas documentales requieren revisión" if total_hallazgos else "La selección no muestra fallas críticas",
            f"Hay {criticas} OT críticas, {retiros} retiros incompletos y {detalle_incompleto} registros con detalle insuficiente.",
            "Exigir equipo intervenido, serie, nombre de máquina, descripción del trabajo, firmas y activo fijo cuando corresponda." if total_hallazgos else "Mantener el estándar y auditar una muestra de OT por semana.",
            tono_hallazgo,
        ),
        recomendacion_clara(
            "Foco de mejora", "Comparación entre ST" if comparativo else "Priorizar por zona",
            "Comenzar por el resultado más bajo",
            "La comparación usa la misma pauta documental para todas las OT filtradas." if comparativo else "La vista actual debe analizarse primero por región para evitar una lista masiva de técnicos.",
            "Tomar el ST con menor nota y revisar sus regiones críticas antes del comité." if comparativo else "Abrir el ranking regional, seleccionar la zona con menor nota y después revisar sus técnicos y OT críticas.",
            "accion" if tono_nota != "bien" or comparativo else "bien",
        ),
    ]


def render_analisis_uso_herramienta(metricas):
    render_analisis_hoja("KPI Uso correcto de herramienta", metricas, construir_insights_uso_herramienta_fallback(metricas))


if mostrar_kpi_inicio:
    render_kpi_card_grid([
        {"icono": "&#9606;", "titulo": "Total asignado", "valor": total, "subtitulo": "Base filtrada vigente", "color": KPI_TOTAL},
        {"icono": "&#9673;", "titulo": "% cumplimiento", "valor": f"{pct:.0f}%", "subtitulo": "Inicio <= 15 min", "color": KPI_CUMPLIMIENTO, "badge": "Meta 80%", "progreso": pct},
        {"icono": "&#10003;", "titulo": "Finalizado 1a visita", "valor": finalizadas_primera_visita, "subtitulo": "Cierre sin visita adicional", "color": KPI_PRIMERA_VISITA, "badge": f"{pct_primera_visita:.0f}%", "progreso": pct_primera_visita},
        {"icono": "&#8635;", "titulo": "Ratio revisitas", "valor": f"{pct_revisitas:.1f}%", "subtitulo": "Tickets con visita adicional", "color": KPI_REVISITA, "badge": revisitas, "progreso": pct_revisitas},
    ])
    render_analisis_inicio({
        "total": total,
        "cumple": cumple,
        "pct": pct,
        "finalizadas": finalizadas,
        "no_finalizadas": no_finalizadas,
        "finalizadas_primera_visita": finalizadas_primera_visita,
        "pct_primera_visita": pct_primera_visita,
        "revisitas": revisitas,
        "pct_revisitas": pct_revisitas,
        "comparativo_inicio_proveedor": comparativo_inicio_proveedor,
    })



if mostrar_kpi_epa:
    st.markdown('<div class="kpi-divider"></div>', unsafe_allow_html=True)
    render_tarjeta_metodologia_kpi(KPI_EPA)

    if True:
        render_kpi_card_grid([
            {"icono": "&#9673;", "titulo": "Satisfaccion EPA", "valor": f"{epa_satisfaccion:.0f}%", "subtitulo": "Nota >= 4 (1 a 5)", "color": VERDE, "badge": "Meta 90%", "progreso": epa_satisfaccion},
            {"icono": "&#10003;", "titulo": "Promedio EPA", "valor": f"{epa_promedio:.1f}", "subtitulo": "Escala 1 a 5", "color": CELESTE, "badge": "Nota", "progreso": epa_promedio * 20},
            {"icono": "&#9606;", "titulo": "Respondidas", "valor": epa_total_respuestas, "subtitulo": "Links completados", "color": AZUL_CLARO},
            {"icono": "&#10005;", "titulo": "Pendientes", "valor": epa_pendientes, "subtitulo": "Links sin respuesta", "color": ROSADO},
        ])
        render_analisis_epa({
            "epa_total_atenciones": epa_total_atenciones,
            "epa_total_respuestas": epa_total_respuestas,
            "epa_pendientes": epa_pendientes,
            "epa_promedio": epa_promedio,
            "epa_satisfechas": epa_satisfechas,
            "epa_satisfaccion": epa_satisfaccion,
            "epa_recomendacion": epa_recomendacion,
        })

        gauge_epa = go.Figure()
        gauge_epa.add_trace(
            go.Indicator(
                mode="gauge+number",
                value=epa_satisfaccion,
                number={"suffix": "%", "font": {"size": 54, "family": "Segoe UI Black", "color": VERDE}},
                title={
                    "text": "<b>Satisfacci\u00f3n EPA</b><br><span style='font-size:0.72em;color:#BDEFFF'>Respuestas con nota promedio >= 4 en escala 1 a 5</span>",
                    "font": {"size": 18, "family": "Segoe UI Semibold", "color": "#DDFBFF"}
                },
                gauge={
                    "axis": {"range": [0, 100], "tickwidth": 0, "tickcolor": "rgba(0,0,0,0)"},
                    "bar": {"color": VERDE, "thickness": 0.24},
                    "bgcolor": "rgba(255,255,255,0.45)",
                    "borderwidth": 0,
                    "steps": [
                        {"range": [0, 60], "color": rgba(ROSADO, 0.13)},
                        {"range": [60, 85], "color": rgba(CELESTE, 0.15)},
                        {"range": [85, 100], "color": rgba(VERDE, 0.18)},
                    ],
                    "threshold": {
                        "line": {"color": ROSADO, "width": 5},
                        "thickness": 0.78,
                        "value": 90,
                    },
                },
                domain={"x": [0.02, 0.48], "y": [0.02, 0.86]},
            )
        )

        titulo_barra_epa = "Promedio EPA por región"
        if len(df_epa_respondidas):
            if VISTA_TECNICO_SOLICITADA and "tecnico" in df_epa_respondidas.columns:
                dimension_barra_epa = "tecnico"
            elif "region" in df_epa_respondidas.columns:
                dimension_barra_epa = "region"
            elif SERVICIO_COMPARATIVO and "servicio_tecnico" in df_epa_respondidas.columns:
                dimension_barra_epa = "servicio_tecnico"
            else:
                dimension_barra_epa = "tecnico"
            titulo_barra_epa = (
                "Promedio EPA por Servicio Técnico" if dimension_barra_epa == "servicio_tecnico"
                else "Promedio EPA por región" if dimension_barra_epa == "region"
                else "Promedio EPA por técnico"
            )
            por_dimension_epa = (
                df_epa_respondidas.assign(**{
                    dimension_barra_epa: df_epa_respondidas[dimension_barra_epa].fillna("Sin dato").astype(str).str.strip().replace({"": "Sin dato"})
                })
                .groupby(dimension_barra_epa, dropna=False)["promedio"]
                .mean()
                .sort_values(ascending=True)
                .tail(8)
            )
            gauge_epa.add_trace(
                go.Bar(
                    x=por_dimension_epa.values,
                    y=por_dimension_epa.index.astype(str),
                    orientation="h",
                    marker=dict(color=CELESTE, line=dict(color="#FFFFFF", width=1.5)),
                    text=[f"{v:.1f}" for v in por_dimension_epa.values],
                    textposition="outside",
                    cliponaxis=False,
                    hovertemplate="%{y}<br>Promedio EPA: %{x:.2f}<extra></extra>",
                    xaxis="x2",
                    yaxis="y2",
                    showlegend=False,
                )
            )

        gauge_epa.add_shape(
            type="rect",
            x0=0, y0=0, x1=1, y1=1,
            xref="paper", yref="paper",
            fillcolor="rgba(6,18,34,0.82)",
            line=dict(color=rgba(CELESTE, 0.56), width=1.4),
            layer="below"
        )
        gauge_epa.add_shape(
            type="rect",
            x0=0, y0=0.965, x1=1, y1=1,
            xref="paper", yref="paper",
            fillcolor=CELESTE,
            line=dict(width=0),
            layer="below"
        )
        gauge_epa.add_annotation(
            x=0.73, y=0.84,
            xref="paper", yref="paper",
            text=f"<b>{titulo_barra_epa}</b>",
            showarrow=False,
            font=dict(size=16, color="#DDFBFF", family="Segoe UI Semibold")
        )
        gauge_epa.update_layout(
            height=350,
            margin=dict(l=20, r=34, t=42, b=22),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(6,18,34,0.72)",
            xaxis2=dict(
                domain=[0.57, 0.98],
                range=[0, 5],
                showgrid=True,
                gridcolor="rgba(143,239,255,0.14)",
                zeroline=False,
                tickfont=dict(size=11, color="#BDEFFF")
            ),
            yaxis2=dict(
                domain=[0.12, 0.72],
                automargin=True,
                tickfont=dict(size=11, color="#EAFBFF", family="Segoe UI Semibold")
            ),
            showlegend=False
        )

        st.plotly_chart(gauge_epa, width="stretch", config=PLOTLY_CONFIG_SOLO_LECTURA)

        if len(df_epa_respondidas):
            if VISTA_TECNICO_SOLICITADA and "tecnico" in df_epa_respondidas.columns:
                dimension_dispersion_epa = "tecnico"
                titulo_dispersion_epa = "Promedio EPA en el tiempo por técnico seleccionado"
            elif "region" in df_epa_respondidas.columns:
                dimension_dispersion_epa = "region"
                titulo_dispersion_epa = "Promedio EPA en el tiempo por región"
            elif "servicio_tecnico" in df_epa_respondidas.columns:
                dimension_dispersion_epa = "servicio_tecnico"
                titulo_dispersion_epa = "Promedio EPA en el tiempo por Servicio Técnico"
            else:
                dimension_dispersion_epa = "tecnico"
                titulo_dispersion_epa = "Promedio EPA en el tiempo por técnico"

            dispersion_epa = preparar_dispersion_epa(df_epa_respondidas, dimension_dispersion_epa)
            if len(dispersion_epa):
                st.plotly_chart(
                    grafico_dispersion_epa(dispersion_epa, dimension_dispersion_epa, titulo_dispersion_epa),
                    width="stretch",
                    config=PLOTLY_CONFIG_SOLO_LECTURA,
                )
            else:
                st.info("No hay respuestas EPA con fecha y promedio para graficar la vista seleccionada.")

        if not epa_total_atenciones:
            st.info("Aun no hay links EPA creados. Genera atenciones desde la carpeta EPA para alimentar este KPI.")

    with st.expander("Revisi\u00f3n EPA", expanded=False):
        if len(df_epa_f):
            export_col, icon_col = st.columns([0.92, 0.08], gap="small")
            with export_col:
                st.markdown('<div class="filter-mini-note">Detalle EPA filtrado por regi\u00f3n, t\u00e9cnico, periodo y cliente.</div>', unsafe_allow_html=True)
            with icon_col:
                render_boton_exportar_epa_revision(df_epa_export, filtros_export)

            st.dataframe(df_epa_export, width="stretch", hide_index=True)
        else:
            st.info("No hay registros EPA para revisar.")


if mostrar_kpi_uso_herramienta:
    st.markdown('<div class="kpi-divider"></div>', unsafe_allow_html=True)
    render_tarjeta_metodologia_kpi(KPI_USO_HERRAMIENTA)

    render_uso_herramienta_kpi_cards()
    render_analisis_uso_herramienta({
        "uso_total": uso_total,
        "uso_promedio": uso_promedio,
        "uso_excelentes": uso_excelentes,
        "uso_buenas": uso_buenas,
        "uso_regulares": uso_regulares,
        "uso_criticas": uso_criticas,
        "uso_pct_ok": uso_pct_ok,
        "uso_retiros_incompletos": uso_retiros_incompletos,
        "uso_detalle_incompleto": uso_detalle_incompleto,
        "uso_cge_sin_activo": uso_cge_sin_activo,
        "uso_brecha_meta": uso_brecha_meta,
        "comparativo_uso_herramienta_proveedor": comparativo_uso_herramienta_proveedor,
    })

    if len(df_uso_f):
        dimension_dispersion_uso = "tecnico" if VISTA_TECNICO_SOLICITADA else "region_atendida"
        st.plotly_chart(
            grafico_uso_herramienta_dispersion_contextual(df_uso_f, dimension_dispersion_uso),
            width="stretch",
            config=PLOTLY_CONFIG_SOLO_LECTURA,
        )

        col_uso_region, col_uso_ranking = st.columns([0.55, 0.45])
        with col_uso_region:
            st.plotly_chart(
                grafico_uso_herramienta_region(df_uso_f),
                width="stretch",
                config=PLOTLY_CONFIG_SOLO_LECTURA,
            )
        with col_uso_ranking:
            ranking_uso = preparar_ranking_uso_tecnico(df_uso_f)
            if len(ranking_uso):
                ranking_vista = ranking_uso.head(15).rename(columns={
                    "ranking_global": "#",
                    "servicio_tecnico": "ST",
                    "tecnico": "Tecnico",
                    "region_atendida": "Region",
                    "ots": "OT",
                    "nota_promedio": "Nota",
                    "pct_ok": "% OK",
                    "criticas": "Criticas",
                })
                st.markdown('<div class="filter-mini-note">Ranking global por tecnico, ordenado por nota promedio y consistencia de OT.</div>', unsafe_allow_html=True)
                st.dataframe(
                    ranking_vista[["#", "ST", "Tecnico", "Region", "OT", "Nota", "% OK", "Criticas"]],
                    width="stretch",
                    hide_index=True,
                )
            else:
                st.info("No hay ranking tecnico para los filtros seleccionados.")

        with st.expander("Detalle auditoria OT", expanded=False):
            st.markdown('<div class="filter-mini-note">Detalle limpio de auditoria; el export conserva la evidencia completa, descripcion, hallazgos y fuente de clasificacion.</div>', unsafe_allow_html=True)
            columnas_detalle_uso = [
                "Servicio tecnico", "Folio OT", "Ticket", "Cliente", "Region atendida",
                "Tecnico", "Nota OT", "Clasificacion", "Requiere retiro",
                "Requiere instalacion", "Hallazgos",
            ]
            columnas_detalle_uso = [col for col in columnas_detalle_uso if col in df_uso_export.columns]
            st.dataframe(
                df_uso_export[columnas_detalle_uso].head(DISPONIBILIDAD_TABLA_MAX_FILAS),
                width="stretch",
                hide_index=True,
            )
            if len(df_uso_export) > DISPONIBILIDAD_TABLA_MAX_FILAS:
                st.markdown(
                    f'<div class="filter-mini-note">Mostrando {DISPONIBILIDAD_TABLA_MAX_FILAS} de {len(df_uso_export)} OT en pantalla. El export conserva todo el detalle filtrado.</div>',
                    unsafe_allow_html=True,
                )
    else:
        render_estado_sin_datos(
            "No hay datos para mostrar",
            "Sin auditoria OT para los filtros seleccionados. Ejecuta actualizacion completa para leer la PST y refrescar los PDF.",
        )


if mostrar_kpi_disponibilidad:
    st.markdown('<div class="kpi-divider"></div>', unsafe_allow_html=True)
    render_tarjeta_metodologia_kpi(KPI_DISPONIBILIDAD)

    if disponibilidad_no_aplica_servicio:
        render_estado_sin_datos(
            "No hay datos para mostrar",
            f"{SERVICIO_ACTUAL} no aplica en KPI Disponibilidad porque opera directo con centro de comando.",
            "KPI no aplicable",
        )
    else:
        color_cumplimiento_disp = VERDE if disp_pct >= DISPONIBILIDAD_META_PCT else ROSADO
        render_disponibilidad_kpi_cards(color_cumplimiento_disp, disp_pct, disp_total, disp_cumple, disp_no_cumple, disp_sin_respuesta, disp_reit_cecom_total)
        render_analisis_disponibilidad({
            "disp_total": disp_total,
            "disp_pct": disp_pct,
            "disp_cumple": disp_cumple,
            "disp_no_cumple": disp_no_cumple,
            "disp_sin_respuesta": disp_sin_respuesta,
            "disp_brecha_meta": disp_brecha_meta,
            "disp_reiteraciones": disp_reiteraciones,
            "disp_tickets_reiterados": disp_tickets_reiterados,
            "disp_reit_cecom_total": disp_reit_cecom_total,
            "reclamos_total": reclamos_total,
            "reclamos_alta": reclamos_alta,
            "reclamos_tickets": reclamos_tickets,
            "reclamos_motivo_top": str(reclamos_motivo_top),
            "comparativo_disponibilidad_proveedor": comparativo_disponibilidad_proveedor,
        })

        if not existe_cache_disponibilidad(SERVICIOS_ACTIVOS):
            render_estado_sin_datos(
                "No hay datos para mostrar",
                "Aun no existe extraccion de disponibilidad para el servicio seleccionado.",
                "Base pendiente",
            )
        elif len(df_disp_f):
            resumen_disp = preparar_resumen_mensual_disponibilidad(df_disp_f)
            if len(resumen_disp):
                st.plotly_chart(
                    grafico_disponibilidad_mensual(resumen_disp),
                    width="stretch",
                    config=PLOTLY_CONFIG_SOLO_LECTURA,
                )
            else:
                render_estado_sin_datos("No hay datos para mostrar", "No hay fechas de solicitud válidas para graficar la tendencia mensual.")
            st.plotly_chart(
                grafico_disponibilidad_region_operacional(df_disp_f),
                width="stretch",
                config=PLOTLY_CONFIG_SOLO_LECTURA,
            )
        else:
            render_estado_sin_datos("No hay datos para mostrar", "Sin solicitudes de disponibilidad para los filtros seleccionados.")


if mostrar_kpi_reclamos:
    st.markdown('<div class="kpi-divider"></div>', unsafe_allow_html=True)
    render_tarjeta_metodologia_kpi(KPI_RECLAMOS)

    if reclamos_no_aplica_servicio:
        render_estado_sin_datos(
            "No hay datos para mostrar",
            f"{SERVICIO_ACTUAL} no se mide en KPI Reclamos dentro de este panel.",
            "KPI no aplicable",
        )
    else:
        render_reclamos_kpi_cards(
            reclamos_total,
            reclamos_reclamos_duros,
            reclamos_reforzamientos,
            reclamos_alta,
            reclamos_tickets,
            reclamos_clientes,
            atenciones_asignadas_reclamos,
            reclamos_ratio_incumplimiento,
            reclamos_cumplimiento_ajustado,
            reclamos_brecha_meta,
            reclamos_cliente_top,
            reclamos_cliente_top_count,
            reclamos_cliente_top_tickets,
            reclamos_proveedor_reforzado_top,
            reclamos_proveedor_reforzado_top_count,
        )
        render_analisis_reclamos({
            "reclamos_total": reclamos_total,
            "reclamos_reclamos_duros": reclamos_reclamos_duros,
            "reclamos_reforzamientos": reclamos_reforzamientos,
            "reclamos_alta": reclamos_alta,
            "reclamos_tickets": reclamos_tickets,
            "reclamos_clientes": reclamos_clientes,
            "reclamos_motivo_top": str(reclamos_motivo_top),
            "reclamos_motivo_top_count": reclamos_motivo_top_count,
            "reclamos_cliente_top": str(reclamos_cliente_top),
            "reclamos_cliente_top_count": reclamos_cliente_top_count,
            "reclamos_proveedor_reforzado_top": str(reclamos_proveedor_reforzado_top),
            "reclamos_proveedor_reforzado_top_count": reclamos_proveedor_reforzado_top_count,
            "atenciones_asignadas_reclamos": atenciones_asignadas_reclamos,
            "reclamos_ratio_incumplimiento": reclamos_ratio_incumplimiento,
            "reclamos_cumplimiento_ajustado": reclamos_cumplimiento_ajustado,
            "reclamos_brecha_meta": reclamos_brecha_meta,
            "comparativo_reclamos_proveedor": comparativo_reclamos_proveedor,
        })

        if len(df_reclamos_f):
            col_rec_motivo, col_rec_region = st.columns([0.48, 0.52])
            with col_rec_motivo:
                st.plotly_chart(
                    grafico_reclamos_motivo(df_reclamos_f),
                    width="stretch",
                    config=PLOTLY_CONFIG_SOLO_LECTURA,
                )
            with col_rec_region:
                st.plotly_chart(
                    grafico_reclamos_region(df_reclamos_f),
                    width="stretch",
                    config=PLOTLY_CONFIG_SOLO_LECTURA,
                )

            st.markdown(f'<div class="filter-mini-note">Detalle reclamos {SERVICIO_TITULO}: cliente, ticket y clasificacion homologada. El export conserva remitentes, asunto, extracto y evidencia completa.</div>', unsafe_allow_html=True)
            df_reclamos_vista = preparar_vista_reclamos_limpia(df_reclamos_export).head(DISPONIBILIDAD_TABLA_MAX_FILAS)
            if len(df_reclamos_export) > DISPONIBILIDAD_TABLA_MAX_FILAS:
                st.markdown(
                    f'<div class="filter-mini-note">Mostrando {DISPONIBILIDAD_TABLA_MAX_FILAS} de {len(df_reclamos_export)} filas en pantalla. El export conserva la vista filtrada completa.</div>',
                    unsafe_allow_html=True,
                )
            st.dataframe(df_reclamos_vista, width="stretch", hide_index=True)
        else:
            render_estado_sin_datos("No hay datos para mostrar", "Sin reclamos para los filtros seleccionados.")




if mostrar_kpi_inicio:
    # =====================================================
    # GRAFICO GERENCIAL ENTEL - OPCION 2: COMPARATIVO PREMIUM
    # =====================================================
    # Opción más limpia y ejecutiva: tendencia por región, conectores de brecha
    # mensual, zona de meta Entel y lectura sin títulos sobrepuestos.

    df_graf_inicio = df_f.copy()
    estado_graf_col = "Estado"
    dimension_graf_label = "Región"
    titulo_evolucion_inicio = "Evolución mensual de cumplimiento por región"
    subtitulo_evolucion_inicio = "Comparativo gerencial contra meta operacional Entel 80%"
    if VISTA_TECNICO_SOLICITADA and "Recurso" in df_graf_inicio.columns:
        df_graf_inicio["_Dimension_Graf"] = (
            df_graf_inicio["Recurso"]
            .fillna("Sin técnico")
            .astype(str)
            .str.strip()
            .replace({"": "Sin técnico"})
        )
        estado_graf_col = "_Dimension_Graf"
        dimension_graf_label = "Técnico"
        titulo_evolucion_inicio = "Evolución mensual de técnicos seleccionados"
        subtitulo_evolucion_inicio = "Vista técnica solicitada contra meta operacional Entel 80%"
    elif "Estado" in df_graf_inicio.columns:
        regiones_top = (
            df_graf_inicio["Estado"]
            .dropna()
            .astype(str)
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .value_counts()
            .head(5)
            .index
            .tolist()
        )
        if df_graf_inicio["Estado"].dropna().astype(str).nunique() > len(regiones_top):
            df_graf_inicio["_Estado_Graf"] = df_graf_inicio["Estado"].where(
                df_graf_inicio["Estado"].astype(str).isin(regiones_top),
                "Otras regiones",
            )
            estado_graf_col = "_Estado_Graf"

    graf = (
        df_graf_inicio.groupby(["Mes", estado_graf_col])["Cumple"]
            .mean()
            .mul(100)
            .reset_index()
            .rename(columns={estado_graf_col: "Estado"})
    )

    graf["Mes"] = pd.Categorical(graf["Mes"], categories=MESES, ordered=True)
    graf = graf.sort_values(["Mes", "Estado"])

    # Encabezado fuera del gráfico para evitar que Plotly pise títulos o leyendas.
    st.markdown(
        f"""
        <div style="
            background:radial-gradient(circle at 96% 18%,rgba(46,203,242,.18),transparent 24%),linear-gradient(180deg,rgba(255,255,255,.96) 0%,rgba(248,252,255,.94) 100%);
            border-top:6px solid {AZUL};
            border-left:1px solid rgba(46,203,242,0.24);
            border-right:1px solid rgba(253,108,152,0.18);
            border-bottom:1px solid #E6EBF3;
            padding:11px 18px 10px 18px;
            margin-top:4px;
            margin-bottom:0px;
            box-shadow:0 18px 34px rgba(16,6,159,.10),0 0 18px rgba(46,203,242,.14),inset 0 1px 0 rgba(255,255,255,.90);
        ">
            <div style="font-size:20px;font-weight:900;color:{AZUL};letter-spacing:-.2px;text-shadow:0 0 12px rgba(46,203,242,.18);">
                {titulo_evolucion_inicio}
            </div>
            <div style="font-size:12px;font-weight:650;color:#64748B;margin-top:3px;">
                {subtitulo_evolucion_inicio}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    fig = go.Figure()

    # Fondo por capas: da profundidad sin competir con las series regionales.
    for y0, y1, alpha in [(0, 20, 0.018), (20, 40, 0.026), (40, 60, 0.034), (60, 80, 0.042)]:
        fig.add_hrect(
            y0=y0,
            y1=y1,
            fillcolor=rgba(AZUL_CLARO, alpha),
            line_width=0,
            layer="below"
        )

    # Zona objetivo Entel.
    fig.add_hrect(
        y0=80,
        y1=100,
        fillcolor="rgba(253,108,152,0.10)",
        line_width=0,
        layer="below"
    )

    fig.add_hline(
        y=80,
        line_dash="dot",
        line_width=2.8,
        line_color=ROSADO
    )

    st.markdown(
        f"""
        <div style="
            display:flex;
            justify-content:flex-start;
            align-items:center;
            padding:9px 0 0 22px;
            margin:0;
        ">
            <div style="
                display:inline-flex;
                align-items:center;
                gap:8px;
                background:transparent;
                color:{ROSADO};
                font-size:13px;
                font-weight:950;
                font-family:'Segoe UI',sans-serif;
                letter-spacing:.02em;
                border:1px solid rgba(253,108,152,.78);
                border-radius:999px;
                padding:6px 12px;
                box-shadow:0 0 14px rgba(253,108,152,.38), inset 0 0 10px rgba(253,108,152,.10);
                text-shadow:0 0 8px rgba(253,108,152,.90), 0 0 16px rgba(253,108,152,.48);
            ">
                <span style="
                    width:8px;
                    height:8px;
                    border-radius:50%;
                    background:{ROSADO};
                    box-shadow:0 0 10px rgba(253,108,152,.95),0 0 18px rgba(253,108,152,.55);
                    display:inline-block;
                "></span>
                Meta Entel 80%
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    palette = CHART_PALETTE
    regiones_graf = list(graf["Estado"].dropna().unique())
    mostrar_etiquetas_region = len(regiones_graf) <= 4

    # Conectores de brecha mensual entre regiones: da lectura gerencial sin usar barras.
    pivot = (
        graf.pivot_table(
            index="Mes",
            columns="Estado",
            values="Cumple",
            aggfunc="mean",
            observed=False
        )
        .reindex(MESES)
        .dropna(how="all")
    )

    if len(regiones_graf) >= 2:
        for mes in pivot.index:
            vals = pivot.loc[mes].dropna()
            if len(vals) >= 2:
                fig.add_trace(go.Scatter(
                    x=[mes, mes],
                    y=[vals.min(), vals.max()],
                    mode="lines",
                    line=dict(color="rgba(15,23,42,0.10)", width=10),
                    hoverinfo="skip",
                    showlegend=False
                ))
                fig.add_trace(go.Scatter(
                    x=[mes, mes],
                    y=[vals.min(), vals.max()],
                    mode="lines",
                    line=dict(color="rgba(148,163,184,0.50)", width=1.6),
                    hoverinfo="skip",
                    showlegend=False
                ))

    # Tendencias por región.
    for i, zona in enumerate(regiones_graf):
        d = graf[graf["Estado"] == zona].copy()
        c = palette[i % len(palette)]

        posiciones = ["top center" if i % 2 == 0 else "bottom center"] * len(d)

        # Sombra desplazada: simula profundidad sin alterar los valores.
        fig.add_trace(go.Scatter(
            x=d["Mes"],
            y=d["Cumple"].sub(1.4).clip(lower=0),
            mode="lines",
            line=dict(color="rgba(15,23,42,0.11)", width=12, shape="spline", smoothing=0.9),
            hoverinfo="skip",
            showlegend=False
        ))

        # Halo de color por serie.
        fig.add_trace(go.Scatter(
            x=d["Mes"],
            y=d["Cumple"],
            mode="lines",
            line=dict(color=rgba(c, 0.18), width=15, shape="spline", smoothing=0.9),
            hoverinfo="skip",
            showlegend=False
        ))

        # Sombra de marcadores.
        fig.add_trace(go.Scatter(
            x=d["Mes"],
            y=d["Cumple"].sub(0.9).clip(lower=0),
            mode="markers",
            marker=dict(size=20, color="rgba(15,23,42,0.16)", line=dict(width=0)),
            hoverinfo="skip",
            showlegend=False
        ))

        # Línea principal.
        fig.add_trace(go.Scatter(
            x=d["Mes"],
            y=d["Cumple"],
            name=str(zona),
            mode="lines+markers+text" if mostrar_etiquetas_region else "lines+markers",
            line=dict(color=c, width=4.4, shape="spline", smoothing=0.9),
            marker=dict(
                size=15,
                color="#FFFFFF",
                line=dict(color=c, width=4)
            ),
            text=[f"<b>{v:.1f}%</b>" for v in d["Cumple"]] if mostrar_etiquetas_region else None,
            textposition=posiciones if mostrar_etiquetas_region else None,
            textfont=dict(size=13, color=c, family="Segoe UI Black"),
            hovertemplate=(
                "<b>%{x}</b><br>"
                f"{dimension_graf_label}: <b>{zona}</b><br>"
                "Cumplimiento: <b>%{y:.1f}%</b><br>"
                "Meta: <b>80%</b><br>"
                "Brecha vs meta: <b>%{customdata:.1f} pp</b>"
                "<extra></extra>"
            ),
            customdata=(d["Cumple"] - 80).round(1)
        ))

    # Resumen ejecutivo discreto en la esquina superior derecha.
    promedio_graf = float(graf["Cumple"].mean()) if len(graf) else 0
    brecha_graf = promedio_graf - 80
    color_brecha = VERDE if brecha_graf >= 0 else NARANJO

    fig.add_annotation(
        visible=False,
        xref="paper",
        yref="paper",
        x=0.985,
        y=1.085,
        xanchor="right",
        yanchor="top",
        showarrow=False,
        align="right",
        text=(
            "<span style='font-size:11px;color:#64748B'>PROMEDIO FILTRADO</span><br>"
            f"<span style='font-size:22px;color:{color_brecha}'><b>{promedio_graf:.1f}%</b></span><br>"
            f"<span style='font-size:10px;color:#64748B'>Brecha: {brecha_graf:+.1f} pp</span>"
        ),
        bgcolor="rgba(6,18,34,0.88)",
        bordercolor="rgba(46,203,242,0.30)",
        borderwidth=1,
        borderpad=8
    )

    # Marcadores ejecutivos: mejor y peor punto sin invadir el título.
    if len(graf):
        mejor = graf.loc[graf["Cumple"].idxmax()]
        critico = graf.loc[graf["Cumple"].idxmin()]

        fig.add_annotation(
            x=mejor["Mes"],
            y=mejor["Cumple"],
            text="Máximo",
            showarrow=True,
            arrowhead=2,
            arrowsize=1,
            arrowwidth=1.4,
            arrowcolor=VERDE,
            ax=22,
            ay=-42,
            font=dict(size=11, color="#EAFBFF", family="Segoe UI Semibold"),
            bgcolor="rgba(6,18,34,0.90)",
            bordercolor="rgba(71,225,144,0.50)",
            borderwidth=1,
            borderpad=4
        )

        fig.add_annotation(
            x=critico["Mes"],
            y=critico["Cumple"],
            text="Mínimo",
            showarrow=True,
            arrowhead=2,
            arrowsize=1,
            arrowwidth=1.4,
            arrowcolor=NARANJO,
            ax=-24,
            ay=38,
            font=dict(size=11, color="#EAFBFF", family="Segoe UI Semibold"),
            bgcolor="rgba(6,18,34,0.90)",
            bordercolor="rgba(255,61,0,0.45)",
            borderwidth=1,
            borderpad=4
        )

    fig.update_layout(
        height=420 if (SERVICIO_ACTUAL == "SAO" and not SERVICIO_COMPARATIVO and len(regiones_graf) > 4) else 330,
        hovermode="x unified",
        paper_bgcolor="rgba(255,255,255,0)",
        plot_bgcolor="rgba(6,18,34,0.74)",
        margin=dict(l=52, r=34, t=62, b=42),
        legend=dict(
            orientation="h",
            x=0.5,
            xanchor="center",
            y=1.085,
            yanchor="top",
            bgcolor="rgba(6,18,34,0.82)",
            bordercolor="rgba(46,203,242,0.42)",
            borderwidth=1,
            font=dict(size=11 if (SERVICIO_ACTUAL == "SAO" and not SERVICIO_COMPARATIVO) else 13, family="Segoe UI Semibold", color="#EAFBFF"),
            itemwidth=130 if (SERVICIO_ACTUAL == "SAO" and not SERVICIO_COMPARATIVO) else 170
        ),
        hoverlabel=dict(
            bgcolor="rgba(6,18,34,0.94)",
            bordercolor="rgba(46,203,242,0.36)",
            font=dict(size=12, family="Segoe UI", color="#EAFBFF")
        ),
        transition=dict(duration=0)
    )

    fig.update_xaxes(
        title=None,
        showgrid=False,
        zeroline=False,
        tickfont=dict(size=14, family="Segoe UI Semibold", color="#DDFBFF"),
        showline=True,
        linecolor="rgba(143,239,255,0.20)",
        linewidth=1,
        ticks=""
    )

    fig.update_yaxes(
        title=None,
        range=[0, 105],
        ticksuffix="%",
        dtick=20,
        showgrid=True,
        gridcolor="rgba(143,239,255,0.14)",
        zeroline=False,
        tickfont=dict(size=13, family="Segoe UI", color="#BDEFFF"),
        showline=False
    )

    st.plotly_chart(
        fig,
        width="stretch",
        config=PLOTLY_CONFIG_SOLO_LECTURA
    )





if mostrar_kpi_inicio:
    # =========================================================
    # ESTADO FINAL DE ATENCIONES - PLOTLY PREMIUM BALANCEADO
    # =========================================================

    st.markdown('<div class="estado-final-heading"><h2 class="kpi-title">Estado final de atenciones</h2><div class="kpi-divider"></div></div>', unsafe_allow_html=True)

    def fmt_num(valor):
        return f"{int(valor):,}".replace(",", ".")


    def kpi_plotly(titulo, valor, porcentaje, color, icono, subtitulo, compact=False):
        """Tarjeta KPI premium en Plotly. No usa HTML para evitar que se muestre código."""
        fig_kpi = go.Figure()
        accent = "#2D8CFF" if str(color).upper() == str(AZUL).upper() else color

        fig_kpi.add_shape(
            type="rect",
            x0=0,
            y0=0,
            x1=1,
            y1=1,
            xref="paper",
            yref="paper",
            fillcolor="rgba(7,18,34,0.94)",
            line=dict(color=rgba(accent, 0.58), width=1.35),
            layer="below"
        )

        fig_kpi.add_shape(
            type="rect",
            x0=0,
            y0=0.955,
            x1=1,
            y1=1,
            xref="paper",
            yref="paper",
            fillcolor=accent,
            line=dict(width=0),
            layer="below"
        )

        fig_kpi.add_shape(
            type="circle",
            x0=0.055,
            y0=0.59,
            x1=0.17,
            y1=0.86,
            xref="paper",
            yref="paper",
            fillcolor=rgba(accent, 0.26),
            line=dict(color=rgba(accent, 0.72), width=1.25),
            layer="below"
        )

        fig_kpi.add_annotation(
            x=0.112,
            y=0.725,
            text=icono,
            showarrow=False,
            font=dict(size=17, color="#FFFFFF", family="Arial Black")
        )

        fig_kpi.add_annotation(
            x=0.22,
            y=0.72,
            xanchor="left",
            text=titulo,
            showarrow=False,
            font=dict(size=10 if compact else 12, color="#EAFBFF", family="Segoe UI Semibold")
        )

        fig_kpi.add_annotation(
            x=0.22,
            y=0.43,
            xanchor="left",
            text=fmt_num(valor),
            showarrow=False,
            font=dict(size=21 if compact else 26, color="#F8FAFC", family="Arial Black")
        )

        fig_kpi.add_annotation(
            x=0.94,
            y=0.43,
            xanchor="right",
            text=f"{porcentaje:.1f}%",
            showarrow=False,
            font=dict(size=16 if compact else 19, color=accent, family="Arial Black")
        )

        fig_kpi.add_annotation(
            x=0.22,
            y=0.17,
            xanchor="left",
            text=subtitulo,
            showarrow=False,
            font=dict(size=8 if compact else 9, color="#9BD7EA", family="Segoe UI Semibold")
        )

        fig_kpi.update_xaxes(visible=False, range=[0, 1], fixedrange=True)
        fig_kpi.update_yaxes(visible=False, range=[0, 1], fixedrange=True)
        fig_kpi.update_layout(
            height=76 if compact else 84,
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)"
        )

        return fig_kpi


    def encabezado_plotly(titulo):
        """Encabezado del panel de distribución, hecho en Plotly para mantener el mismo estilo."""
        fig_head = go.Figure()

        fig_head.add_shape(
            type="rect",
            x0=0,
            y0=0,
            x1=1,
            y1=1,
            xref="paper",
            yref="paper",
            fillcolor="rgba(7,18,34,0.88)",
            line=dict(color="rgba(46,203,242,0.44)", width=1.1),
            layer="below"
        )

        fig_head.add_shape(
            type="rect",
            x0=0,
            y0=0.90,
            x1=1,
            y1=1,
            xref="paper",
            yref="paper",
            fillcolor=AZUL,
            line=dict(width=0),
            layer="below"
        )

        fig_head.add_annotation(
            x=0.03,
            y=0.48,
            xanchor="left",
            text=titulo,
            showarrow=False,
            font=dict(size=14, color="#DDFBFF", family="Segoe UI Semibold")
        )

        fig_head.update_xaxes(visible=False, range=[0, 1], fixedrange=True)
        fig_head.update_yaxes(visible=False, range=[0, 1], fixedrange=True)
        fig_head.update_layout(
            height=34,
            margin=dict(l=0, r=0, t=0, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)"
        )

        return fig_head


    left, right = st.columns([0.42, 0.58], gap="medium")

    with left:
        st.plotly_chart(
            encabezado_plotly("Distribución de atenciones"),
            width="stretch",
            config=PLOTLY_CONFIG_SOLO_LECTURA
        )

        pie = go.Figure()

        # Donut con profundidad simulada: sombra inferior + base + anillo principal.
        pie.add_trace(
            go.Pie(
                labels=["Finalizadas", "No finalizadas"],
                values=[finalizadas, no_finalizadas],
                hole=0.61,
                sort=False,
                direction="clockwise",
                rotation=90,
            domain=dict(x=[0.160, 0.840], y=[0.015, 0.825]),
                textinfo="none",
                hoverinfo="skip",
                marker=dict(
                    colors=[rgba(AZUL, 0.20), rgba(ROSADO, 0.20)],
                    line=dict(color="rgba(0,0,0,0)", width=0)
                ),
                showlegend=False
            )
        )

        pie.add_trace(
            go.Pie(
                labels=["Finalizadas", "No finalizadas"],
                values=[finalizadas, no_finalizadas],
                hole=0.61,
                sort=False,
                direction="clockwise",
                rotation=90,
                domain=dict(x=[0.160, 0.840], y=[0.055, 0.865]),
                textinfo="none",
                hoverinfo="skip",
                marker=dict(
                    colors=["#064AD8", "#D84C7D"],
                    line=dict(color="rgba(255,255,255,0.20)", width=1.2)
                ),
                showlegend=False
            )
        )

        pie.add_trace(
            go.Pie(
                labels=["Finalizadas", "No finalizadas"],
                values=[finalizadas, no_finalizadas],
                hole=0.64,
                sort=False,
                direction="clockwise",
                rotation=90,
                domain=dict(x=[0.160, 0.840], y=[0.105, 0.940]),
                texttemplate="<b>%{percent:.1%}</b>",
                textposition="inside",
                insidetextorientation="horizontal",
                textfont=dict(size=11, color="#FFFFFF", family="Segoe UI Black"),
                marker=dict(
                    colors=[AZUL_CLARO, ROSADO],
                    line=dict(color="#FFFFFF", width=3.2)
                ),
                pull=[0.008, 0.014],
                showlegend=True,
                hovertemplate="%{label}<br>Cantidad: %{value}<br>Participación: %{percent}<extra></extra>"
            )
        )

        pie.add_annotation(
            x=0.5,
            y=0.505,
            text=f"<b>{fmt_num(total_atenciones)}</b>",
            showarrow=False,
            font=dict(size=31, color=CELESTE, family="Segoe UI Black")
        )

        pie.add_annotation(
            x=0.5,
            y=0.405,
            text="<b>Atenciones</b>",
            showarrow=False,
            font=dict(size=12, color="#BDEFFF", family="Segoe UI Semibold")
        )

        pie.update_layout(
            height=230,
            paper_bgcolor="rgba(255,255,255,0)",
            plot_bgcolor="rgba(6,18,34,0.72)",
            margin=dict(t=20, b=6, l=8, r=8),
            showlegend=True,
            legend=dict(
                orientation="h",
                x=0.5,
                xanchor="center",
                y=1.02,
                yanchor="bottom",
                font=dict(size=10, family="Segoe UI Semibold", color="#EAFBFF"),
                bgcolor="rgba(6,18,34,0.84)",
                bordercolor="rgba(46,203,242,0.40)",
                borderwidth=1
            ),
            uniformtext=dict(minsize=10, mode="hide")
        )

        st.plotly_chart(pie, width="stretch", config=PLOTLY_CONFIG_SOLO_LECTURA)

    with right:
        motivo_col = next(
            (c for c in ["Motivo de no realización", "Motivo", "Resultado", "Acción Realizada", "Observación"] if c in df_f.columns),
            None
        )

        if motivo_col:
            motivos_limpios = df_f.loc[~estado.str.contains("FINAL", na=False), motivo_col].fillna("Otros")
            base = consolidar_motivos_no_realizado(motivos_limpios).head(8)
        else:
            base = pd.Series(dtype=int)

        st.plotly_chart(
            encabezado_plotly("Motivo de No Realizado"),
            width="stretch",
            config=PLOTLY_CONFIG_SOLO_LECTURA
        )

        if len(base):
            pct_motivos = (base / base.sum() * 100).round(1)
            max_x = max(base.values) if len(base) else 1

            bar = go.Figure(
                go.Bar(
                    x=base.values,
                    y=base.index,
                    orientation="h",
                    text=[f"{v} ({p}%)" for v, p in zip(base.values, pct_motivos)],
                    textposition="outside",
                    cliponaxis=False,
                    textfont=dict(size=12, color="#EAFBFF", family="Segoe UI Semibold"),
                    marker=dict(color=ROSADO, line=dict(color="#FFFFFF", width=1.3)),
                    hovertemplate="%{y}<br>Cantidad: %{x}<extra></extra>"
                )
            )

            bar.update_layout(
                height=230,
                margin=dict(t=12, b=24, l=14, r=86),
                paper_bgcolor="rgba(255,255,255,0)",
                plot_bgcolor="rgba(6,18,34,0.72)",
                xaxis=dict(
                    range=[0, max_x * 1.15],
                    showgrid=True,
                    gridcolor="rgba(143,239,255,0.14)",
                    zeroline=False,
                    tickfont=dict(size=11, color="#BDEFFF", family="Segoe UI Semibold")
                ),
                yaxis=dict(
                    autorange="reversed",
                    automargin=True,
                    tickfont=dict(size=12, color="#EAFBFF", family="Segoe UI Semibold")
                ),
                showlegend=False
            )

            st.plotly_chart(bar, width="stretch", config=PLOTLY_CONFIG_SOLO_LECTURA)
        else:
            st.info("No hay motivos de no realización para los filtros aplicados.")

    estado_cards = st.columns([1, 1, 1, 1.18], gap="small")

    with estado_cards[0]:
        st.plotly_chart(
            kpi_plotly("Finalizadas", finalizadas, pct_fin, AZUL_CLARO, "✓", "Del total filtrado", compact=True),
            width="stretch",
            config=PLOTLY_CONFIG_SOLO_LECTURA
        )

    with estado_cards[1]:
        st.plotly_chart(
            kpi_plotly("No finalizadas", no_finalizadas, pct_no_fin, ROSADO, "!", "Del total filtrado", compact=True),
            width="stretch",
            config=PLOTLY_CONFIG_SOLO_LECTURA
        )

    with estado_cards[2]:
        st.plotly_chart(
            kpi_plotly(
                "Total no finalizadas",
                no_finalizadas,
                pct_no_fin,
                ROSADO,
                "!",
                "Base del gráfico de motivos",
                compact=True
            ),
            width="stretch",
            config=PLOTLY_CONFIG_SOLO_LECTURA
        )

    with estado_cards[3]:
        revisita_kpi_col, revisita_export_col = st.columns([0.86, 0.14], gap="small")
        with revisita_kpi_col:
            st.plotly_chart(
                kpi_plotly(
                    "Revisitas",
                    revisitas,
                    pct_revisitas,
                    CELESTE,
                    "R",
                    "Del total filtrado",
                    compact=True
                ),
                width="stretch",
                config=PLOTLY_CONFIG_SOLO_LECTURA
            )
        with revisita_export_col:
            render_boton_revisitas(df_revisitas_export, filtros_export)

    st.markdown(
        """
        <div class="estado-info-note">
            <span class="info-icon">i</span>
            <span>Estado final de las atenciones según los filtros aplicados.</span>
        </div>
        """,
        unsafe_allow_html=True
    )


# =========================================================
# FOOTER
# =========================================================


st.markdown("---")

st.caption(
    f"Última actualización: "
    f"{datetime.now().strftime('%d-%m-%Y %H:%M')} | {APP_OWNER}"
)


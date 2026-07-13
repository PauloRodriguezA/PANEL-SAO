from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import Any


REGION_LABELS = {
    "ARICA": "Región de Arica y Parinacota",
    "TARAPACA": "Región de Tarapacá",
    "ANTOFAGASTA": "Región de Antofagasta",
    "ATACAMA": "Región de Atacama",
    "COQUIMBO": "Región de Coquimbo",
    "VALPARAISO": "Región de Valparaíso",
    "METROPOLITANA": "Región Metropolitana",
    "OHIGGINS": "Región de O'Higgins",
    "MAULE": "Región del Maule",
    "NUBLE": "Región de Ñuble",
    "BIOBIO": "Región del Biobío",
    "ARAUCANIA": "Región de La Araucanía",
    "LOS RIOS": "Región de Los Ríos",
    "LOS LAGOS": "Región de Los Lagos",
    "AYSEN": "Región de Aysén",
    "MAGALLANES": "Región de Magallanes",
}

REGION_ALIASES = {
    "ARICA": ["ARICA", "PARINACOTA", "XV REGION"],
    "TARAPACA": ["TARAPACA", "I REGION", "IQUIQUE", "ALTO HOSPICIO"],
    "ANTOFAGASTA": ["ANTOFAGASTA", "II REGION", "CALAMA", "TOCOPILLA", "MEJILLONES"],
    "ATACAMA": ["ATACAMA", "III REGION", "COPIAPO", "VALLENAR"],
    "COQUIMBO": ["COQUIMBO", "IV REGION", "LA SERENA", "SERENA", "OVALLE", "ILLAPEL"],
    "VALPARAISO": ["VALPARAISO", "V REGION", "VINA DEL MAR", "QUILLOTA", "LOS ANDES", "SAN FELIPE"],
    "METROPOLITANA": ["METROPOLITANA", "XIII REGION", "REGION RM", "SANTIAGO", "PROVIDENCIA"],
    "OHIGGINS": ["OHIGGINS", "O HIGGINS", "VI REGION", "RANCAGUA", "MACHALI"],
    "MAULE": ["MAULE", "VII REGION", "TALCA", "CURICO", "LINARES"],
    "NUBLE": ["NUBLE", "AUBLE", "XVI REGION", "CHILLAN"],
    "BIOBIO": ["BIO BIO", "BIOBIO", "BIO BAO", "BIOBAO", "VIII REGION", "CONCEPCION", "LOS ANGELES", "CANETE"],
    "ARAUCANIA": ["ARAUCANIA", "ARAUCANAA", "IX REGION", "TEMUCO", "VILLARRICA"],
    "LOS RIOS": ["LOS RIOS", "XIV REGION", "VALDIVIA"],
    "LOS LAGOS": ["LOS LAGOS", "X REGION", "PUERTO MONTT", "OSORNO", "CASTRO", "QUELLON"],
    "AYSEN": ["AYSEN", "XI REGION", "COYHAIQUE"],
    "MAGALLANES": ["MAGALLANES", "XII REGION", "PUNTA ARENAS"],
}

COMUNA_REGION = {
    "ARICA": "ARICA",
    "IQUIQUE": "TARAPACA",
    "ALTO HOSPICIO": "TARAPACA",
    "POZO ALMONTE": "TARAPACA",
    "ANTOFAGASTA": "ANTOFAGASTA",
    "CALAMA": "ANTOFAGASTA",
    "TOCOPILLA": "ANTOFAGASTA",
    "MEJILLONES": "ANTOFAGASTA",
    "TALTAL": "ANTOFAGASTA",
    "COPIAPO": "ATACAMA",
    "VALLENAR": "ATACAMA",
    "CHAÑARAL": "ATACAMA",
    "CHANARAL": "ATACAMA",
    "LA SERENA": "COQUIMBO",
    "SERENA": "COQUIMBO",
    "COQUIMBO": "COQUIMBO",
    "OVALLE": "COQUIMBO",
    "ILLAPEL": "COQUIMBO",
    "VALPARAISO": "VALPARAISO",
    "VINA DEL MAR": "VALPARAISO",
    "VIÑA DEL MAR": "VALPARAISO",
    "QUILLOTA": "VALPARAISO",
    "LOS ANDES": "VALPARAISO",
    "SAN FELIPE": "VALPARAISO",
    "SANTIAGO": "METROPOLITANA",
    "LA FLORIDA": "METROPOLITANA",
    "PROVIDENCIA": "METROPOLITANA",
    "LAS CONDES": "METROPOLITANA",
    "LA REINA": "METROPOLITANA",
    "PUENTE ALTO": "METROPOLITANA",
    "MAIPU": "METROPOLITANA",
    "TALAGANTE": "METROPOLITANA",
    "RANCAGUA": "OHIGGINS",
    "MACHALI": "OHIGGINS",
    "SAN FERNANDO": "OHIGGINS",
    "TALCA": "MAULE",
    "CURICO": "MAULE",
    "LINARES": "MAULE",
    "CHILLAN": "NUBLE",
    "CHILLAN VIEJO": "NUBLE",
    "BULNES": "NUBLE",
    "COBQUECURA": "NUBLE",
    "COELEMU": "NUBLE",
    "COIHUECO": "NUBLE",
    "EL CARMEN": "NUBLE",
    "NINHUE": "NUBLE",
    "NIQUEN": "NUBLE",
    "PEMUCO": "NUBLE",
    "PINTO": "NUBLE",
    "PORTEZUELO": "NUBLE",
    "QUILLON": "NUBLE",
    "QUIRIHUE": "NUBLE",
    "RANQUIL": "NUBLE",
    "SAN CARLOS": "NUBLE",
    "SAN FABIAN": "NUBLE",
    "SAN NICOLAS": "NUBLE",
    "TREGUACO": "NUBLE",
    "YUNGAY": "NUBLE",
    "CONCEPCION": "BIOBIO",
    "LOS ANGELES": "BIOBIO",
    "CANETE": "BIOBIO",
    "CAÑETE": "BIOBIO",
    "ANTUCO": "BIOBIO",
    "ARAUCO": "BIOBIO",
    "CABRERO": "BIOBIO",
    "CHIGUAYANTE": "BIOBIO",
    "CONTULMO": "BIOBIO",
    "CORONEL": "BIOBIO",
    "CURANILAHUE": "BIOBIO",
    "FLORIDA": "BIOBIO",
    "HUALPEN": "BIOBIO",
    "HUALQUI": "BIOBIO",
    "LAJA": "BIOBIO",
    "LEBU": "BIOBIO",
    "LOS ALAMOS": "BIOBIO",
    "LOTA": "BIOBIO",
    "MULCHEN": "BIOBIO",
    "NACIMIENTO": "BIOBIO",
    "NEGRETE": "BIOBIO",
    "PENCO": "BIOBIO",
    "QUILACO": "BIOBIO",
    "QUILLECO": "BIOBIO",
    "SAN PEDRO DE LA PAZ": "BIOBIO",
    "SAN ROSENDO": "BIOBIO",
    "SANTA BARBARA": "BIOBIO",
    "SANTA JUANA": "BIOBIO",
    "TALCAHUANO": "BIOBIO",
    "TIRUA": "BIOBIO",
    "TOME": "BIOBIO",
    "TUCAPEL": "BIOBIO",
    "YUMBEL": "BIOBIO",
    "TEMUCO": "ARAUCANIA",
    "VILLARRICA": "ARAUCANIA",
    "VALDIVIA": "LOS RIOS",
    "LOS LAGOS": "LOS RIOS",
    "PUERTO MONTT": "LOS LAGOS",
    "OSORNO": "LOS LAGOS",
    "CASTRO": "LOS LAGOS",
    "QUELLON": "LOS LAGOS",
    "COYHAIQUE": "AYSEN",
    "PUNTA ARENAS": "MAGALLANES",
}

# Comunas y localidades que aparecen realmente en WFM. La ciudad manda sobre
# una region heredada incorrecta (por ejemplo, Camina nunca es Metropolitana).
COMUNAS_OPERACIONALES_POR_REGION = {
    "ARICA": (
        "CAMARONES", "PUTRE", "GENERAL LAGOS",
    ),
    "TARAPACA": (
        "CAMINA", "COLCHANE", "HUARA", "PICA",
    ),
    "ANTOFAGASTA": (
        "MARIA ELENA", "SAN PEDRO DE ATACAMA",
    ),
    "ATACAMA": (
        "CALDERA", "DIEGO DE ALMAGRO", "HUASCO", "TIERRA AMARILLA",
    ),
    "COQUIMBO": (
        "ANDACOLLO", "COMBARBALA", "LA HIGUERA", "LOS VILOS", "MONTE PATRIA",
        "PAIHUANO", "PAIGUANO", "PUNITAQUI", "RIO HURTADO", "SALAMANCA", "VICUNA",
    ),
    "VALPARAISO": (
        "ALGARROBO", "CABILDO", "CALERA", "CARTAGENA", "CATEMU", "CONCON",
        "EL QUISCO", "EL TABO", "LA CALERA", "LA CRUZ", "LA LIGUA", "LIMACHE",
        "LLAILLAY", "NOGALES", "PANQUEHUE", "PAPUDO", "PETORCA", "PUCHUNCAVI",
        "PUTAENDO", "QUILPUE", "QUINTERO", "RENACA", "SAN ANTONIO", "SAN ESTEBAN",
        "SANTA MARIA", "VILLA ALEMANA", "VILLA ALMEMANA",
    ),
    "OHIGGINS": (
        "CHIMBARONGO", "CODEGUA", "COINCO", "COLTAUCO", "DONIHUE", "GRANEROS",
        "LA ESTRELLA", "LAS CABRAS", "LITUECHE", "MARCHIGUE", "MARCHIHUE",
        "MOSTAZAL", "NANCAGUA", "NAVIDAD", "OLIVAR", "PALMILLA", "PAREDONES",
        "PERALILLO", "PEUMO", "PICHIDEGUA", "PICHILEMU", "PLACILLA", "PUMANQUE",
        "QUINTA DE TILCOCO", "RENGO", "REQUEGUA", "REQUINOA", "ROSARIO",
        "SAN VICENTE", "SAN VICENTE DE TAGUA TAGUA", "SANTA CRUZ",
    ),
    "MAULE": (
        "CAUQUENES", "CHANCO", "CONSTITUCION", "CURANIPE", "CUREPTO", "EMPEDRADO",
        "HUALANE", "LICANTEN", "LLICO DE MATAQUITO", "LONTUE", "LONGAVI", "MOLINA",
        "PARRAL", "PELARCO", "PELLUHUE", "PENCAHUE", "RIO CLARO", "ROMERAL",
        "SAGRADA FAMILIA", "SAN CLEMENTE", "SAN JAVIER", "SAN RAFAEL", "SARMIENTO",
        "TENO", "VICHUQUEN", "VILLA ALEGRE", "YERBAS BUENAS",
    ),
    "NUBLE": (
        "SAN IGNACIO",
    ),
    "BIOBIO": (
        "ALTO BIOBIO", "ISLA SANTA MARIA", "SANTA FE",
    ),
    "ARAUCANIA": (
        "ANGOL", "CARAHUE", "CAUTIN", "CHOLCHOL", "COLLIPULLI", "CUNCO",
        "CURACAUTIN", "ERCILLA", "FREIRE", "GALVARINO", "GORBEA", "LAUTARO",
        "LONCOCHE", "LOS SAUCES", "LUMACO", "MELIPEUCO", "NUEVA IMPERIAL",
        "PADRE LAS CASAS", "PITRUFQUEN", "PUCON", "RENAICO", "SAAVEDRA",
        "TEODORO SCHMIDT", "TRAIGUEN", "VICTORIA", "VILCUN",
    ),
    "LOS RIOS": (
        "FUTRONO", "LA UNION", "LAGO RANCO", "MAFIL", "MARIQUINA", "PAILLACO",
        "PANGUIPULLI", "RIO BUENO",
    ),
    "LOS LAGOS": (
        "ACHAO", "ALERCE", "ANCUD", "CALBUCO", "CHAITEN", "COCHAMO", "CORRENTOSO",
        "CURACO DE VELEZ", "DALCAHUE", "LLANQUIHUE", "LOS MUERMOS", "MAULLIN",
        "PADRE HURTADO MIRASOL", "PUAUCHO", "PUERTO OCTAY", "PUERTO VARAS",
        "PUQUELDON", "PUYEHUE", "QUEMCHI", "QUINCHAO", "RIO NEGRO",
        "SAN JUAN DE LA COSTA",
    ),
    "AYSEN": (
        "CHILE CHICO", "COCHRANE", "GUAITECAS", "MANIHUALES", "RIO IBANEZ",
    ),
    "MAGALLANES": (
        "CABO DE HORNOS", "NATALES", "PORVENIR", "PUERTO NATALES", "RIO SECO",
        "TORRES DEL PAINE",
    ),
    "METROPOLITANA": (
        "ALHUE", "BUIN", "CALERA DE TANGO", "CERRILLOS", "COLINA", "CONCHALI",
        "CURACAVI", "ESTACION CENTRAL", "HUECHURABA", "INDEPENDENCIA", "LA CISTERNA",
        "LA GRANJA", "LA PINTANA", "LAMPA", "LO BARNECHEA", "LO ESPEJO", "LO PRADO",
        "LONGOVILO", "LONQUEN", "MACUL", "MAIPO", "MELIPILLA", "PADRE HURTADO",
        "PAINE", "PEDRO AGUIRRE CERDA", "PENAFLOR", "PENALOLEN", "PIRQUE", "PUDAHUEL",
        "QUILICURA", "QUINTA NORMAL", "RECOLETA", "SAN BERNARDO", "SAN JOAQUIN",
        "SAN JOSE DE MAIPO", "SAN MIGUEL", "SAN PEDRO", "TILTIL", "VITACURA", "NUNOA",
    ),
}

for _region_key, _comunas in COMUNAS_OPERACIONALES_POR_REGION.items():
    COMUNA_REGION.update({_comuna: _region_key for _comuna in _comunas})


@lru_cache(maxsize=4096)
def reparar_mojibake(valor: Any) -> str:
    texto = "" if valor is None else str(valor)
    for _ in range(2):
        if not any(marca in texto for marca in ("Ã", "Â", "â")):
            break
        try:
            reparado = texto.encode("latin1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if reparado == texto:
            break
        texto = reparado
    return texto


@lru_cache(maxsize=4096)
def normalizar_texto(valor: Any) -> str:
    texto = reparar_mojibake(valor).upper().strip().replace("\xa0", " ")
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    texto = re.sub(r"[^A-Z0-9]+", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return "" if texto in {"", "NAN", "NONE", "NULL", "NA"} else texto


@lru_cache(maxsize=4096)
def normalizar_region_chile(valor: Any) -> str:
    norm = normalizar_texto(valor)
    if not norm:
        return ""
    for key, aliases in REGION_ALIASES.items():
        for alias in aliases:
            alias_norm = normalizar_texto(alias)
            if re.search(rf"(?<![A-Z0-9]){re.escape(alias_norm)}(?![A-Z0-9])", norm):
                return REGION_LABELS[key]
    return reparar_mojibake(valor).strip()


@lru_cache(maxsize=4096)
def region_desde_ciudad(ciudad: Any) -> str:
    norm = normalizar_texto(ciudad)
    if not norm:
        return ""
    for comuna, region_key in sorted(COMUNA_REGION.items(), key=lambda item: len(item[0]), reverse=True):
        comuna_norm = normalizar_texto(comuna)
        if re.search(rf"(?<![A-Z0-9]){re.escape(comuna_norm)}(?![A-Z0-9])", norm):
            return REGION_LABELS[region_key]
    region = normalizar_region_chile(norm)
    return region if normalizar_texto(region).startswith("REGION ") else ""


@lru_cache(maxsize=8192)
def region_por_ciudad_o_comuna(ciudad: Any, region_actual: Any = "") -> str:
    por_ciudad = region_desde_ciudad(ciudad)
    if por_ciudad:
        return por_ciudad
    por_region = normalizar_region_chile(region_actual)
    return por_region or str(region_actual or "").strip()


def corregir_region_por_ciudad(df: Any, ciudad_col: str = "Ciudad", region_col: str = "Estado") -> Any:
    if df is None or ciudad_col not in df.columns or region_col not in df.columns:
        return df
    df[region_col] = [
        region_por_ciudad_o_comuna(ciudad, region)
        for ciudad, region in zip(df[ciudad_col].fillna(""), df[region_col].fillna(""))
    ]
    return df

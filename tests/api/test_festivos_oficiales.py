"""Municipio del centro y festivos oficiales en línea (las fuentes se simulan)."""

import pytest

from turnos.servicios import festivos_oficiales

FESTIVOS_IO_2026 = {
    "attribution": "festivos.io — CC BY 4.0",
    "holidays": [
        {"date": "2026-01-01", "name": {"es": "Año Nuevo"}, "level": "national",
         "source": {"ref": "BOE-A-2025-21667", "url": "https://www.boe.es/diario_boe/txt.php?id=BOE-A-2025-21667"}},
        {"date": "2026-05-15", "name": {"es": "San Isidro"}, "level": "local",
         "source": {"ref": "Comunidad de Madrid — Festivos locales (datos abiertos)", "url": "https://datos.comunidad.madrid/x"}},
        {"date": "2026-11-09", "name": {"es": "La Almudena"}, "level": "local", "source": {"ref": "BOCM"}},
        {"date": "2026-11-02", "name": {"es": "Día siguiente a Todos los Santos"}, "level": "regional", "source": {}},
    ],
}
MADRID_LOCALES = {"data": [
    {"municipio_codigo": "079", "entidad_codigo": "00", "municipio_nombre": "Madrid", "año": "2027", "fecha_festivo": "2027-05-15"},
    {"municipio_codigo": "079", "entidad_codigo": "00", "municipio_nombre": "Madrid", "año": "2027", "fecha_festivo": "2027-11-09"},
    {"municipio_codigo": "005", "entidad_codigo": "00", "municipio_nombre": "Alcalá de Henares", "año": "2027", "fecha_festivo": "2027-08-06"},
]}


@pytest.fixture
def fuentes(monkeypatch):
    """Respuestas simuladas por dirección; None = 404; una excepción = sin conexión."""
    respuestas = {}
    pedidas = []

    def descargar(url):
        pedidas.append(url)
        valor = respuestas.get(url)
        if isinstance(valor, Exception):
            raise valor
        return valor

    monkeypatch.setattr(festivos_oficiales, "descargar_json", descargar)
    respuestas["pedidas"] = pedidas
    return respuestas


def io(anio, ine="28079"):
    return festivos_oficiales.FESTIVOS_IO.format(anio=anio, ine=ine)


def test_buscar_municipios_sin_tildes_y_primero_los_que_empiezan(cliente):
    nombres = [m["nombre"] for m in cliente.get("/api/festivos/municipios", params={"q": "alcobend"}).json()]
    assert nombres[0] == "Alcobendas"
    alcala = cliente.get("/api/festivos/municipios", params={"q": "alcala de hen"}).json()
    assert alcala[0] == {"ine": "28005", "nombre": "Alcalá de Henares", "provincia": "Madrid",
                         "ccaa": "ES-MD", "ccaa_nombre": "Comunidad de Madrid"}
    assert cliente.get("/api/festivos/municipios", params={"q": " "}).json() == []
    assert cliente.get("/api/festivos/municipios/28079").json()["nombre"] == "Madrid"
    assert cliente.get("/api/festivos/municipios/00000").status_code == 404


def test_buscar_compara_con_los_festivos_guardados(cliente, fuentes):
    fuentes[io(2026)] = FESTIVOS_IO_2026
    r = cliente.get("/api/festivos/oficiales/2026")
    assert r.status_code == 200
    datos = r.json()
    assert datos["municipio"]["nombre"] == "Madrid"
    assert datos["completo"]
    estados = {f["fecha"]: (f["estado"], f["ambito"], f["fuente"]) for f in datos["festivos"]}
    # Los precargados de 2026 ya tienen esas fechas: 1 de enero igual; el local se llama
    # «San Isidro Labrador», así que el nombre oficial es distinto.
    assert estados["2026-01-01"] == ("IGUAL", "NACIONAL", "BOE-A-2025-21667")
    assert estados["2026-05-15"][0] == "DISTINTO"
    assert estados["2026-11-02"][1] == "AUTONOMICO"
    # Los precargados que no están en la respuesta simulada.
    assert "2026-12-25" in {f["fecha"] for f in datos["solo_en_tus_datos"]}
    # No hace falta la fuente de Madrid: ya hay dos locales.
    assert fuentes["pedidas"] == [io(2026)]


def test_cargar_solo_anade_los_que_faltan_y_marca_el_anio(cliente, fuentes):
    fuentes[io(2030)] = {"holidays": [
        {"date": "2030-01-01", "name": {"es": "Año Nuevo"}, "level": "national", "source": {"ref": "BOE"}},
        {"date": "2030-05-15", "name": {"es": "San Isidro"}, "level": "local", "source": {"ref": "BOCM"}},
        {"date": "2030-11-09", "name": {"es": "La Almudena"}, "level": "local", "source": {"ref": "BOCM"}},
    ]}
    cliente.post("/api/festivos", json={"fecha": "2030-01-01", "descripcion": "Puesto a mano", "ambito": "OTRO"})
    anadidos = cliente.post("/api/festivos/oficiales/2030").json()
    assert [f["fecha"] for f in anadidos] == ["2030-05-15", "2030-11-09"]
    festivos = {f["fecha"]: f["descripcion"] for f in cliente.get("/api/festivos", params={"anio": 2030}).json()}
    assert festivos["2030-01-01"] == "Puesto a mano"  # no se cambia lo que había
    anio = next(a for a in cliente.get("/api/festivos/anios").json() if a["anio"] == 2030)
    assert anio == {"anio": 2030, "calendario": "oficial:28079", "completo": True, "precargado": False}
    assert cliente.post("/api/festivos/oficiales/2030").json() == []


def test_locales_de_madrid_si_la_fuente_principal_no_tiene_el_anio(cliente, fuentes):
    fuentes[io(2027)] = None  # 404
    fuentes[festivos_oficiales.MADRID_LOCALES] = MADRID_LOCALES
    datos = cliente.get("/api/festivos/oficiales/2027").json()
    assert [(f["fecha"], f["ambito"]) for f in datos["festivos"]] == [("2027-05-15", "LOCAL"), ("2027-11-09", "LOCAL")]
    assert datos["completo"]
    assert datos["fuentes"] == ["Comunidad de Madrid, datos abiertos (CC BY)"]


def test_sin_conexion_y_anio_sin_publicar(cliente, fuentes):
    error = OSError("sin red")
    fuentes[io(2026)] = error
    fuentes[festivos_oficiales.MADRID_LOCALES] = error
    r = cliente.get("/api/festivos/oficiales/2026")
    assert r.status_code == 502
    assert "No se ha podido consultar ninguna fuente" in r.json()["detail"]

    fuentes[io(2031)] = None
    fuentes[festivos_oficiales.MADRID_LOCALES] = {"data": []}
    datos = cliente.get("/api/festivos/oficiales/2031").json()
    assert datos["festivos"] == [] and not datos["completo"]
    assert any("Aún no hay festivos publicados" in a for a in datos["avisos"])
    assert cliente.post("/api/festivos/oficiales/2031").json() == []
    assert 2031 not in [a["anio"] for a in cliente.get("/api/festivos/anios").json()]


def test_otro_municipio_fuera_de_madrid_no_consulta_madrid(cliente, fuentes):
    cliente.put("/api/ajustes", json={"todos_trabajan": True, "municipio": "08019"})  # Barcelona
    fuentes[io(2026, "08019")] = {"holidays": [
        {"date": "2026-09-24", "name": {"es": "La Mercè"}, "level": "local", "source": {"ref": "DOGC"}},
    ]}
    datos = cliente.get("/api/festivos/oficiales/2026").json()
    assert datos["municipio"]["nombre"] == "Barcelona"
    assert not datos["completo"]
    assert any("Faltan festivos locales" in a for a in datos["avisos"])
    assert fuentes["pedidas"] == [io(2026, "08019")]

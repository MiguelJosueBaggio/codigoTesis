"""Smoke test de andamiaje (change foundation-setup / C-01).

Verificaba originalmente que los 4 modulos stub del pipeline (ingestion,
validation, transformation, persistence) importaban sin error y que sus
funciones publicas, todavia no implementadas, fallaban de forma explicita
con `NotImplementedError` en vez de fallar silenciosamente o devolver
`None`.

`ingestion.ingest` dejo de ser un stub: el change `ingestion-module` (C-03)
lo reemplazo por la implementacion real (ver `tests/test_ingestion.py`).
`validation.validate` dejo de ser un stub: el change `validation-engine`
(C-04) lo reemplazo por el motor declarativo real (ver
`tests/test_validation.py`). `transformation.transform` dejo de ser un
stub: el change `transformation-module` (C-05) lo reemplazo por el modulo
real de normalizacion/estandarizacion (ver `tests/test_transformation.py`).
`persistence.persist` dejo de ser un stub: el change
`persistence-audit-module` (C-06) lo reemplazo por la capa real de
persistencia y auditoria (ver `tests/test_persistence.py`).

Con los 4 modulos implementados, ya no queda ninguna funcion stub que
verificar aca; el unico smoke test remanente confirma que el paquete
`pipeline` sigue siendo importable como un todo.
"""


def test_stub_modules_import_without_error():
    """Los 4 modulos, ya implementados, deben poder importarse sin lanzar
    excepcion."""
    from pipeline import ingestion, validation, transformation, persistence  # noqa: F401

"""Script de respaldo automatico fuera del repositorio principal (RN-AUD-03)
-- change persistence-audit-module (C-06).

Copia (a) el dataset persistido, (b) la bitacora de transformaciones y (c)
una referencia de codigo (el hash de commit Git ya registrado en
`Ejecucion.commit_git`) a un directorio destino FUERA del arbol del
repositorio principal, parametrizado por la variable de entorno
`BACKUP_DIR` (Decision 9, design.md; documentada en `.env.example`).

Este modulo entrega el SCRIPT de respaldo; su *scheduling* (cron / nodo
Schedule de n8n) se cablea en el change `n8n-orchestration` (C-08) -- NO se
programa aca (Non-Goal explicito del design).
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

REPO_ROOT = Path(__file__).resolve().parent.parent
_BACKUP_DIR_ENV_VAR = "BACKUP_DIR"


class BackupError(Exception):
    """Base de los errores del script de respaldo."""


class BackupDirNoConfiguradoError(BackupError):
    """No hay destino de respaldo configurado (ni `BACKUP_DIR` en el
    entorno ni pasado explicitamente)."""


class BackupDestinoInvalidoError(BackupError):
    """El destino resuelto queda DENTRO del arbol del repositorio.

    RN-AUD-03 exige que el respaldo quede fuera del repo principal; fail
    -closed en vez de aceptar en silencio un destino que rompe esa regla.
    """


def _esta_dentro_de(ruta: Path, contenedor: Path) -> bool:
    try:
        ruta.relative_to(contenedor)
        return True
    except ValueError:
        return False


def resolver_directorio_backup(
    backup_dir: Optional[Union[str, Path]] = None,
    repo_root: Path = REPO_ROOT,
) -> Path:
    """Resuelve el destino de respaldo a una ruta absoluta y valida que
    quede fuera del arbol del repo (RN-AUD-03).

    Args:
        backup_dir: ruta explicita (los tests inyectan un directorio
            temporal); si se omite, se toma de la variable de entorno
            `BACKUP_DIR` (Decision 9).
        repo_root: raiz del repositorio contra la que se valida "fuera del
            arbol" (parametrizable para tests; default el repo real).

    Raises:
        BackupDirNoConfiguradoError: si no hay destino configurado.
        BackupDestinoInvalidoError: si el destino resuelto queda dentro
            del repo (p. ej. una ruta relativa que no sale del arbol).
    """
    destino = backup_dir if backup_dir is not None else os.environ.get(_BACKUP_DIR_ENV_VAR)
    if not destino:
        raise BackupDirNoConfiguradoError(
            f"No hay directorio de respaldo configurado. Defini "
            f"'{_BACKUP_DIR_ENV_VAR}' (ver .env.example) o pasalo explicitamente."
        )

    repo_root_resuelto = repo_root.resolve()
    ruta = Path(destino).expanduser()
    if not ruta.is_absolute():
        ruta = repo_root_resuelto / ruta
    ruta = ruta.resolve()

    if _esta_dentro_de(ruta, repo_root_resuelto):
        raise BackupDestinoInvalidoError(
            f"El destino de respaldo '{ruta}' queda DENTRO del repositorio "
            f"('{repo_root_resuelto}'). RN-AUD-03 exige que el respaldo quede "
            "fuera del arbol del repo -- usa una ruta absoluta o relativa que "
            "salga de el (p. ej. '../ensayos-backups')."
        )
    return ruta


def hacer_backup(
    dataset_path: Union[str, Path],
    bitacora_path: Union[str, Path],
    commit_git: str,
    backup_dir: Optional[Union[str, Path]] = None,
    repo_root: Path = REPO_ROOT,
) -> Path:
    """Copia dataset + bitacora + referencia de codigo a un subdirectorio
    con marca de tiempo dentro del destino de respaldo resuelto.

    Args:
        dataset_path: ruta al archivo del dataset persistido a respaldar.
        bitacora_path: ruta al archivo de la bitacora de transformaciones.
        commit_git: hash del commit Git a dejar como referencia de codigo
            (ya registrado en `Ejecucion.commit_git`, RN-AUD-01).
        backup_dir: ver `resolver_directorio_backup`.
        repo_root: ver `resolver_directorio_backup`.

    Returns:
        La ruta del subdirectorio de respaldo creado (fuera del repo).
    """
    destino_base = resolver_directorio_backup(backup_dir, repo_root)
    marca_tiempo = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    destino = destino_base / marca_tiempo
    destino.mkdir(parents=True, exist_ok=True)

    shutil.copy2(dataset_path, destino / Path(dataset_path).name)
    shutil.copy2(bitacora_path, destino / Path(bitacora_path).name)
    (destino / "commit_git.txt").write_text(commit_git, encoding="utf-8")

    return destino

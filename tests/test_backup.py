"""Tests de `scripts/backup.py` -- change persistence-audit-module (C-06).

Spec: "Respaldo automatico fuera del repositorio principal" (RN-AUD-03).
El destino se parametriza por `BACKUP_DIR` (Decision 9, design.md); el test
usa un `repo_root` de prueba (nunca el repo real) para no depender del
entorno de la maquina que corre la suite.
"""

from __future__ import annotations

import pytest

from scripts.backup import (
    BackupDestinoInvalidoError,
    BackupDirNoConfiguradoError,
    hacer_backup,
    resolver_directorio_backup,
)


def test_backup_copia_dataset_bitacora_y_referencia_de_codigo(tmp_path):
    repo_falso = tmp_path / "repo"
    repo_falso.mkdir()
    dataset = repo_falso / "dataset.csv"
    dataset.write_text("col_a,col_b\n1,2\n", encoding="utf-8")
    bitacora = repo_falso / "bitacora.json"
    bitacora.write_text('[{"tipo": "x"}]', encoding="utf-8")

    destino_backup = tmp_path / "afuera" / "backups"

    destino = hacer_backup(
        dataset_path=dataset,
        bitacora_path=bitacora,
        commit_git="abc123",
        backup_dir=destino_backup,
        repo_root=repo_falso,
    )

    assert (destino / "dataset.csv").read_text(encoding="utf-8") == dataset.read_text(encoding="utf-8")
    assert (destino / "bitacora.json").read_text(encoding="utf-8") == bitacora.read_text(encoding="utf-8")
    assert (destino / "commit_git.txt").read_text(encoding="utf-8") == "abc123"


def test_directorio_de_backup_resuelto_queda_fuera_del_arbol_del_repo(tmp_path):
    repo_falso = tmp_path / "repo"
    repo_falso.mkdir()
    destino_backup = tmp_path / "afuera"

    resuelto = resolver_directorio_backup(destino_backup, repo_root=repo_falso)

    with pytest.raises(ValueError):
        resuelto.relative_to(repo_falso.resolve())


def test_backup_dir_relativo_que_resuelve_dentro_del_repo_falla(tmp_path):
    repo_falso = tmp_path / "repo"
    repo_falso.mkdir()

    with pytest.raises(BackupDestinoInvalidoError):
        resolver_directorio_backup("subcarpeta_interna", repo_root=repo_falso)


def test_backup_dir_no_configurado_falla_con_mensaje_claro(monkeypatch, tmp_path):
    monkeypatch.delenv("BACKUP_DIR", raising=False)
    repo_falso = tmp_path / "repo"
    repo_falso.mkdir()

    with pytest.raises(BackupDirNoConfiguradoError):
        resolver_directorio_backup(repo_root=repo_falso)


def test_backup_dir_se_lee_de_la_variable_de_entorno_si_no_se_pasa_explicito(
    monkeypatch, tmp_path
):
    repo_falso = tmp_path / "repo"
    repo_falso.mkdir()
    destino_backup = tmp_path / "afuera_env"
    monkeypatch.setenv("BACKUP_DIR", str(destino_backup))

    resuelto = resolver_directorio_backup(repo_root=repo_falso)

    assert resuelto == destino_backup.resolve()

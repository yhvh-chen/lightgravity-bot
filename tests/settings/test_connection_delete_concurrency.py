"""Deletion must serialize with controlled Settings and Agent reference writers."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from lightgravity.contracts import AppError
from lightgravity.resources.service import ResourceService
from lightgravity.settings import ConnectionService, FileSecretStore
from lightgravity.store import FileStore


@pytest.mark.parametrize('binding', ['default', 'agent'])
def test_delete_does_not_race_a_new_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, binding: str,
) -> None:
    root = tmp_path / 'data'
    store = FileStore(root, root / 'workspaces')
    service = ConnectionService(store, secret_store=FileSecretStore(tmp_path / 'secrets'))
    service.create_connection('deepseek', actor='test', request_id='create')
    store.create('agent', 'helper', {'title': 'Helper', 'enabled': True},
                 actor='test', request_id='agent')
    # Distinct instances on the same root model separate application processes.
    other_store = FileStore(root, root / 'workspaces')
    other_service = ConnectionService(
        other_store, secret_store=FileSecretStore(tmp_path / 'secrets'),
    )
    resources = ResourceService(other_store, connections=other_service)
    checked = threading.Event()
    binding_finished = threading.Event()
    original_guard = service._guard_connection_delete

    def paused_guard(connection_id: str) -> None:
        original_guard(connection_id)
        checked.set()
        # On the unfixed product the other entity lock allows binding to finish
        # here. On a repaired product it must wait for deletion to finish.
        binding_finished.wait(0.25)

    monkeypatch.setattr(service, '_guard_connection_delete', paused_guard)

    def bind() -> str:
        assert checked.wait(5)
        try:
            if binding == 'default':
                other_service.update_settings(
                    expected_revision=None, actor='test',
                    default_worker_connection_ref='deepseek',
                )
            else:
                resources.update('agent', 'helper', patch={'connection_ref': 'deepseek'},
                                 expected_revision=0, actor='test')
            return 'bound'
        except AppError as error:
            assert error.code in {'reference_invalid', 'not_found'}
            return 'rejected'
        finally:
            binding_finished.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(bind)
        deletion = pool.submit(service.delete_connection, 'deepseek',
                               expected_revision=0, actor='test')
        assert deletion.result(timeout=10)['deleted'] is True
        outcome = writer.result(timeout=10)
    assert outcome == 'rejected', 'writer committed a dangling connection reference'
    assert not store.entity_path('connection', 'deepseek').exists()
    assert service.repository.read_settings().default_worker_connection_ref is None
    assert store.read('agent', 'helper').entity.get('connection_ref') is None


@pytest.mark.parametrize('binding', ['default', 'agent'])
def test_new_reference_wins_before_delete_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, binding: str,
) -> None:
    root = tmp_path / 'data'
    store = FileStore(root, root / 'workspaces')
    service = ConnectionService(store, secret_store=FileSecretStore(tmp_path / 'secrets'))
    service.create_connection('deepseek', actor='test', request_id='create')
    store.create('agent', 'helper', {'title': 'Helper', 'enabled': True},
                 actor='test', request_id='agent')
    other_store = FileStore(root, root / 'workspaces')
    other_service = ConnectionService(
        other_store, secret_store=FileSecretStore(tmp_path / 'secrets'),
    )
    resources = ResourceService(other_store, connections=other_service)
    validated = threading.Event()
    release = threading.Event()
    delete_entered = threading.Event()

    def pause() -> None:
        validated.set()
        assert release.wait(5)

    if binding == 'default':
        original_default = service._validate_default_ref

        def validate_default(ref: Any, *, role: str) -> None:
            original_default(ref, role=role)
            if ref == 'deepseek':
                pause()

        monkeypatch.setattr(service, '_validate_default_ref', validate_default)
    else:
        original_agent = resources._validate_candidate

        def validate_agent(kind: str, candidate: Any) -> None:
            original_agent(kind, candidate)
            pause()

        monkeypatch.setattr(resources, '_validate_candidate', validate_agent)

    def bind() -> None:
        if binding == 'default':
            service.update_settings(expected_revision=None, actor='test',
                                    default_worker_connection_ref='deepseek')
        else:
            resources.update('agent', 'helper', patch={'connection_ref': 'deepseek'},
                             expected_revision=0, actor='test')

    def delete() -> None:
        delete_entered.set()
        with pytest.raises(AppError) as error:
            other_service.delete_connection('deepseek', expected_revision=0, actor='test')
        assert error.value.code == 'reference_invalid'

    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(bind)
        assert validated.wait(5)
        deletion = pool.submit(delete)
        assert delete_entered.wait(5)
        release.set()
        writer.result(timeout=10)
        deletion.result(timeout=10)
    assert store.entity_path('connection', 'deepseek').is_file()
    refs = service.references_to('deepseek')
    assert refs.default_roles == (('worker',) if binding == 'default' else ())
    assert refs.agent_refs == (('helper',) if binding == 'agent' else ())


@pytest.mark.parametrize('endpoint', [
    'http://127.0.0.1:9/v1',
    'https://custom.example/v1',
    'https://api.deepseek.com.evil.example/v1',
    'https://api.deepseek.com@evil.example/v1',
])
def test_any_host_can_be_default_and_proxied(
    tmp_path: Path, endpoint: str,
) -> None:
    # LG-230: the product no longer restricts hosts; any configured endpoint
    # may be the default and receive its own credential through the proxy.
    from lightgravity.adapter.credentials import Secret
    from lightgravity.adapter.proxy import LocalAuthProxy

    root = tmp_path / 'data'
    store = FileStore(root, root / 'workspaces')
    service = ConnectionService(store, secret_store=FileSecretStore(tmp_path / 'secrets'))
    view = service.create_connection('custom', base_url=endpoint,
                                     actor='test', request_id='custom')
    assert view['capabilities']['executable'] is True
    service.update_settings(expected_revision=None, actor='test',
                            default_worker_connection_ref='custom')
    assert service.repository.read_settings().default_worker_connection_ref == 'custom'
    LocalAuthProxy(credential=Secret('dummy-local-only'),
                   upstream_url=endpoint + '/chat/completions')

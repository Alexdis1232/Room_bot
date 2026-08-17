"""Регресс на автообновление (_maybe_self_update).

Раньше любой фикс требовал вручную скачать room_bot.py с GitHub и подменить
файл на компьютере — легко забыть, и бот неделями работал на старой версии.
Эти тесты проверяют механизм самообновления: сравнение с версией на GitHub,
перезапись файла на диске, защита от мусора вместо кода вместо реального
файла (например HTML-страницы ошибки).

Запуск: pytest (из корня room_bot) или python -m pytest tests/.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import room_bot as rb


class _FakeResp:
    def __init__(self, text, ok=True):
        self.text = text
        self._ok = ok

    def raise_for_status(self):
        if not self._ok:
            import requests
            raise requests.HTTPError("boom")


def _valid_code(marker):
    # достаточно длинный текст с "def main(" внутри, чтобы пройти защиту
    # от мусора в _maybe_self_update
    return f"# {marker}\n" + ("x = 1\n" * 300) + "def main():\n    pass\n"


def test_self_update_overwrites_when_code_differs(monkeypatch, tmp_path):
    target = tmp_path / "room_bot.py"
    target.write_text(_valid_code("old"), encoding="utf-8")

    new_code = _valid_code("new")
    monkeypatch.setattr(rb.requests, "get", lambda *a, **kw: _FakeResp(new_code))

    updated = rb._maybe_self_update(target_path=str(target))
    assert updated is True
    assert target.read_text(encoding="utf-8") == new_code


def test_self_update_is_noop_when_code_is_identical(monkeypatch, tmp_path):
    code = _valid_code("same")
    target = tmp_path / "room_bot.py"
    target.write_text(code, encoding="utf-8")

    monkeypatch.setattr(rb.requests, "get", lambda *a, **kw: _FakeResp(code))

    updated = rb._maybe_self_update(target_path=str(target))
    assert updated is False
    assert target.read_text(encoding="utf-8") == code


def test_self_update_ignores_garbage_response(monkeypatch, tmp_path):
    # если GitHub вдруг отдал не сырой файл, а HTML-страницу ошибки —
    # не должны затирать рабочий файл мусором
    original = _valid_code("original")
    target = tmp_path / "room_bot.py"
    target.write_text(original, encoding="utf-8")

    monkeypatch.setattr(rb.requests, "get", lambda *a, **kw: _FakeResp("<html>404 not found</html>"))

    updated = rb._maybe_self_update(target_path=str(target))
    assert updated is False
    assert target.read_text(encoding="utf-8") == original


def test_self_update_survives_network_error(monkeypatch, tmp_path):
    original = _valid_code("original")
    target = tmp_path / "room_bot.py"
    target.write_text(original, encoding="utf-8")

    def raise_network_error(*a, **kw):
        import requests
        raise requests.RequestException("network down")

    monkeypatch.setattr(rb.requests, "get", raise_network_error)

    updated = rb._maybe_self_update(target_path=str(target))
    assert updated is False
    assert target.read_text(encoding="utf-8") == original


def test_self_update_restarts_process_when_requested(monkeypatch, tmp_path):
    target = tmp_path / "room_bot.py"
    target.write_text(_valid_code("old"), encoding="utf-8")

    new_code = _valid_code("new")
    monkeypatch.setattr(rb.requests, "get", lambda *a, **kw: _FakeResp(new_code))

    try:
        rb._maybe_self_update(restart_on_update=True, target_path=str(target))
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert e.code == 0
    # файл должен быть перезаписан ДО выхода из процесса
    assert target.read_text(encoding="utf-8") == new_code

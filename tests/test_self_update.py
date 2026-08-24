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
    def __init__(self, text, ok=True, content=None):
        self.text = text
        self.content = content if content is not None else (text.encode("utf-8") if isinstance(text, str) else text)
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


# ==================== СИНХРОНИЗАЦИЯ АССЕТОВ (assets/welcome.jpg и т.п.) ====================
# room_bot.py — не единственный файл, который нужен боту: обложка
# приветствия лежит в assets/. Самообновление кода само по себе её не
# трогает, поэтому есть отдельный, но такой же по духу механизм.

def test_sync_assets_downloads_new_file(monkeypatch, tmp_path):
    new_bytes = b"\xff\xd8\xff-jpeg-bytes-v2"
    monkeypatch.setattr(rb.requests, "get", lambda *a, **kw: _FakeResp(None, content=new_bytes))
    monkeypatch.setattr(rb, "ASSET_FILES", ["assets/welcome.jpg"])

    rb._maybe_sync_assets(base_dir=str(tmp_path))

    saved = tmp_path / "assets" / "welcome.jpg"
    assert saved.read_bytes() == new_bytes


def test_sync_assets_noop_when_identical(monkeypatch, tmp_path):
    content = b"\xff\xd8\xff-same-jpeg-bytes"
    asset_path = tmp_path / "assets" / "welcome.jpg"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_bytes(content)
    original_mtime = asset_path.stat().st_mtime_ns

    monkeypatch.setattr(rb.requests, "get", lambda *a, **kw: _FakeResp(None, content=content))
    monkeypatch.setattr(rb, "ASSET_FILES", ["assets/welcome.jpg"])

    rb._maybe_sync_assets(base_dir=str(tmp_path))

    assert asset_path.stat().st_mtime_ns == original_mtime


def test_sync_assets_survives_network_error(monkeypatch, tmp_path):
    def raise_network_error(*a, **kw):
        import requests
        raise requests.RequestException("network down")

    monkeypatch.setattr(rb.requests, "get", raise_network_error)
    monkeypatch.setattr(rb, "ASSET_FILES", ["assets/welcome.jpg"])

    # не должно кидать исключение наружу — только залогировать и продолжить
    rb._maybe_sync_assets(base_dir=str(tmp_path))
    assert not (tmp_path / "assets" / "welcome.jpg").exists()


def test_send_telegram_photo_file_reads_local_bytes(monkeypatch, tmp_path):
    # общая утилита остаётся полезной сама по себе (например для будущих
    # функций), даже раз /start больше не шлёт фото — проверяем, что она
    # реально читает файл с диска и передаёт его в _telegram_api
    image_path = tmp_path / "pic.jpg"
    image_path.write_bytes(b"\xff\xd8\xff-fake-jpeg")

    calls = []
    monkeypatch.setattr(rb, "_telegram_api", lambda method, **kw: calls.append((method, kw)) or {"ok": True})

    ok = rb.send_telegram_photo_file("42", str(image_path), caption="подпись")
    assert ok is True
    method, kw = calls[0]
    assert method == "sendPhoto"
    assert kw["data"]["caption"] == "подпись"
    assert kw["files"]["photo"][1] == b"\xff\xd8\xff-fake-jpeg"

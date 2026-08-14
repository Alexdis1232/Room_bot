"""Регрессия: смена фильтра через кнопочное меню не должна повторно
присылать посты, уже отправленные раньше (при любом фильтре).

Раньше send_recent_matching_ads() при каждом нажатии "Применить" заново
сканировал последние 48 часов и не проверял, отправлялся ли пост уже —
расширение фильтра (например, добавили "Комната" к уже применённым
"1-к"/"2-к") повторно присылало все старые подходящие объявления.

Также использует настоящий state.json (во временной папке — не трогает
реальный файл проекта), чтобы заодно проверить save_state(): фикстура
имитирует то, что делает RoomBotListener — читает state независимо от
только что записанного другим вызовом.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import room_bot as rb


def make_post(post_id, channel="chanA", text="1-к квартира, 55000 руб"):
    return {
        "id": post_id, "channel": channel, "date": "", "datetime": None,
        "text": text, "link": f"https://t.me/{channel}/{post_id}", "photos": [],
    }


def base_filters(**overrides):
    filters = {
        "keywords_include": [], "keywords_exclude": [], "districts": [],
        "price_ranges": [], "property_types": [], "price_min": 0,
        "price_max": 200000, "rooms": [], "metro_max_minutes": None,
    }
    filters.update(overrides)
    return filters


class _DigestRecorder:
    def __init__(self):
        self.messages = []
        self.digests = []

    def send_message(self, text, **kwargs):
        self.messages.append(text)

    def send_digest(self, posts):
        self.digests.append([p["id"] for p in posts])
        # реальная send_digest помечает посты отправленными сама (см.
        # _mark_as_sent) — заглушка должна делать то же самое, иначе тесты
        # проверяли бы не то поведение, что действительно есть в коде
        rb._mark_as_sent(posts)


def setup_isolated_state(monkeypatch, tmp_path):
    # реальные load_json/save_json/save_state продолжают работать как в
    # проде, просто на файле во временной папке — не трогаем state.json
    # самого проекта и заодно проверяем настоящую логику блокировки/слияния
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(rb, "STATE_PATH", str(state_path))
    monkeypatch.setattr(rb, "STATE_LOCK_PATH", str(state_path) + ".lock")
    monkeypatch.setattr(rb, "state", {"last_ids": {}})

    recorder = _DigestRecorder()
    monkeypatch.setattr(rb, "send_telegram_message", recorder.send_message)
    monkeypatch.setattr(rb, "send_digest", recorder.send_digest)
    return recorder


def test_widening_filter_does_not_resend_already_delivered_posts(monkeypatch, tmp_path):
    recorder = setup_isolated_state(monkeypatch, tmp_path)

    posts = [
        make_post(1, text="1-к квартира, 55000 руб"),
        make_post(2, text="2-к квартира, 60000 руб"),
    ]
    monkeypatch.setattr(rb, "fetch_channel_posts_since", lambda channel, cutoff, max_pages=15: posts)

    filters_1_2 = base_filters(property_types=["1-к квартира", "2-к квартира"])
    rb.send_recent_matching_ads(hours=48, channels=["chanA"], filters=filters_1_2)
    assert recorder.digests == [[1, 2]]

    # расширили фильтр: добавили "Комната" — старые 1-к/2-к уже отправлены,
    # в канале появился ещё и пост с комнатой
    posts_with_room = posts + [make_post(3, text="Сдаётся комната, 30000 руб")]
    monkeypatch.setattr(rb, "fetch_channel_posts_since", lambda channel, cutoff, max_pages=15: posts_with_room)

    filters_1_2_room = base_filters(property_types=["1-к квартира", "2-к квартира", "Комната"])
    rb.send_recent_matching_ads(hours=48, channels=["chanA"], filters=filters_1_2_room)

    # только новый пост (id=3) — посты 1 и 2 уже были отправлены
    assert recorder.digests[-1] == [3]


def test_removing_then_reapplying_filter_does_not_resend(monkeypatch, tmp_path):
    recorder = setup_isolated_state(monkeypatch, tmp_path)

    posts = [make_post(1, text="1-к квартира, 55000 руб"), make_post(2, text="2-к квартира, 60000 руб")]
    monkeypatch.setattr(rb, "fetch_channel_posts_since", lambda channel, cutoff, max_pages=15: posts)

    filters_1_2 = base_filters(property_types=["1-к квартира", "2-к квартира"])
    rb.send_recent_matching_ads(hours=48, channels=["chanA"], filters=filters_1_2)
    assert recorder.digests == [[1, 2]]

    # убрали 2-комнатную
    filters_1_only = base_filters(property_types=["1-к квартира"])
    rb.send_recent_matching_ads(hours=48, channels=["chanA"], filters=filters_1_only)
    assert len(recorder.digests) == 1  # ничего нового не появилось

    # "через сутки" вернули 2-комнатную обратно — тот же пост 2 всё ещё
    # виден в последних 48 часах, но уже отправлялся раньше
    rb.send_recent_matching_ads(hours=48, channels=["chanA"], filters=filters_1_2)
    assert len(recorder.digests) == 1  # дубль не отправлен
    assert "не нашлось" in recorder.messages[-1]


def test_scheduled_scan_does_not_resend_manually_applied_post(monkeypatch, tmp_path):
    # плановый скан (fetch_new_posts) не должен повторно прислать пост,
    # который только что ушёл через ручное "Применить" — оба пути делят
    # один и тот же sent_post_ids в state.json
    recorder = setup_isolated_state(monkeypatch, tmp_path)

    post = make_post(10, text="1-к квартира, 55000 руб")
    monkeypatch.setattr(rb, "fetch_channel_posts_since", lambda channel, cutoff, max_pages=15: [post])
    filters_1 = base_filters(property_types=["1-к квартира"])
    rb.send_recent_matching_ads(hours=48, channels=["chanA"], filters=filters_1)
    assert recorder.digests == [[10]]

    # плановый скан видит тот же пост впервые (last_ids пуст для chanA)
    monkeypatch.setattr(rb, "fetch_channel_posts", lambda channel: [post])
    results = rb.fetch_new_posts(["chanA"], filters_1)
    assert results == []  # уже отправлен вручную — плановый скан его не возвращает


def test_manual_send_digest_call_prevents_later_resend(monkeypatch, tmp_path):
    # раньше send_digest() сама по себе НЕ помечала посты отправленными —
    # это делали только fetch_new_posts/send_recent_matching_ads. Значит
    # разовая ручная отправка (например, показать пример объявления)
    # в обход этих двух функций не попадала в sent_post_ids, и тот же пост
    # мог потом снова найтись плановым сканом/"Применить" и уйти повторно
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(rb, "STATE_PATH", str(state_path))
    monkeypatch.setattr(rb, "STATE_LOCK_PATH", str(state_path) + ".lock")
    monkeypatch.setattr(rb, "state", {"last_ids": {}})
    sent_messages = []
    monkeypatch.setattr(rb, "send_telegram_message", lambda text, **kw: sent_messages.append(text))

    post = {
        "id": 99, "channel": "chanA", "date": "", "datetime": None,
        "text": "1-к квартира, 55000 руб", "link": "https://t.me/chanA/99", "photos": [],
    }

    # разовая ручная отправка (как для демонстрации примера) — идёт мимо
    # fetch_new_posts/send_recent_matching_ads
    rb.send_digest([post])

    on_disk = rb.load_json(str(state_path), {})
    assert on_disk.get("sent_post_ids") == ["chanA/99"]

    # теперь плановый скан находит тот же пост впервые (last_ids пуст) —
    # не должен вернуть его повторно
    monkeypatch.setattr(rb, "fetch_channel_posts", lambda channel: [post])
    filters_1 = base_filters(property_types=["1-к квартира"])
    results = rb.fetch_new_posts(["chanA"], filters_1)
    assert results == []


def test_save_state_merges_instead_of_clobbering_other_process(monkeypatch, tmp_path):
    # имитация гонки двух процессов: "скан" пишет last_ids/sent_post_ids,
    # "слушатель" с более старым state в памяти сохраняет свои изменения
    # позже — не должен стереть то, что записал скан
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(rb, "STATE_PATH", str(state_path))
    monkeypatch.setattr(rb, "STATE_LOCK_PATH", str(state_path) + ".lock")

    monkeypatch.setattr(rb, "state", {"last_ids": {}})
    rb.save_state(last_ids={"chanA": 42}, sent_post_ids=["chanA/1"])

    # "слушатель" запустился раньше и не знает про last_ids/sent_post_ids,
    # обновлёт только last_update_id
    monkeypatch.setattr(rb, "state", {"last_ids": {}})  # его устаревший снимок
    rb.save_state(last_update_id=999)

    on_disk = rb.load_json(str(state_path), {})
    assert on_disk["last_ids"] == {"chanA": 42}
    assert on_disk["sent_post_ids"] == ["chanA/1"]
    assert on_disk["last_update_id"] == 999

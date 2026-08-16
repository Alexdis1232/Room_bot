"""Регрессионные тесты на извлечение полей из текста объявления.

Эта часть room_bot.py — самая сложная и самая часто чинившаяся руками (см.
комментарии в самом room_bot.py про конкретные баги, которые тут когда-то
были). Раньше это никак не было защищено от повторного появления той же
ошибки при следующей правке регулярки — эти тесты фиксируют уже проверенное
поведение.

Запуск: pytest (из корня room_bot) или python -m pytest tests/.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import room_bot as rb


# ==================== ЦЕНА ====================

def test_price_with_currency_suffix():
    assert rb.extract_price("Сдам квартиру, 55000 руб") == 55000


def test_price_with_thousands_separator():
    assert rb.extract_price("Цена 55.000 руб") == 55000


def test_price_excludes_nearby_utility_amount():
    # раньше "70 000 + 3 600 коммунальные" отдавало 3 600 как цену — брался
    # минимум из всех чисел с валютой, включая коммуналку (см. room_bot.py,
    # комментарий у _price_exclusion_spans)
    assert rb.extract_price("70 000 руб + 3 600 коммунальные услуги") == 70000


def test_price_with_rub_per_month_abbreviation_no_dot():
    # "40.000 р/мес" — сокращение "рублей/месяц" без точки после "р": ни
    # PRICE_RE (там после "р" всегда нужна точка, а не "/"), ни старый
    # PRICE_MONTH_RE (не пускал букву "р" перед "/мес") это не ловили,
    # цена уходила как "не указана" у реального объявления с ценой
    assert rb.extract_price("Условия: 40.000 р/мес. К/у включены в стоимость") == 40000
    assert rb.extract_price("40000 р/мес") == 40000


def test_price_shorthand_with_plus_sign():
    # "Оплата 45+ счётчики" = 45 тысяч + коммуналка отдельно
    assert rb.extract_price("Оплата 45+ счётчики") == 45000


def test_price_bare_shorthand_without_keyword():
    # "28к" отдельной строкой, без "цена/оплата/стоимость" рядом — частый
    # компактный формат ("28к (все включено)")
    assert rb.extract_price("Расположение: метро Белорусская\n28к (все включено)") == 28000
    # но не однозначное сокращение числа комнат (там всегда одна цифра)
    assert rb.extract_price("2-к квартира, метро Сокольники") is None
    assert rb.extract_price("35 кв.м, ремонт свежий") is None


def test_price_shorthand_prepositional_case():
    # "По цене: 28к" — раньше не ловилось: искали только "цена" в
    # именительном падеже, а тут предложный ("цене")
    assert rb.extract_price("По цене: 28к КУ включены") == 28000


def test_price_ignores_small_unrelated_monthly_fee():
    # "Интернет — 450 ₽ в месяц" не должен побеждать как "минимальная" цена
    # среди всех найденных чисел с валютой — реальная аренда намного больше
    text = "💰 46 000 ₽ / месяц\nИнтернет — 450 ₽ в месяц."
    assert rb.extract_price(text) == 46000


def test_price_ignores_range_upper_bound():
    # "3 000–4 000 ₽" — верхняя граница оценочного диапазона (обычно
    # коммуналка), не отдельная цена сама по себе
    text = "💰 46 000 ₽ / месяц\nКоммунальные услуги — примерно 3 000–4 000 ₽ в месяц."
    assert rb.extract_price(text) == 46000


def test_price_ignores_zhkh_utility_estimate():
    # "ЖКХ" — частый синоним "коммунальных услуг", раньше не распознавался
    # как ключевое слово для исключения суммы рядом ("около 3.500₽" рядом
    # с "ЖКХ" побеждало как "минимальная" цена вместо настоящих 30 000)
    text = "Цена: 30.000₽/мес. + ЖКХ (около 3.500₽)"
    assert rb.extract_price(text) == 30000


def test_negation_does_not_leak_across_newline():
    # "включены" из строки про коммуналку не должно считаться отрицанием
    # для залога строкой ниже — раньше перенос строки не был границей
    # предложения, и залог ошибочно помечался как "без залога"
    text = "По цене: 28к КУ включены\nЗалог: 5к можно разбить"
    extras = rb.extract_price_extras(text)
    assert "залог" in extras
    assert "без залога" not in extras


def test_price_extras_negation_scoped_to_sentence():
    # "без" относится только к комиссии в своём предложении — "Залог
    # возвращается" в отдельном предложении дальше не должен считаться
    # отрицанием залога
    extras = rb.extract_price_extras("Без комиссии. Залог возвращается.")
    assert "без комиссии" in extras
    assert "залог" in extras


# ==================== КОМНАТЫ / ЭТАЖ / ПЛОЩАДЬ ====================

def test_rooms_basic():
    assert rb.extract_rooms("2-к квартира") == 2


def test_floor_word_format():
    assert rb.extract_floor("12 этаж из 17") == "12 из 17"


def test_floor_slash_format():
    # "N/M этаж" словом — отдельный формат от слитного "8/15эт"
    assert rb.extract_floor("3/8 этаж") == "3 из 8"


def test_area_with_superscript_m2():
    assert rb.extract_area("36,5 м²") == "36,5"


def test_area_with_kvm_abbreviation():
    assert rb.extract_area("36,5 кв.м") == "36,5"


def test_area_shorthand_without_kvm_or_superscript():
    # "19,6м" — без "кв."/"²", просто число слитно с "м"
    assert rb.extract_area("Сдается уютная новая студия 19,6м у м.Котельники") == "19,6"


def test_area_shorthand_does_not_break_metro_abbreviation():
    # "м." с точкой перед станцией — это метро, не площадь
    assert rb.extract_area("15м. Марксистская пешком") is None


# ==================== МЕБЕЛЬ ====================

def test_basic_furniture_detected_from_individual_pieces():
    # по фото бот не смотрит — ориентируется на упоминания конкретных
    # предметов обстановки в тексте (кровать/шкаф/...), даже без слова
    # "мебель" целиком
    text = (
        "В студии есть: кровать 140x200 с матрасом; большой шкаф; "
        "кондиционер; обеденный стол и 2 стула."
    )
    amenities = rb.extract_amenities(text)
    assert amenities[0] == "базовая мебель"
    assert "кондиционер" in amenities


def test_basic_furniture_not_confused_with_oven():
    # "духовой шкаф" — кухонная техника, а не платяной шкаф; само по себе
    # не должно считаться признаком базовой мебели
    text = "Оснащение кухни: варочная панель, духовой шкаф, холодильник."
    amenities = rb.extract_amenities(text)
    assert "базовая мебель" not in amenities
    assert "духовой шкаф" in amenities


def test_basic_furniture_respects_negation():
    text = "Сдаётся пустая квартира без мебели, только стены и окна."
    assert "базовая мебель" not in rb.extract_amenities(text)


def test_basic_furniture_not_confused_with_capital_city():
    # "стол" в "столица"/"столичный" — не про мебель
    text = "Уютная студия в центре Москвы, столица встречает гостей. Есть кондиционер."
    amenities = rb.extract_amenities(text)
    assert "базовая мебель" not in amenities
    assert amenities == ["кондиционер"]


# ==================== МЕТРО ====================

def test_metro_minutes_and_mode():
    minutes, mode = rb.extract_metro_minutes_and_mode("10 мин пешком до метро Сокольники")
    assert minutes == 10
    assert mode == "пешком"


def test_metro_station_fallback_without_metro_word():
    # станция без слова "метро"/"м." рядом — ищем по справочнику известных
    # станций (find_known_station)
    assert rb.extract_metro_station("1-комнатная кв. на Профсоюзной") == "Профсоюзная"


def test_metro_station_does_not_swallow_following_words():
    # регэксп разрешает 2-3 слова после первого (для "Чистые пруды" и
    # похожих), но раньше это позволяло захватить случайные соседние слова:
    # "метро Ясенево комната где то" -> "Ясенево комната где" вместо
    # "Ясенево"
    text = "в 5 минутах от метро Ясенево комната где то 14-16м2"
    assert rb.extract_metro_station(text) == "Ясенево"


def test_metro_station_multi_word_name_still_works():
    # многословные названия по-прежнему должны находиться целиком
    assert rb.extract_metro_station("рядом метро Чистые пруды, 10 минут") == "Чистые пруды"


def test_streshnevo_has_a_line_color_icon():
    # раньше станции не было в справочнике вообще — цветной кружок линии не
    # находился, и вместо него показывался серый значок-заглушка 🚇
    icon = rb.metro_line_icon_html("Стрешнево")
    assert icon != "🚇"
    assert "tg-emoji" in icon


def test_multiword_station_split_across_line_break_is_recognized():
    # "м. Бульвар \nДмитрия Донского" — перенос строки внутри названия
    # станции: METRO_STATION_RE не перепрыгивает через "пробел+перенос
    # строки" как один разделитель между словами захвата, поэтому сырой
    # захват обрезался до одного "Бульвар" — справочник по такому огрызку
    # не находил станцию, и вместо цветного значка линии показывалась
    # заглушка
    text = "СРОЧНО Ищу соседку. М. Бульвар \nДмитрия донского, 15 мин пешком."
    assert rb.extract_metro_station(text) == "Бульвар Дмитрия Донского"


# ==================== ТИП ЖИЛЬЯ ====================

def test_property_type_room_word_wins_over_room_count():
    # "комната" отдельным словом значит "сдаётся комната", даже если в
    # тексте дальше встретится число комнат квартиры целиком
    assert rb.extract_property_type("Сдаётся комната в квартире") == "Комната"


def test_property_type_bed_space_counts_as_room():
    # "койко-место"/"койко место"/"спальное место" — тоже фактически сдача
    # комнаты (подселение), просто без слова "комната" в тексте
    assert rb.extract_property_type("Сдаётся койко-место в 3-комнатной квартире") == "Комната"
    assert rb.extract_property_type("Сдаётся койко место в квартире") == "Комната"
    assert rb.extract_property_type("Сдаётся спальное место, метро ВДНХ") == "Комната"


def test_property_type_not_confused_by_bathroom_mention():
    # "Ванная комната" в списке удобств не должна перекрывать реальный тип
    # жилья ("Студия" из заголовка) — раньше любое упоминание "Ванная
    # комната" превращало студию/квартиру в "Комната"
    text = "Студия | м. Бутырская\nВанная комната: душевая кабина, стиральная машина"
    assert rb.extract_property_type(text) == "Студия"


def test_property_type_by_room_count():
    assert rb.extract_property_type("2-комнатная квартира в аренду") == "2-к квартира"


def test_evrodvushka_normalizes_to_2k_for_filtering():
    # отдельной кнопки/категории для "евродвушки" в фильтрах больше нет —
    # такие объявления должны проходить под фильтром "2-к квартира"
    assert rb.extract_property_type("Продаю евродвушку в новом ЖК") == "Евродвушка"
    assert rb.normalize_property_type("Евродвушка") == "2-к квартира"

    filters = {
        "keywords_include": [], "keywords_exclude": [], "districts": [],
        "price_ranges": [], "property_types": ["2-к квартира"],
        "price_min": 0, "price_max": 200000, "rooms": [], "metro_max_minutes": None,
    }
    assert rb.matches_filters("Сдам евродвушку, 90000 руб", filters) is True


# ==================== АДРЕС ====================

def test_address_stops_before_price_block():
    # без явной точки в конце адрес раньше "проглатывал" всё до цены
    address = rb.extract_address(
        "Пролетарский пр-т, 45. Арендная плата: 55.000 руб, 36,5м2"
    )
    assert address == "Пролетарский пр-т, 45"


def test_address_with_abbreviated_type_followed_by_comma():
    # "Волоколамское ш., 24к1" — после сокращения "ш." сразу запятая, а не
    # пробел; раньше (?=\s) требовал пробел СРАЗУ после точки, и такие
    # адреса не находились вообще (extract_address возвращал None)
    text = "м Стрешнево — 2 минуты пешком\nВолоколамское ш., 24к1\nЗаезд — на этой неделе"
    assert rb.extract_address(text) == "Волоколамское ш., 24к1"


def test_address_falls_back_to_zhk_name_with_number():
    # без явной улицы, но с названием ЖК и номером дома — используем это
    # как адрес, а не показываем "не указан"; номер дома раньше терялся
    # (ZHK_NAME_RE не разрешал цифры в продолжении названия)
    text = "Дом находится в ЖК «Руставели 14» — рядом метро"
    assert rb.extract_address(text) == "ЖК Руставели 14"


def test_zhk_address_not_duplicated_in_infrastructure():
    # если название ЖК уже показано как адрес, не повторяем его же вторым
    # пунктом в блоке "Инфраструктура"
    post = {
        "text": "Студия в ЖК «Руставели 14», рядом супермаркет",
        "link": "https://t.me/test/1",
    }
    message = rb.format_post_message(post)
    assert message.count("Руставели 14") == 1


def test_address_combines_street_and_zhk_name():
    # название ЖК добавляется в адрес всегда, когда оно есть в тексте — даже
    # если явная улица тоже нашлась (раньше ЖК попадал только в
    # "Инфраструктуру" в этом случае, а не в "Адрес")
    text = "Пролетарский пр-т, 45, ЖК «Южные сады». Рядом супермаркет и парк."
    assert rb.extract_address(text) == "Пролетарский пр-т, 45, ЖК Южные сады"
    # и не дублируется в инфраструктуре
    assert "Южные сады" not in rb.extract_infrastructure(text)


# ==================== КОНТАКТЫ ====================

def test_contacts_do_not_bleed_across_newline_into_price():
    # "к.1" (номер корпуса) в конце строки и "40 000" (цена) на следующей —
    # раньше \s в регэкспе телефона включал перенос строки и склеивал их в
    # один "телефон" ('1\n40 000'), хотя реального контакта в тексте нет
    text = (
        "Сдам 1-к квартиру 39м2\n"
        "М. Алма-Атинская, ул. Алма-Атинская д.8 к.1\n"
        "40 000 руб/мес — \nсобственник"
    )
    assert rb.extract_contacts(text) is None


def test_contacts_still_finds_real_phone_with_spaces():
    assert rb.extract_contacts("Звоните +7 963 643 6 777 Ольга") == "+7 963 643 6 777"


def test_hidden_avito_link_behind_text_is_picked_up_as_contact(monkeypatch):
    # "собственник" в посте может быть кликабельной ссылкой на Авито, а не
    # обычным словом — сам URL виден только в href, а не в видимом тексте,
    # поэтому его нужно отдельно вытаскивать (как раньше уже делалось для
    # ссылок VK/WhatsApp/Instagram), иначе контакт вообще не найдётся
    html = """
    <div class="tgme_widget_message" data-post="testchan/1">
      <div class="tgme_widget_message_text">
        Сдам 1-к квартиру 39м2<br>М. Алма-Атинская, ул. Алма-Атинская д.8 к.1<br>
        40 000 руб/мес &mdash;
        <a href="https://www.avito.ru/moskva/kvartiry/1-k._kvartira_39_m_8302990329">собственник</a>
      </div>
      <time datetime="2026-08-14T08:12:00+00:00"></time>
    </div>
    """

    class FakeResponse:
        text = html

        def raise_for_status(self):
            pass

    monkeypatch.setattr(rb.requests, "get", lambda *a, **kw: FakeResponse())

    posts = rb.fetch_channel_posts("testchan")
    assert len(posts) == 1
    contacts = rb.extract_contacts(posts[0]["text"])
    assert contacts == "https://www.avito.ru/moskva/kvartiry/1-k._kvartira_39_m_8302990329"


# ==================== ФИЛЬТРЫ ====================

def test_channel_self_promo_post_is_excluded():
    # репост-самореклама другого канала ("вступай", "скидывай друзьям",
    # ссылка-приглашение) не должен проходить как объявление о сдаче жилья
    # просто потому, что упоминает слова "квартиру"/"комнату"
    promo_text = (
        "Можно ли найти хорошую квартиру или комнату в Москве?\n\n"
        "Ответ - конечно ДА!\n"
        "и это канал - Аренда Москва\n\n"
        "В нашем канале только собственники, без посредников.\n\n"
        "Так что заглядывай и обязательно скидывай его всем своим друзьям, "
        "ссылка для вступления -> https://t.me/+gwhgUuvClN00MDQy"
    )
    filters = {
        "keywords_include": [],
        "keywords_exclude": [
            "ссылка для вступления", "скидывай", "подпишись",
            "подписывайся", "наш канал", "нашем канале", "это канал -",
        ],
        "districts": [], "price_ranges": [], "property_types": ["Комната"],
        "price_min": 0, "price_max": 200000, "rooms": [], "metro_max_minutes": None,
    }
    assert rb.matches_filters(promo_text, filters) is False


def test_landlord_seeking_tenant_is_not_excluded():
    # "ищем" в исключениях должен ловить "ищем квартиру" (арендатор ищет
    # жильё), а не "ищем жильца" (арендодатель описывает, кого хочет
    # видеть) — раньше по голой подстроке "ищем" отсеивались реальные
    # объявления от собственников
    filters = {
        "keywords_include": [],
        "keywords_exclude": ["ищу квартир", "ищет квартир", "ищем квартир", "ищут квартир"],
        "districts": [], "price_ranges": [], "property_types": [],
        "price_min": 0, "price_max": 200000, "rooms": [], "metro_max_minutes": None,
    }
    landlord_text = "Сдается студия, 60000 руб. Ищем аккуратного жильца или пару на длительный срок."
    assert rb.matches_filters(landlord_text, filters) is True

    tenant_text = "Ищу квартиру в аренду, срочно, звоните."
    assert rb.matches_filters(tenant_text, filters) is False


def test_price_ranges_take_precedence_over_min_max():
    # если задан price_ranges (кнопочное меню) — price_min/price_max
    # игнорируются, даже если цена вне их диапазона
    filters = {
        "keywords_include": [], "keywords_exclude": [], "districts": [],
        "price_ranges": [[40000, 55000]], "price_min": 0, "price_max": 30000,
        "property_types": [], "rooms": [], "metro_max_minutes": None,
    }
    assert rb.matches_filters("Сдам, 50000 руб", filters) is True


# ==================== ОКРУГ ====================

def test_extract_district_by_metro_station():
    assert rb.extract_district("в 5 минутах от метро Кунцевская") == "ЗАО"
    assert rb.extract_district("метро Тушинская, 10 минут") == "СЗАО"
    assert rb.extract_district("рядом метро Ховрино") == "САО"
    assert rb.extract_district("метро Чистые пруды") == "ЦАО"


def test_okrug_filter_matches_recognized_district():
    filters = {
        "keywords_include": [], "keywords_exclude": [], "districts": [],
        "price_ranges": [], "property_types": [], "okrugs": ["ЗАО"],
        "price_min": 0, "price_max": 200000, "rooms": [], "metro_max_minutes": None,
    }
    assert rb.matches_filters("Сдам квартиру, метро Кунцевская, 55000 руб", filters) is True


def test_okrug_filter_rejects_other_recognized_district():
    filters = {
        "keywords_include": [], "keywords_exclude": [], "districts": [],
        "price_ranges": [], "property_types": [], "okrugs": ["ЗАО"],
        "price_min": 0, "price_max": 200000, "rooms": [], "metro_max_minutes": None,
    }
    # Чистые пруды — ЦАО, не ЗАО
    assert rb.matches_filters("Сдам квартиру, метро Чистые пруды, 55000 руб", filters) is False


def test_okrug_filter_soft_passes_unrecognized_station():
    # станция вне справочника (не входит в размеченные ЦАО/САО/СЗАО/ЗАО) —
    # не отбрасываем объявление зря, справочник не покрывает все округа
    filters = {
        "keywords_include": [], "keywords_exclude": [], "districts": [],
        "price_ranges": [], "property_types": [], "okrugs": ["ЗАО"],
        "price_min": 0, "price_max": 200000, "rooms": [], "metro_max_minutes": None,
    }
    assert rb.matches_filters("Сдам квартиру, 55000 руб, без указания метро", filters) is True


# ==================== ДУБЛИКАТЫ ====================

def test_same_ad_reposted_with_different_contacts_is_duplicate():
    # тот же текст объявления, но с добавленными телефоном/хэштегом —
    # типичный вид репоста в другом канале; CONTACT_RE должен вырезать
    # контакты/хэштеги при сравнении, чтобы это всё равно считалось дублем
    words_a = rb.extract_signature_words(
        "Сдам уютную однокомнатную квартиру рядом с метро Сокольники, "
        "ремонт свежий, мебель есть, звоните"
    )
    words_b = rb.extract_signature_words(
        "Срочно! Сдам уютную однокомнатную квартиру рядом с метро Сокольники, "
        "ремонт свежий, мебель есть +79161234567 #аренда"
    )
    assert rb.is_duplicate(words_b, [list(words_a)]) is True


def test_unrelated_posts_not_duplicate():
    words_a = rb.extract_signature_words("Сдам уютную квартиру рядом с метро, звоните")
    words_b = rb.extract_signature_words("Продаю диван, самовывоз, недорого")
    assert rb.is_duplicate(words_b, [list(words_a)]) is False


# ==================== ДВОЙНЫЕ ПОСТЫ (ФОТО + ЦЕНА ОТДЕЛЬНО) ====================

def _fake_post(post_id, text, photos=None, channel="chanA"):
    return {
        "id": post_id, "channel": channel, "date": "", "datetime": None,
        "text": text, "link": f"https://t.me/{channel}/{post_id}",
        "photos": photos or [],
    }


def test_double_post_price_continuation_gets_merged():
    # реальный паттерн канала Find_flat: фото+описание одним постом, а цена
    # и контакт — отдельным постом сразу следом, без единого фото и без
    # собственного признака нового объявления (только цена/контакт/хэштеги)
    photo_post = _fake_post(
        40001,
        "2-к квартира, м.Преображенская площадь, 60,7 м², 5 этаж.",
        photos=["https://cdn1.telesco.pe/file/a.jpg"],
    )
    continuation = _fake_post(
        40011,
        "Готова к заселению.\nАрендная плата: 120.000₽ / месяц + ку, залог 80.000₽.\n"
        "Для связи: @aniaettinger\n#аренда2к\n#квартиры",
    )
    merged = rb._merge_price_continuation_posts([photo_post, continuation])
    assert [p["id"] for p in merged] == [40001]
    assert rb.extract_price(merged[0]["text"]) == 120000
    assert rb.extract_contacts(merged[0]["text"]) == "@aniaettinger"


def test_independent_next_post_is_not_merged():
    # следующий пост — самостоятельное объявление (явно указан тип жилья),
    # а не обрубок с ценой — склеивать не нужно
    first = _fake_post(1, "Сдаётся комната, метро Сокольники, фото внутри", photos=["x.jpg"])
    second = _fake_post(2, "Сдаётся 1-к квартира, 60000 руб, звоните")
    merged = rb._merge_price_continuation_posts([first, second])
    assert [p["id"] for p in merged] == [1, 2]


def test_continuation_from_different_channel_is_not_merged():
    first = _fake_post(1, "2-к квартира, фото внутри", photos=["x.jpg"], channel="chanA")
    continuation = _fake_post(2, "Арендная плата: 100.000₽, @someone", channel="chanB")
    merged = rb._merge_price_continuation_posts([first, continuation])
    assert [p["id"] for p in merged] == [1, 2]


def test_unrelated_post_with_bare_phone_number_is_not_merged():
    # раньше "нет фото + нет типа жилья + есть хоть какой-то контакт" было
    # достаточным условием для склейки — два совсем не связанных поста
    # (продажа дивана и следующий пост с номером телефона в подписи) могли
    # склеиться просто потому, что во втором нашёлся номер телефона
    first = _fake_post(1, "Продам диван, самовывоз, отличное состояние", photos=["a.jpg"])
    second = _fake_post(2, "Ремонт свежий, рядом парк, звоните 89161234567")
    merged = rb._merge_price_continuation_posts([first, second])
    assert [p["id"] for p in merged] == [1, 2]


def test_double_post_merge_works_across_pagination_boundary():
    # send_recent_matching_ads/фильтр "Применить" тянут историю канала
    # постранично (fetch_channel_posts_since); склейка двойных постов
    # раньше шла только ВНУТРИ одной страницы — если фото-пост и его
    # продолжение с ценой попадали на границу двух страниц, каждая
    # страница видела только половину пары, и склейка не срабатывала
    import datetime as dt

    def fake_fetch(channel, before=None):
        if before is None:
            # новая страница: только продолжение с ценой — фото-пост уже
            # "утёк" на более старую (следующую) страницу
            return [{
                "id": 21, "channel": channel, "text": "Арендная плата: 100.000₽, звоните",
                "photos": [], "datetime": None,
            }]
        return [{
            "id": 20, "channel": channel, "text": "2-к квартира, метро Тестовая",
            "photos": ["x.jpg"], "datetime": None,
        }]

    real_fetch = rb.fetch_channel_posts
    rb.fetch_channel_posts = fake_fetch
    try:
        cutoff = dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc)
        posts = rb.fetch_channel_posts_since("chanA", cutoff, max_pages=2)
    finally:
        rb.fetch_channel_posts = real_fetch

    assert [p["id"] for p in posts] == [20]
    assert rb.extract_price(posts[0]["text"]) == 100000

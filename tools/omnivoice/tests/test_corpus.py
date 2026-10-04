from omnivoice import corpus


def test_good_sentence_rules():
    assert corpus.good_sentence("Во славу Плети, и пусть никто не уйдёт живым.")
    assert not corpus.good_sentence("Слишком коротко.")                       # < 4 слов
    assert not corpus.good_sentence("В 1999 году всё изменилось навсегда.")   # цифры
    assert not corpus.good_sentence("Он открыл Windows и ушёл.")             # латиница
    assert not corpus.good_sentence("Сотрудники МВД и ФСБ пришли рано утром.")  # аббревиатуры
    assert not corpus.good_sentence(" ".join(["слово"] * 21) + ".")           # > 20 слов


def test_pick_user_lines_first_and_minutes_budget():
    pool = [f"Это предложение номер {w} для проверки выбора." for w in
            ("один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять", "десять")]
    out = corpus.pick(pool, ["Ты не надейся на быструю смерть!", "   ", ""], minutes=0.1, chars_per_sec=10)
    assert out[0] == ("Ты не надейся на быструю смерть!", "user")
    assert all(src == "corpus" for _, src in out[1:]) and len(out) < 1 + len(pool)
    budget = 0.1 * 60 * 10  # символов
    assert sum(len(t) for t, _ in out[:-1]) < budget <= sum(len(t) for t, _ in out) + len(out[-1][0])


def test_pick_prefers_new_bigrams():
    pool = ["ааа ааа ааа ааа", "бвг дежз ийк лмн", "ааа ааа ааа ааб"]
    out = corpus.pick(pool, [], minutes=0.02, chars_per_sec=10)
    assert out[0][0] == "бвг дежз ийк лмн"


def test_bundled_russian_corpus():
    lines = corpus.load("ru")
    assert len(lines) >= 3000 and all(corpus.good_sentence(s) for s in lines[:200])
    assert corpus.load("xx") == []

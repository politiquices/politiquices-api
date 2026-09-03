from src.chave import extract_full_article


class TestExtractFullArticle:
    def test_single_multi_paragraph_article_keeps_every_paragraph(self):
        # Real shape sampled from PUBLICO-19940309-117: a kicker line, the title, then several
        # long paragraphs with no short line in between them.
        doc_text = (
            "Quebra do PIB deveu-se a política monetária\n"
            "Catroga critica política económica de Cavaco\n"
            "«O papel central da política monetária na luta contra a inflação, implicando taxas "
            "de juro reais elevadas e apreciação do escudo no período 1990-92» constituiu um dos "
            "«factores internos na economia portuguesa explicativos da queda conjuntural».\n"
            "Além desta apreciação feita à política seguida naquele período e à quebra da procura "
            "externa ocorrida desde então, outros factores foram ainda adiantados por Catroga.\n"
        )
        title, author, text = extract_full_article(doc_text)
        assert title == "Catroga critica política económica de Cavaco"
        assert author is None
        assert "papel central da política monetária" in text
        assert "quebra da procura externa" in text

    def test_bundled_briefs_stop_at_the_next_short_title_line(self):
        # Real shape sampled from PUBLICO-19940305-001: several unrelated one-paragraph briefs
        # concatenated under a single doc id, alternating short title / long paragraph.
        doc_text = (
            "Mediatecas\n"
            "O primeiro encontro distrital sobre «Mediatecas e Centro de Recursos na Escola» "
            "terminou ontem na Moita, distrito de Setúbal, com a participação de uma centena de "
            "docentes, investigadores e outros profissionais interessados no tema.\n"
            "Espírito Santo\n"
            "A ESCOLA Superior de Artes Decorativas da Fundação Ricardo Espírito Santo procede, "
            "na próxima quarta-feira, à entrega dos diplomas dos finalistas de 1992-93.\n"
        )
        title, author, text = extract_full_article(doc_text)
        assert title == "Mediatecas"
        assert author is None
        assert "Centro de Recursos na Escola" in text
        assert "Espírito Santo" not in text

    def test_byline_line_is_split_out_as_author_not_kept_as_title(self):
        # Real shape sampled from PUBLICO-19940608-097: kicker, quoted pull-quote subtitle,
        # reporter's byline, then the body -- the byline used to be mistaken for the title.
        doc_text = (
            "Guterres e Vitorino reagem no Largo do Carmo às acusações de Cavaco\n"
            "«Vai valer tudo para intimidar os portugueses»\n"
            "Jerónimo Pimentel\n"
            "Guterres quis responder às acusações de Cavaco. Para isso, dramatizou, usando como o "
            "primeiro-ministro um tom mais intimista a que acrescentou um ar de indignação.\n"
        )
        title, author, text = extract_full_article(doc_text)
        assert title == "«Vai valer tudo para intimidar os portugueses»"
        assert author == "Jerónimo Pimentel"
        assert "Guterres quis responder" in text

    def test_byline_without_a_preceding_title_line_is_kept_as_the_title(self):
        # If a name-shaped line is the very first line, there's no earlier line to promote to
        # title, so it's better shown as the title than dropped entirely.
        doc_text = "Ana Gomes\nUm parágrafo qualquer com mais de quinze palavras para servir de corpo do artigo completo.\n"
        title, author, text = extract_full_article(doc_text)
        assert title == "Ana Gomes"
        assert author is None

    def test_no_qualifying_line_returns_none(self):
        assert extract_full_article("short\nlines\nonly\n") is None

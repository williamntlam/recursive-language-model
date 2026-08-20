from rlm.domains.corpus import load_corpus
from tests.util import FIXTURE_CORPUS, make_rlm, repl


def test_corpus_loads_three_docs():
    corpus = load_corpus(FIXTURE_CORPUS)
    assert len(corpus.docs) == 3
    ids = {d.id for d in corpus.docs}
    assert len(ids) == 3


def test_research_combines_two_docs_ignores_distractor(tmp_path):
    rlm, _ = make_rlm(
        tmp_path,
        [
            repl(
                "hits_a = corpus.search('recursive inference')\n"
                "hits_b = corpus.search('rolling summaries')\n"
                "soup = corpus.search('Tomato soup')\n"
                "a_id = hits_a[0].doc_id\n"
                "b_id = hits_b[0].doc_id\n"
                "report = (\n"
                "  f'Disagree: {a_id} claims recursive inference; '\n"
                "  f'{b_id} claims compaction/summaries are enough. '\n"
                "  f'Distractor soup hits={len(soup)} ignored for the claim.'\n"
                ")\n"
                "FINAL_VAR('report')\n"
            )
        ],
    )
    out = rlm.research(FIXTURE_CORPUS, "Where do the papers disagree?")
    assert "doc-" in out.response
    assert out.response.count("doc-") >= 2
    assert "recursive" in out.response.lower()
    assert "soup" in out.response.lower()  # mentioned as ignored

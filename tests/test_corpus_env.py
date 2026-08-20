from rlm.domains.corpus import load_corpus
from tests.util import FIXTURE_CORPUS, make_rlm, repl


def test_corpus_loads_three_docs():
    corpus = load_corpus(FIXTURE_CORPUS)
    assert len(corpus.docs) == 3
    ids = {d.id for d in corpus.docs}
    assert len(ids) == 3


def test_search_hit_is_subscriptable():
    corpus = load_corpus(FIXTURE_CORPUS)
    hit = corpus.search("recursive")[0]
    assert hit["doc_id"] == hit.doc_id
    assert hit[0] == hit.doc_id
    doc_id, line_no, snippet = hit
    assert doc_id == hit.doc_id
    assert "recursive" in snippet.lower()


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


def test_corpus_ask_sends_doc_to_leaf(tmp_path):
    rlm, client = make_rlm(
        tmp_path,
        [
            repl(
                "hits = corpus.search('recursive inference')\n"
                "out = corpus.ask(hits[0].doc_id, 'One-sentence claim.')\n"
                "FINAL(out)\n"
            ),
            "leaf-claim",
        ],
    )
    out = rlm.research(FIXTURE_CORPUS, "What does paper A claim?")
    assert out.response == "leaf-claim"
    assert out.usage.subcalls >= 1
    leaf = "\n".join(m.content for m in client.calls[1])
    assert "recursive inference" in leaf.lower()


def test_corpus_explore_spawns_child(tmp_path):
    rlm, client = make_rlm(
        tmp_path,
        [
            repl(
                "ans = corpus.explore("
                "'Search recursive inference; FINAL the doc id')\n"
                "FINAL(ans)\n"
            ),
            repl(
                "hits = corpus.search('recursive inference')\n"
                "FINAL(hits[0].doc_id)\n"
            ),
        ],
    )
    out = rlm.research(FIXTURE_CORPUS, "Which doc?")
    assert out.response.startswith("doc-")
    assert out.usage.subcalls >= 1
    assert client.models[1] == "gpt-5"

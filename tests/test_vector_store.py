from vector_store import SearchResults, VectorStore


def test_from_chroma_unwraps_first_row():
    raw = {
        "documents": [["d1", "d2"]],
        "metadatas": [[{"a": 1}]],
        "distances": [[0.1]],
    }
    results = SearchResults.from_chroma(raw)
    assert results.documents == ["d1", "d2"]
    assert results.error is None


def test_empty_factory_sets_error_and_is_empty():
    results = SearchResults.empty("no match")
    assert results.error == "no match"
    assert results.is_empty() is True


def test_is_empty_false_with_documents():
    assert SearchResults(["x"], [{}], [0.0]).is_empty() is False


def _filter(course_title, lesson_number):
    return VectorStore._build_filter(
        VectorStore.__new__(VectorStore), course_title, lesson_number
    )


def test_build_filter_none_when_no_params():
    assert _filter(None, None) is None


def test_build_filter_course_only():
    assert _filter("MCP", None) == {"course_title": "MCP"}


def test_build_filter_both():
    assert _filter("MCP", 2) == {
        "$and": [{"course_title": "MCP"}, {"lesson_number": 2}]
    }

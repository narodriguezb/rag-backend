from document_processor import DocumentProcessor


def test_chunk_text_normalizes_whitespace_single_chunk():
    dp = DocumentProcessor(chunk_size=100, chunk_overlap=0)
    assert dp.chunk_text("Hello   world.\n\nThis  is fine.") == [
        "Hello world. This is fine."
    ]


def test_chunk_text_splits_when_exceeding_size():
    dp = DocumentProcessor(chunk_size=15, chunk_overlap=0)
    assert dp.chunk_text("Hello world. This is fine.") == [
        "Hello world.",
        "This is fine.",
    ]


def test_chunk_text_overlap_repeats_boundary_sentence():
    dp = DocumentProcessor(chunk_size=20, chunk_overlap=10)
    assert dp.chunk_text("Aaaaaa. Bbbbbb. Cccccc.") == [
        "Aaaaaa. Bbbbbb.",
        "Bbbbbb. Cccccc.",
        "Cccccc.",
    ]


def test_chunk_text_empty_returns_no_chunks():
    dp = DocumentProcessor(chunk_size=100, chunk_overlap=0)
    assert dp.chunk_text("   ") == []


def test_process_document_parses_metadata_and_lessons(tmp_path):
    content = (
        "Course Title: My Course\n"
        "Course Link: http://c\n"
        "Course Instructor: Bob\n"
        "\n"
        "Lesson 0: Intro\n"
        "Lesson Link: http://l0\n"
        "This is the intro content.\n"
    )
    f = tmp_path / "c.txt"
    f.write_text(content, encoding="utf-8")

    dp = DocumentProcessor(chunk_size=800, chunk_overlap=100)
    course, chunks = dp.process_course_document(str(f))

    assert course.title == "My Course"
    assert course.instructor == "Bob"
    assert len(course.lessons) == 1
    assert course.lessons[0].lesson_number == 0
    assert course.lessons[0].lesson_link == "http://l0"

    assert len(chunks) == 1
    assert chunks[0].content == "Course My Course Lesson 0 content: This is the intro content."
    assert chunks[0].course_title == "My Course"
    assert chunks[0].lesson_number == 0

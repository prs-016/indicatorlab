from src.example import project_summary


def test_project_summary() -> None:
    assert project_summary("demo") == "demo: ready for data science work"

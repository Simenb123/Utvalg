import inspect

from src.pages.dataset.frontend.pane import DatasetPane


def test_dataset_pane_exposes_legacy_api():
    # Eldre deler av repoet forventer disse APIene
    assert hasattr(DatasetPane, "build_dataset")
    assert hasattr(DatasetPane, "get_last_build")
    assert hasattr(DatasetPane, "frm")


def test_dataset_pane_init_accepts_title_positional():
    sig = inspect.signature(DatasetPane.__init__)
    params = list(sig.parameters.values())

    # self, master, title, ...
    assert len(params) >= 3
    assert params[2].name == "title"
    assert params[2].default == "Dataset"

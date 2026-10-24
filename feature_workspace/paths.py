"""Source inputs and bounded output paths for feature preparation."""
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
REPO_ROOT = WORKSPACE.parent
TRAIN_INPUT = REPO_ROOT / "data/traning_data/train"
GENERATED = WORKSPACE / "generated"


def output_path(relative_path: str | Path) -> Path:
    """Return an output filename within generated/, rejecting escapes/symlinks.

    This helper does not write files or change source-data permissions. Future
    feature writers must use it for their destination paths.
    """
    relative = Path(relative_path)
    base = GENERATED.resolve()
    source = (REPO_ROOT / "data").resolve()
    if relative.is_absolute():
        raise ValueError("Pass a relative output filename")
    if not base.is_relative_to(WORKSPACE) or base.is_relative_to(source):
        raise ValueError("Generated directory must stay in the feature workspace")
    destination = (base / relative).resolve()
    if destination == base or not destination.is_relative_to(base):
        raise ValueError("Output must stay inside feature_workspace/generated/")
    return destination

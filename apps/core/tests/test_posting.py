import pytest

from apps.core.exceptions import PostedRecordImmutableError
from apps.core.posting import PostingState, ensure_record_is_mutable


def test_draft_record_is_mutable():
    ensure_record_is_mutable(PostingState.DRAFT)


@pytest.mark.parametrize("state", [PostingState.POSTED, PostingState.REVERSED])
def test_non_draft_record_requires_traceable_correction(state):
    with pytest.raises(PostedRecordImmutableError, match="traceable correction"):
        ensure_record_is_mutable(state)

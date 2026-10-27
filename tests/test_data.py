import pytest

from oakgpt.tokenization import Tokenizer
from oakgpt.training.data import TokenWindows


@pytest.mark.parametrize("kind", ["byte", "character"])
def test_tokenizer_roundtrip_and_serialization(kind):
    text = "Oak 🌳 åäö\n"
    tokenizer = Tokenizer.fit(kind, text)
    ids = tokenizer.encode(text, bos=True, eos=True)
    assert tokenizer.decode(ids) == text
    assert max(ids) < tokenizer.vocab_size
    assert Tokenizer.from_dict(tokenizer.to_dict()).encode(text) == tokenizer.encode(text)


def test_character_unknown_and_training_only_vocabulary():
    tokenizer = Tokenizer.fit("character", "abc")
    assert tokenizer.encode("z") == [tokenizer.unk_id]
    assert tokenizer.decode([tokenizer.unk_id]) == "�"


def test_windows_shift_targets_and_drop_incomplete_tail():
    data = TokenWindows(list(range(12)), 4)
    assert len(data) == 2
    assert data[0][0].tolist() == [0, 1, 2, 3]
    assert data[0][1].tolist() == [1, 2, 3, 4]
    assert data[1][0].tolist() == [4, 5, 6, 7]
    with pytest.raises(ValueError):
        TokenWindows([1, 2], 4)

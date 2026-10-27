import pytest
import torch

from oakgpt.config import ModelConfig
from oakgpt.model import TransformerLM


@pytest.mark.parametrize("position", ["learned", "sinusoidal"])
def test_causal_attention_does_not_read_future(position):
    torch.manual_seed(42)
    config = ModelConfig(
        vocab_size=19,
        context_length=12,
        d_model=15,
        n_heads=3,
        n_layers=2,
        dropout=0,
        positional_encoding=position,
    )
    model = TransformerLM(config).eval()
    tokens = torch.randint(0, 19, (2, 12))
    altered = tokens.clone()
    altered[:, 6:] = (altered[:, 6:] + 1) % 19
    torch.testing.assert_close(model(tokens)[:, :6], model(altered)[:, :6])
    assert not torch.allclose(model(tokens)[:, 6:], model(altered)[:, 6:])
    assert model.lm_head.weight is model.token_embedding.weight


def test_forward_backward_and_overfit():
    torch.manual_seed(1)
    model = TransformerLM(
        ModelConfig(vocab_size=8, context_length=8, d_model=16, n_heads=2, n_layers=1, dropout=0)
    )
    inputs = torch.tensor([[0, 3, 4, 3, 4, 3, 4, 3]])
    targets = torch.tensor([[3, 4, 3, 4, 3, 4, 3, 1]])
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.03)
    initial = model.loss(inputs, targets).item()
    for _ in range(35):
        optimizer.zero_grad()
        loss = model.loss(inputs, targets)
        loss.backward()
        assert all(torch.isfinite(p.grad).all() for p in model.parameters() if p.grad is not None)
        optimizer.step()
    assert model.loss(inputs, targets).item() < initial * 0.15


def test_context_and_config_errors():
    with pytest.raises(ValueError, match="divisible"):
        ModelConfig(d_model=13, n_heads=4)
    model = TransformerLM(ModelConfig(context_length=4))
    with pytest.raises(ValueError, match="context"):
        model(torch.zeros(1, 5, dtype=torch.long))

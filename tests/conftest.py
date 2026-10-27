import torch


def pytest_sessionstart(session: object) -> None:
    torch.set_num_threads(2)

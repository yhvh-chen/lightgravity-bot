"""Reader v2/CTC model math used by the pinned English ASR runtime.

Derived from the public Apache-2.0
``mlboydaisuke/EmbeddingGemma-2-Transcribe-Reader`` reader code (``train/model.py``)
and the LG-159 harness.  The released reader config in this version uses
architecture ``a`` (6 pre-LayerNorm transformer layers, 512-d model, 8 heads,
FFN 2048, rotary positions, 768-d output).  Not a generic model loader and not a
substitute for an ASR engine: the weights and word table are fixed by SHA-256 in
:mod:`lightgravity.asr.pins`.

Attribution/licence: see ``backend/lightgravity/asr/NOTICE`` and
``backend/lightgravity/asr/LICENSE.reader``.
"""

from __future__ import annotations

import math

import torch
import torch.nn as nn
import torch.nn.functional as F

D_IN, D_OUT = 512, 768


def key_mask(lengths: torch.Tensor, T: int) -> torch.Tensor:
    """[B, 1, 1, T] bool, True = a real token (attend)."""

    return (torch.arange(T, device=lengths.device)[None, :] < lengths[:, None])[:, None, None, :]


def rope(T: int, dim: int, base: float, device: torch.device) -> tuple[torch.Tensor, torch.Tensor]:
    inv = 1.0 / (base ** (torch.arange(0, dim, 2, device=device, dtype=torch.float32) / dim))
    f = torch.arange(T, device=device, dtype=torch.float32)[:, None] * inv[None, :]
    emb = torch.cat([f, f], dim=-1)
    return emb.cos(), emb.sin()


def rotate_half(x: torch.Tensor) -> torch.Tensor:
    x1, x2 = x.chunk(2, dim=-1)
    return torch.cat([-x2, x1], dim=-1)


class Block(nn.Module):
    def __init__(self, d: int, heads: int, ffn: int) -> None:
        super().__init__()
        self.heads = heads
        self.ln1 = nn.LayerNorm(d)
        self.qkv = nn.Linear(d, 3 * d)
        self.proj = nn.Linear(d, d)
        self.ln2 = nn.LayerNorm(d)
        self.ff1 = nn.Linear(d, ffn)
        self.ff2 = nn.Linear(ffn, d)

    def forward(
        self, x: torch.Tensor, mask: torch.Tensor, cos: torch.Tensor, sin: torch.Tensor
    ) -> torch.Tensor:
        B, T, D = x.shape
        q, k, v = (
            self.qkv(self.ln1(x))
            .view(B, T, 3, self.heads, D // self.heads)
            .permute(2, 0, 3, 1, 4)
        )
        q = q * cos + rotate_half(q) * sin
        k = k * cos + rotate_half(k) * sin
        a = F.scaled_dot_product_attention(q, k, v, attn_mask=mask)
        x = x + self.proj(a.transpose(1, 2).reshape(B, T, D))
        return x + self.ff2(F.gelu(self.ff1(self.ln2(x))))


class ReaderA(nn.Module):
    def __init__(
        self,
        d: int = 512,
        layers: int = 6,
        heads: int = 8,
        ffn: int = 2048,
        rope_base: float = 10000.0,
    ) -> None:
        super().__init__()
        self.heads, self.rope_base = heads, rope_base
        self.ln_in = nn.LayerNorm(D_IN)
        self.inp = nn.Linear(D_IN, d)
        self.blocks = nn.ModuleList([Block(d, heads, ffn) for _ in range(layers)])
        self.ln_out = nn.LayerNorm(d)
        self.out = nn.Linear(d, D_OUT)

    def forward(self, x: torch.Tensor, lengths: torch.Tensor) -> torch.Tensor:
        T = x.shape[1]
        mask = key_mask(lengths, T)
        cos, sin = rope(T, self.inp.out_features // self.heads, self.rope_base, x.device)
        h = self.inp(self.ln_in(x))
        for blk in self.blocks:
            h = blk(h, mask, cos, sin)
        return self.out(self.ln_out(h))


class Reader(nn.Module):
    """Reader body + blank head + learned CTC scale."""

    def __init__(
        self,
        arch: str,
        n_vocab: int,
        *,
        layers: int = 6,
    ) -> None:
        super().__init__()
        if arch != "a":
            raise ValueError(f"unsupported reader architecture {arch!r}; this runtime pins 'a'")
        self.arch = arch
        self.body = ReaderA(layers=layers)
        self.blank = nn.Linear(D_OUT, 1)
        nn.init.constant_(self.blank.bias, math.log(n_vocab))
        self.log_scale = nn.Parameter(torch.tensor(math.log(20.0)))

    @property
    def scale(self) -> torch.Tensor:
        return self.log_scale.exp()

    def forward(self, x: torch.Tensor, lengths: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Return unit vectors [B, T, 768] and blank logits [B, T]."""

        v = self.body(x, lengths)
        return F.normalize(v, dim=-1), self.blank(v).squeeze(-1)


def collapse(labels: list[int], blank_id: int) -> list[int]:
    """Greedy CTC read-out: merge repeats, drop blanks."""

    out: list[int] = []
    prev: int | None = None
    for cls in labels:
        if cls != prev and cls != blank_id:
            out.append(cls)
        prev = cls
    return out


__all__ = ["Reader", "ReaderA", "Block", "collapse"]

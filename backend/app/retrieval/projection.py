"""Dimensionality reduction for the 3D knowledge map: PCA via SVD (numpy only, deterministic)."""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def project_3d(vectors: Sequence[Sequence[float]]) -> tuple[np.ndarray, list[float]]:
    """Project embedding vectors onto their top 3 principal components.

    Returns `(coords, explained)`: `coords` has shape (n, 3) scaled into [-1, 1]; `explained` is the share of
    variance each of the 3 axes carries. Degenerate inputs (no points, one point, identical points, fewer than
    3 dimensions of variance) yield zeros on the missing axes instead of raising. Axis signs are fixed so the
    same data always renders the same map.
    """
    x = np.asarray(vectors, dtype=np.float64)
    if x.ndim != 2 or x.shape[0] == 0:
        return np.zeros((0, 3)), [0.0, 0.0, 0.0]
    n = x.shape[0]
    centred = x - x.mean(axis=0)
    if n == 1 or not np.any(centred):
        return np.zeros((n, 3)), [0.0, 0.0, 0.0]

    _, s, vt = np.linalg.svd(centred, full_matrices=False)
    k = min(3, vt.shape[0])
    comps = vt[:k].copy()
    for i in range(k):  # deterministic orientation: largest-magnitude loading is positive
        if comps[i][np.argmax(np.abs(comps[i]))] < 0:
            comps[i] *= -1
    coords = centred @ comps.T
    variance = s**2
    total = float(variance.sum()) or 1.0
    explained = [float(v / total) for v in variance[:k]]

    if k < 3:
        coords = np.hstack([coords, np.zeros((n, 3 - k))])
        explained += [0.0] * (3 - k)
    scale = float(np.abs(coords).max())
    if scale > 0:
        coords = coords / scale
    return coords, explained

from __future__ import annotations

import numpy as np

from app.retrieval.projection import project_3d


def test_empty_input():
    coords, explained = project_3d([])
    assert coords.shape == (0, 3)
    assert explained == [0.0, 0.0, 0.0]


def test_single_point_and_identical_points_do_not_raise():
    c1, _ = project_3d([[1.0, 2.0, 3.0]])
    assert c1.shape == (1, 3) and not c1.any()
    c2, e2 = project_3d([[1.0, 1.0]] * 4)
    assert c2.shape == (4, 3) and not c2.any() and e2 == [0.0, 0.0, 0.0]


def test_output_shape_and_range():
    rng = np.random.default_rng(0)
    coords, explained = project_3d(rng.normal(size=(40, 16)))
    assert coords.shape == (40, 3)
    assert np.abs(coords).max() <= 1.0 + 1e-9
    assert abs(coords).max() > 0.99  # scaled to fill the cube
    assert all(0 <= e <= 1 for e in explained)
    assert explained[0] >= explained[1] >= explained[2]


def test_deterministic():
    rng = np.random.default_rng(1)
    data = rng.normal(size=(25, 8))
    a, _ = project_3d(data)
    b, _ = project_3d(data)
    assert np.array_equal(a, b)


def test_low_rank_data_pads_missing_axes_with_zeros():
    data = [[0.0, 0.0], [1.0, 1.0], [2.0, 2.0], [3.0, 3.0]]  # a line: one axis of variance
    coords, explained = project_3d(data)
    assert coords.shape == (4, 3)
    assert not coords[:, 1:].any()
    assert explained[0] > 0.99


def test_clusters_stay_separated():
    rng = np.random.default_rng(2)
    a = rng.normal(0, 0.05, size=(20, 10))
    b = rng.normal(0, 0.05, size=(20, 10)) + 5.0
    coords, _ = project_3d(np.vstack([a, b]))
    gap = abs(coords[:20, 0].mean() - coords[20:, 0].mean())
    assert gap > 1.0

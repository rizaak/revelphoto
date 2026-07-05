import numpy as np

from revelado.simulate import simulate


def _gray(value=120, shape=(100, 200, 3)):
    return np.full(shape, value, dtype=np.uint8)


def test_exposure_brightens():
    out = simulate(_gray(), exposure=1.0)
    assert out.mean() > _gray().mean() * 1.5


def test_warm_shift_raises_red_lowers_blue():
    out = simulate(_gray(), temp_shift=800)
    b, _, r = out[..., 0].mean(), out[..., 1].mean(), out[..., 2].mean()
    assert r > 120 and b < 120


def test_crop_reduces_dimensions():
    out = simulate(_gray(), crop=(0.25, 0.25, 0.75, 0.75))
    assert out.shape[0] == 50 and out.shape[1] == 100


def test_contrast_increases_spread():
    img = _gray()
    img[:, :100] = 80
    img[:, 100:] = 170
    out = simulate(img, contrast=50)
    assert out.std() > img.std()


def test_no_adjust_is_identity():
    img = _gray()
    out = simulate(img)
    assert np.array_equal(out, img)


def test_output_clipped_uint8():
    out = simulate(_gray(250), exposure=2.0)
    assert out.dtype == np.uint8 and out.max() <= 255

import math

import numpy as np
import torch
from mmcv import imresize

from ..registry import PIPELINES


@PIPELINES.register_module()
class SRResize:
    """Resize image by a scale, including upsampling and downsampling.

        Image will be loaded from the input_key and the result will be saved
            in the specified output_key (can equal to input_key).

    Args:
        scale (float): The resampling scale. scale > 0.
            scale > 1: upsampling.
            scale < 1: downsampling.
        input_key (str): The input key.
        output_key (str): The output key.
        interpolation (str): Interpolation method, accepted values are
            "nearest", "bilinear", "bicubic", "area", "lanczos" for 'cv2'
            backend, "nearest", "bilinear", "bicubic", "box", "lanczos",
            "hamming" for 'pillow' backend.
            Default: "bicubic".
        backend (str | None): The image resize backend type. Options are `cv2`,
            `pillow`, `None`. If backend is None, the global imread_backend
            specified by ``mmcv.use_backend()`` will be used.
            Default: "pillow".
    """

    def __init__(self,
                 scale,
                 input_key,
                 output_key,
                 interpolation='bicubic',
                 backend='pillow'):
        self.scale = scale
        self.input_key = input_key
        self.output_key = output_key
        self.interpolation = interpolation
        self.backend = backend

    def __call__(self, results):
        """Call function.

        Args:
            results (dict): A dict containing the necessary information and
                data for augmentation. self.input_key is required.

        Returns:
            dict: A dict containing the processed data and information.
                supplement self.output_key to keys.
        """
        assert self.input_key in results, f'Cannot find {self.input_key}.'
        image_in = results[self.input_key]
        h_in, w_in = image_in.shape[:2]
        h_out = math.floor(h_in * self.scale + 1e-9)
        w_out = math.floor(w_in * self.scale + 1e-9)
        image_out = resize_fn(image_in, (w_out, h_out), self.interpolation,
                              self.backend)

        results[self.output_key] = image_out

        return results

    def __repr__(self):
        repr_str = self.__class__.__name__
        repr_str += (f' scale={self.scale}, '
                     f'input_key={self.input_key}, '
                     f'output_key={self.output_key}, '
                     f'interpolation={self.interpolation}, '
                     f'backend={self.backend}')

        return repr_str


@PIPELINES.register_module()
class RandomDownSampling:
    """Generate LQ image from GT (and crop), which will randomly pick a scale.

    Args:
        scale_min (float): The minimum of upsampling scale, inclusive.
            Default: 1.0.
        scale_max (float): The maximum of upsampling scale, exclusive.
            Default: 4.0.
        patch_size (int): The cropped lr patch size.
            Default: None, means no crop.
        interpolation (str): Interpolation method, accepted values are
            "nearest", "bilinear", "bicubic", "area", "lanczos" for 'cv2'
            backend, "nearest", "bilinear", "bicubic", "box", "lanczos",
            "hamming" for 'pillow' backend.
            Default: "bicubic".
        backend (str | None): The image resize backend type. Options are `cv2`,
            `pillow`, `None`. If backend is None, the global imread_backend
            specified by ``mmcv.use_backend()`` will be used.
            Default: "pillow".

        Scale will be picked in the range of [scale_min, scale_max).
    """

    def __init__(self,
                 scale_min=1.0,
                 scale_max=4.0,
                 patch_size=None,
                 interpolation='bicubic',
                 backend='pillow'):
        assert scale_max >= scale_min
        self.scale_min = scale_min
        self.scale_max = scale_max
        self.patch_size = patch_size
        self.interpolation = interpolation
        self.backend = backend

    def __call__(self, results):
        """Call function.

        Args:
            results (dict): A dict containing the necessary information and
                data for augmentation. 'gt' is required.

        Returns:
            dict: A dict containing the processed data and information.
                modified 'gt', supplement 'lq' and 'scale' to keys.
        """
        img = results['gt']
        scale = np.random.uniform(self.scale_min, self.scale_max)

        if self.patch_size is None:
            h_lr = math.floor(img.shape[-3] / scale + 1e-9)
            w_lr = math.floor(img.shape[-2] / scale + 1e-9)
            img = img[:round(h_lr * scale), :round(w_lr * scale), :]
            img_down = resize_fn(img, (w_lr, h_lr), self.interpolation,
                                 self.backend)
            crop_lr, crop_hr = img_down, img
        else:
            w_lr = self.patch_size
            w_hr = round(w_lr * scale)
            x0 = np.random.randint(0, img.shape[-3] - w_hr)
            y0 = np.random.randint(0, img.shape[-2] - w_hr)
            crop_hr = img[x0:x0 + w_hr, y0:y0 + w_hr, :]
            crop_lr = resize_fn(crop_hr, w_lr, self.interpolation,
                                self.backend)
        results['gt'] = crop_hr
        results['lq'] = crop_lr
        results['scale'] = scale

        return results

    def __repr__(self):
        repr_str = self.__class__.__name__
        repr_str += (f' scale_min={self.scale_min}, '
                     f'scale_max={self.scale_max}, '
                     f'patch_size={self.patch_size}, '
                     f'interpolation={self.interpolation}, '
                     f'backend={self.backend}')

        return repr_str


def resize_fn(img, size, interpolation='bicubic', backend='pillow'):
    """Resize the given image to a given size.

    Args:
        img (ndarray | torch.Tensor): The input image.
        size (int | tuple[int]): Target size w or (w, h).
        interpolation (str): Interpolation method, accepted values are
            "nearest", "bilinear", "bicubic", "area", "lanczos" for 'cv2'
            backend, "nearest", "bilinear", "bicubic", "box", "lanczos",
            "hamming" for 'pillow' backend.
            Default: "bicubic".
        backend (str | None): The image resize backend type. Options are `cv2`,
            `pillow`, `None`. If backend is None, the global imread_backend
            specified by ``mmcv.use_backend()`` will be used.
            Default: "pillow".

    Returns:
        ndarray | torch.Tensor: `resized_img`, whose type is same as `img`.
    """
    if isinstance(size, int):
        size = (size, size)
    if isinstance(img, np.ndarray):
        return imresize(
            img, size, interpolation=interpolation, backend=backend)
    elif isinstance(img, torch.Tensor):
        image = imresize(
            img.numpy(), size, interpolation=interpolation, backend=backend)
        return torch.from_numpy(image)

    else:
        raise TypeError('img should got np.ndarray or torch.Tensor,'
                        f'but got {type(img)}')

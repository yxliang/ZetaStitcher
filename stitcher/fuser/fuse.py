import math
import numpy as np

from functools import lru_cache


def flatten(my_list):
    return [item for sublist in my_list for item in sublist]


@lru_cache()
def squircle_alpha(height, width):
    squircle = np.zeros((height, width))
    ratio = width / height
    a = width // 2
    b = height // 2
    grid = np.vstack(np.meshgrid(np.linspace(0, b - 1, b),
                                 np.linspace(0, a - 1, a))).reshape(2, -1).T
    grid = grid.astype(np.int)
    N = max(a, b)
    ps = np.logspace(np.log10(2), np.log10(50), N)
    # ps = np.ones(N) * 2
    alpha = np.linspace(0, 1, N)

    if a > b:
        dra = a / N
        ras = np.arange(0, a, dra) + 1
        rbs = ras / ratio
        drb = dra / ratio
    else:
        drb = b / N
        rbs = np.arange(0, b, drb) + 1
        ras = rbs * ratio
        dra = drb * ratio

    counter = 0
    for y, x in grid:
        j = x / dra
        k = y / drb
        i = int(max(j, k))
        for n in range(0, N - i):
            ii = i + n
            try:
                p = ps[ii]
                ra = ras[ii]
                rb = rbs[ii]
            except IndexError:
                break

            constant = math.pow(x / ra, p) + math.pow(y / rb, p)

            if constant < 1:
                break

        squircle[y + b, x + a] = alpha[ii] ** 2
        counter += 1

    squircle[:b, a:] = np.flipud(squircle[b:, a:])
    squircle[:, :a] = np.fliplr(squircle[:, a:])

    squircle /= np.amax(squircle)
    squircle = 1 - squircle

    return squircle


def fuse_queue(q, dest, debug=False):
    """Fuses a queue of images along Y, optionally applying padding.

    Parameters
    ----------
    q : :py:class:`queue.Queue`
        A queue containing elements in the form ``[slice, top_left, overlaps]``
        where `slice` is a :class:`numpy.ndarray`, `top_left` is a list
        specifying the image position in the form ``[Z, Y, X]``, `overlaps`
        is a :class:`pandas.DataFrame` specifying overlaps with adjacent tiles.
    dest : :class:`numpy.ndarray`
        Destination array.
    debug: bool
        Whether to overlay debug information (tile edges)
    """

    while True:
        slice, pos, overlaps = q.get()

        if slice is None:
            break

        z_from = pos[0]
        z_to = z_from + slice.shape[0]

        y_from = pos[1]
        y_to = y_from + slice.shape[-2]

        x_from = pos[2]
        x_to = x_from + slice.shape[-1]

        z = np.array(flatten(overlaps[['Z_from', 'Z_to']].values))
        z = np.unique(z)
        z = np.sort(z)

        xy_weights = squircle_alpha(*slice.shape[-2::])

        z_list = list(zip(z, z[1::]))
        try:
            z_list += [(z[-1], None)]
        except IndexError:
            pass

        for zfrom, zto in z_list:
            sums = np.copy(xy_weights)
            condition = (overlaps['Z_from'] <= zfrom)
            if zto is not None:
                condition = condition & (zto <= (overlaps['Z_to']))
            else:
                condition = condition & (overlaps['Z_to'] >= z_to)

            for _, row in overlaps[condition].iterrows():
                width = row.X_to - row.X_from
                height = row.Y_to - row.Y_from
                area = width * height
                if not area:
                    continue

                # FIXME: pass size of overlapping tile
                w = squircle_alpha(*slice.shape[-2::])[:height, :width]

                if row.X_from == 0:
                    w = np.fliplr(w)
                if row.Y_from == 0:
                    w = np.flipud(w)

                xy_index = np.index_exp[row.Y_from:row.Y_to,
                                        row.X_from:row.X_to]
                sums[xy_index] += w

            if zto is None:
                slice_index = np.index_exp[zfrom:, ...]
            else:
                slice_index = np.index_exp[zfrom:zto, ...]
            with np.errstate(invalid='ignore'):
                slice[slice_index] *= (xy_weights / sums)

        if debug:
            slice[..., -2:, :] = 65000
            slice[..., -2:] = 65000

        output_roi_index = np.index_exp[z_from:z_to, ..., y_from:y_to,
                                        x_from:x_to]
        dest[output_roi_index] += slice

        q.task_done()
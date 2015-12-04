# Copyright (c) 2012-2015 by the GalSim developers team on GitHub
# https://github.com/GalSim-developers
#
# This file is part of GalSim: The modular galaxy image simulation toolkit.
# https://github.com/GalSim-developers/GalSim
#
# GalSim is free software: redistribution and use in source and binary forms,
# with or without modification, are permitted provided that the following
# conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions, and the disclaimer given in the accompanying LICENSE
#    file.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions, and the disclaimer given in the documentation
#    and/or other materials provided with the distribution.
#

import galsim
import math
import numpy
import logging

# The psf extra output type builds an Image of the PSF at the same locations as the galaxies.

# The function called at the start of each image.
def SetupExtraPSF(image, scratch, config, base, logger=None):
    image.resize(base['image_bounds'], wcs=base['wcs'])
    image.setZero()
    scratch.clear()

# The code the actually draws the PSF on a postage stamp.
def DrawPSFStamp(psf, config, base, bounds, offset, method, logger=None):
    """
    Draw an image using the given psf profile.

    @returns the resulting image.
    """
    if 'draw_method' in config:
        method = galsim.config.ParseValue(config,'draw_method',base,str)[0]
        if method not in ['auto', 'fft', 'phot', 'real_space', 'no_pixel', 'sb']:
            raise AttributeError("Invalid draw_method: %s"%method)
    else:
        method = 'auto'

    # Special: if the galaxy was shifted, then also shift the psf
    if 'shift' in base['gal']:
        gal_shift = galsim.config.GetCurrentValue('gal.shift',base, galsim.PositionD)
        if logger and logger.isEnabledFor(logging.DEBUG):
            logger.debug('obj %d: psf shift (1): %s',base['obj_num'],str(gal_shift))
        psf = psf.shift(gal_shift)

    wcs = base['wcs'].local(base['image_pos'])
    im = galsim.ImageF(bounds, wcs=wcs)
    im = psf.drawImage(image=im, offset=offset, method=method)

    if 'signal_to_noise' in config:
        if method == 'phot':
            raise NotImplementedError(
                "signal_to_noise option not implemented for draw_method = phot")

        if 'image' in base and 'noise' in base['image']:
            noise_var = galsim.config.CalculateNoiseVar(base)
        else:
            raise AttributeError("Need to specify noise level when using psf.signal_to_noise")

        sn_target = galsim.config.ParseValue(config, 'signal_to_noise', base, float)[0]

        sn_meas = math.sqrt( numpy.sum(im.array**2) / noise_var )
        flux = sn_target / sn_meas
        im *= flux

    return im


# The function to call at the end of building each stamp
def ProcessExtraPSFStamp(image, scratch, config, base, obj_num, logger=None):
    # If this doesn't exist, an appropriate exception will be raised.
    psf = base['psf']['current_val']
    draw_method = galsim.config.GetCurrentValue('image.draw_method',base,str)
    bounds = base['current_stamp'].bounds
    offset = base['stamp_offset']
    if 'offset' in base['image']:
        offset += galsim.config.ParseValue(base['image'], 'offset', base, galsim.PositionD)[0]
    psf_im = DrawPSFStamp(psf,config,base,bounds,offset,draw_method,logger)
    if 'signal_to_noise' in config:
        base['index_key'] = 'image_num'
        galsim.config.AddNoise(base,psf_im,0,logger)
        base['index_key'] = 'obj_num'
    scratch[obj_num] = psf_im

# The function to call at the end of building each image
def ProcessExtraPSFImage(image, scratch, config, base, logger=None):
    for stamp in scratch.values():
        b = stamp.bounds & image.getBounds()
        if b.isDefined():
            # This next line is equivalent to:
            #    image[b] += stamp[b]
            # except that this doesn't work through the proxy.  We can only call methods
            # that don't start with _.  Hence using the more verbose form here.
            image.setSubImage(b, image.subImage(b) + stamp[b])

# Register this as a valid extra output
from .extra import RegisterExtraOutput
RegisterExtraOutput('psf', galsim.Image, None,
                    SetupExtraPSF, ProcessExtraPSFStamp, ProcessExtraPSFImage, 
                    galsim.Image.write, galsim.Image.view)

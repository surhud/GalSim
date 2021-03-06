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

valid_gsobject_types = {
    # Note: these are just the types that need a special builder.  Most GSObject sub-classes
    # in base.py (and some elsewhere) can use the default builder, called _BuildSimple, which
    # just uses the req, opt, and single class variables.
    # See the des module for examples of how to extend this from a module.
    'None' : '_BuildNone',
    'Add' : '_BuildAdd',
    'Sum' : '_BuildAdd',
    'Convolve' : '_BuildConvolve',
    'Convolution' : '_BuildConvolve',
    'List' : '_BuildList',
    'Ring' : '_BuildRing',
    'RealGalaxy' : '_BuildRealGalaxy',
    'RealGalaxyOriginal' : '_BuildRealGalaxyOriginal',
    'OpticalPSF' : '_BuildOpticalPSF',
    'COSMOSGalaxy' : '_BuildCOSMOSGalaxy',
}

class SkipThisObject(Exception):
    """
    A class that a builder can throw to indicate that nothing went wrong, but for some
    reason, this particular object should be skipped and just move onto the next object.
    The constructor takes an optional message that will be output to the logger if 
    logging is active.
    """
    def __init__(self, message=None):
        # Using self.message gives a deprecation warning.  Avoid this by using a different name.
        self.msg = message


def BuildGSObject(config, key, base=None, gsparams={}, logger=None):
    """Build a GSObject using config dict for `key=key`.

    @param config       A dict with the configuration information.
    @param key          The key name in config indicating which object to build.
    @param base         A dict which stores potentially useful things like
                        base['rng'] = random number generator
                        base['catalog'] = input catalog for InputCat items
                        base['real_catalog'] = real galaxy catalog for RealGalaxy objects
                        Typically on the initial call to BuildGSObject(), this will be 
                        the same as config, hence the name base. [default: None]
    @param gsparams     Optionally, provide non-default GSParams items.  Any `gsparams` specified
                        at this level will be added to the list.  This should be a dict with
                        whatever kwargs should be used in constructing the GSParams object.
                        [default: {}]
    @param logger       Optionally, provide a logger for logging debug statements.
                        [default: None]

    @returns the tuple `(gsobject, safe)`, where `gsobject` is the built object, and `safe` is
             a bool that says whether it is safe to use this object again next time.
    """
    # I'd like to be able to have base=config be the default value, but python doesn't
    # allow that.  So None is the default, and if it's None, we set it to config.
    if not base:
        base = config
    if logger:
        logger.debug('obj %d: Start BuildGSObject',base['obj_num'])
 
    if isinstance(config,dict):
        if not key in config:
            raise AttributeError("key %s not found in config"%key)
    elif isinstance(config,list):
        if not key < len(config):
            raise AttributeError("Trying to build past the end of a list in config")
    else:
        raise AttributeError("BuildGSObject not given a valid dictionary")

    # Alias for convenience
    ck = config[key]
    if False:
        logger.debug('obj %d: ck = %s',base['obj_num'],str(ck))

    # Check that the input config has a type to even begin with!
    if not 'type' in ck:
        raise AttributeError("type attribute required in config.%s"%key)
    type = ck['type']

    # If we have previously saved an object and marked it as safe, then use it.
    if 'current_val' in ck and ck['current_safe']:
        if logger:
            logger.debug('obj %d: current is safe: %s',base['obj_num'],str(ck['current_val']))
        return ck['current_val'], True

    # Ring is only allowed for top level gal (since it requires special handling in 
    # multiprocessing, and that's the only place we look for it currently).
    if type == 'Ring' and key != 'gal':
        raise AttributeError("Ring type only allowed for top level gal")

    # Check if we need to skip this object
    if 'skip' in ck:
        skip = galsim.config.ParseValue(ck, 'skip', base, bool)[0]
        if skip: 
            if logger:
                logger.debug('obj %d: Skipping because field skip=True',base['obj_num'])
            raise SkipThisObject()

    # Set up the initial default list of attributes to ignore while building the object:
    ignore = [ 
        'dilate', 'dilation', 'ellip', 'rotate', 'rotation', 'scale_flux',
        'magnify', 'magnification', 'shear', 'shift', 
        'gsparams', 'skip', 'current_val', 'current_safe' 
    ]
    # There are a few more that are specific to which key we have.
    if key == 'gal':
        ignore += [ 'resolution', 'signal_to_noise', 'redshift', 're_from_res' ]
        # If redshift is present, parse it here, since it might be needed by the Build functions.
        # All we actually care about is setting the current_val, so don't assign to anything.
        if 'redshift' in ck:
            galsim.config.ParseValue(ck, 'redshift', base, float)
    elif key == 'psf':
        ignore += [ 'saved_re' ]
    elif key != 'pix':
        # As long as key isn't psf or pix, allow resolution.
        # Ideally, we'd like to check that it's something within the gal hierarchy, but
        # I don't know an easy way to do that.
        ignore += [ 'resolution' , 're_from_res' ]

    # Allow signal_to_noise for PSFs only if there is not also a galaxy.
    if 'gal' not in base and key == 'psf':
        ignore += [ 'signal_to_noise']

    # If we are specifying the size according to a resolution, then we 
    # need to get the PSF's half_light_radius.
    if 'resolution' in ck:
        if 'psf' not in base:
            raise AttributeError(
                "Cannot use gal.resolution if no psf is set.")
        if 'saved_re' not in base['psf']:
            raise AttributeError(
                'Cannot use gal.resolution with psf.type = %s'%base['psf']['type'])
        psf_re = base['psf']['saved_re']
        resolution = galsim.config.ParseValue(ck, 'resolution', base, float)[0]
        gal_re = resolution * psf_re
        if 're_from_res' not in ck:
            # The first time, check that half_light_radius isn't also specified.
            if 'half_light_radius' in ck:
                raise AttributeError(
                    'Cannot specify both gal.resolution and gal.half_light_radius')
            ck['re_from_res'] = True
        ck['half_light_radius'] = gal_re

    # Make sure the PSF gets flux=1 unless explicitly overridden by the user.
    if key == 'psf' and 'flux' not in ck and 'signal_to_noise' not in ck:
        ck['flux'] = 1

    if 'gsparams' in ck:
        gsparams = UpdateGSParams(gsparams, ck['gsparams'], 'gsparams', config)

    # See if this type has a specialized build function:
    if type in valid_gsobject_types:
        build_func = eval(valid_gsobject_types[type])
        if logger:
            logger.debug('obj %d: build_func = %s',base['obj_num'],str(build_func))
        gsobject, safe = build_func(ck, key, base, ignore, gsparams, logger)
    # Next, we check if this name is in the galsim dictionary.
    elif type in galsim.__dict__:
        if issubclass(galsim.__dict__[type], galsim.GSObject):
            gsobject, safe = _BuildSimple(ck, key, base, ignore, gsparams, logger)
        else:
            TypeError("Input config type = %s is not a GSObject."%type)
    # Otherwise, it's not a valid type.
    else:
        raise NotImplementedError("Unrecognised config type = %s"%type)

    # If this is a psf, try to save the half_light_radius in case gal uses resolution.
    if key == 'psf':
        try : 
            ck['saved_re'] = gsobject.getHalfLightRadius()
        except :
            pass
    
    # Apply any dilation, ellip, shear, etc. modifications.
    gsobject, safe1 = _TransformObject(gsobject, ck, base, logger)
    safe = safe and safe1

    if 'no_save' not in base:
        ck['current_val'] = gsobject
        ck['current_safe'] = safe

    return gsobject, safe


def UpdateGSParams(gsparams, config, key, base):
    """@brief Add additional items to the `gsparams` dict based on config['gsparams'].
    """
    opt = galsim.GSObject._gsparams
    kwargs, safe = galsim.config.GetAllParams(config, key, base, opt=opt)
    # When we update gsparams, we don't want to corrupt the original, so we need to
    # make a copy first, then update with kwargs.
    ret = {}
    ret.update(gsparams)
    ret.update(kwargs)
    return ret


def _BuildNone(config, key, base, ignore, gsparams, logger):
    """@brief Special type=None returns None.
    """
    return None, True


def _BuildAdd(config, key, base, ignore, gsparams, logger):
    """@brief  Build a Sum object.
    """
    req = { 'items' : list }
    opt = { 'flux' : float }
    # Only Check, not Get.  We need to handle items a bit differently, since it's a list.
    galsim.config.CheckAllParams(config, key, req=req, opt=opt, ignore=ignore)

    gsobjects = []
    items = config['items']
    if not isinstance(items,list):
        raise AttributeError("items entry for config.%s entry is not a list."%type)
    safe = True

    for i in range(len(items)):
        gsobject, safe1 = BuildGSObject(items, i, base, gsparams, logger)
        # Skip items with flux=0
        if 'flux' in items[i] and galsim.config.value.GetCurrentValue(items[i],'flux') == 0.:
            if logger:
                logger.debug('obj %d: Not including component with flux == 0',base['obj_num'])
            continue
        safe = safe and safe1
        gsobjects.append(gsobject)

    if len(gsobjects) == 0:
        raise ValueError("No valid items for %s"%key)
    elif len(gsobjects) == 1:
        gsobject = gsobjects[0]
    else:
        # Special: if the last item in a Sum doesn't specify a flux, we scale it
        # to bring the total flux up to 1.
        if ('flux' not in items[-1]) and all('flux' in item for item in items[0:-1]):
            sum = 0
            for item in items[0:-1]:
                sum += galsim.config.value.GetCurrentValue(item,'flux')
            f = 1. - sum
            if (f < 0):
                import warnings
                warnings.warn(
                    "Automatically scaling the last item in Sum to make the total flux\n" +
                    "equal 1 requires the last item to have negative flux = %f"%f)
            gsobjects[-1] = gsobjects[-1].withFlux(f)
        if gsparams: gsparams = galsim.GSParams(**gsparams)
        else: gsparams = None
        gsobject = galsim.Add(gsobjects,gsparams=gsparams)

    if 'flux' in config:
        flux, safe1 = galsim.config.ParseValue(config, 'flux', base, float)
        if logger:
            logger.debug('obj %d: flux == %f',base['obj_num'],flux)
        gsobject = gsobject.withFlux(flux)
        safe = safe and safe1

    return gsobject, safe

def _BuildConvolve(config, key, base, ignore, gsparams, logger):
    """@brief  Build a Convolution object.
    """
    req = { 'items' : list }
    opt = { 'flux' : float }
    # Only Check, not Get.  We need to handle items a bit differently, since it's a list.
    galsim.config.CheckAllParams(config, key, req=req, opt=opt, ignore=ignore)

    gsobjects = []
    items = config['items']
    if not isinstance(items,list):
        raise AttributeError("items entry for config.%s entry is not a list."%type)
    safe = True
    for i in range(len(items)):
        gsobject, safe1 = BuildGSObject(items, i, base, gsparams, logger)
        safe = safe and safe1
        gsobjects.append(gsobject)

    if len(gsobjects) == 0:
        raise ValueError("No valid items for %s"%key)
    elif len(gsobjects) == 1:
        gsobject = gsobjects[0]
    else:
        if gsparams: gsparams = galsim.GSParams(**gsparams)
        else: gsparams = None
        gsobject = galsim.Convolve(gsobjects,gsparams=gsparams)
    
    if 'flux' in config:
        flux, safe1 = galsim.config.ParseValue(config, 'flux', base, float)
        if logger:
            logger.debug('obj %d: flux == %f',base['obj_num'],flux)
        gsobject = gsobject.withFlux(flux)
        safe = safe and safe1

    return gsobject, safe

def _BuildList(config, key, base, ignore, gsparams, logger):
    """@brief  Build a GSObject selected from a List.
    """
    req = { 'items' : list }
    opt = { 'index' : float , 'flux' : float }
    # Only Check, not Get.  We need to handle items a bit differently, since it's a list.
    galsim.config.CheckAllParams(config, key, req=req, opt=opt, ignore=ignore)

    items = config['items']
    if not isinstance(items,list):
        raise AttributeError("items entry for config.%s entry is not a list."%type)

    # Setup the indexing sequence if it hasn't been specified using the length of items.
    galsim.config.SetDefaultIndex(config, len(items))
    index, safe = galsim.config.ParseValue(config, 'index', base, int)
    if index < 0 or index >= len(items):
        raise AttributeError("index %d out of bounds for config.%s"%(index,type))

    gsobject, safe1 = BuildGSObject(items, index, base, gsparams, logger)
    safe = safe and safe1

    if 'flux' in config:
        flux, safe1 = galsim.config.ParseValue(config, 'flux', base, float)
        if logger:
            logger.debug('obj %d: flux == %f',base['obj_num'],flux)
        gsobject = gsobject.withFlux(flux)
        safe = safe and safe1

    return gsobject, safe

def _BuildRing(config, key, base, ignore, gsparams, logger):
    """@brief  Build a GSObject in a Ring.
    """
    req = { 'num' : int, 'first' : dict }
    opt = { 'full_rotation' : galsim.Angle , 'index' : int }
    # Only Check, not Get.  We need to handle first a bit differently, since it's a gsobject.
    galsim.config.CheckAllParams(config, key, req=req, opt=opt, ignore=ignore)

    num = galsim.config.ParseValue(config, 'num', base, int)[0]
    if num <= 0:
        raise ValueError("Attribute num for gal.type == Ring must be > 0")

    # Setup the indexing sequence if it hasn't been specified using the number of items.
    galsim.config.SetDefaultIndex(config, num)
    index, safe = galsim.config.ParseValue(config, 'index', base, int)
    if index < 0 or index >= num:
        raise AttributeError("index %d out of bounds for config.%s"%(index,type))

    if 'full_rotation' in config:
        full_rotation = galsim.config.ParseValue(config, 'full_rotation', base, galsim.Angle)[0]
    else:
        import math
        full_rotation = math.pi * galsim.radians

    dtheta = full_rotation / num
    if logger:
        logger.debug('obj %d: Ring dtheta = %f',base['obj_num'],dtheta.rad())

    if index % num == 0:
        # Then this is the first in the Ring.  
        gsobject = BuildGSObject(config, 'first', base, gsparams, logger)[0]
    else:
        if not isinstance(config['first'],dict) or 'current_val' not in config['first']:
            raise RuntimeError("Building Ring after the first item, but no current_val stored.")
        gsobject = config['first']['current_val'].rotate(index*dtheta)

    return gsobject, False


def _BuildRealGalaxy(config, key, base, ignore, gsparams, logger):
    """@brief Build a RealGalaxy from the real_catalog input item.
    """
    if 'real_catalog' not in base:
        raise ValueError("No real galaxy catalog available for building type = RealGalaxy")

    if 'num' in config:
        num, safe = ParseValue(config, 'num', base, int)
    else:
        num, safe = (0, True)
    ignore.append('num')

    if num < 0:
        raise ValueError("Invalid num < 0 supplied for RealGalaxy: num = %d"%num)
    if num >= len(base['real_catalog']):
        raise ValueError("Invalid num supplied for RealGalaxy (too large): num = %d"%num)

    real_cat = base['real_catalog'][num]

    # Special: if index is Sequence or Random, and max isn't set, set it to nobjects-1.
    # But not if they specify 'id' which overrides that.
    if 'id' not in config:
        galsim.config.SetDefaultIndex(config, real_cat.getNObjects())

    kwargs, safe1 = galsim.config.GetAllParams(config, key, base, 
        req = galsim.__dict__['RealGalaxy']._req_params,
        opt = galsim.__dict__['RealGalaxy']._opt_params,
        single = galsim.__dict__['RealGalaxy']._single_params,
        ignore = ignore)
    safe = safe and safe1
    if gsparams: kwargs['gsparams'] = galsim.GSParams(**gsparams)
    if logger and galsim.RealGalaxy._takes_logger: kwargs['logger'] = logger

    if 'rng' not in base:
        raise ValueError("No base['rng'] available for %s.type = RealGalaxy"%(key))
    kwargs['rng'] = base['rng']

    if 'index' in kwargs:
        index = kwargs['index']
        if index >= real_cat.getNObjects():
            raise IndexError(
                "%s index has gone past the number of entries in the catalog"%index)

    kwargs['real_galaxy_catalog'] = real_cat
    if logger:
        logger.debug('obj %d: RealGalaxy kwargs = %s',base['obj_num'],str(kwargs))

    gal = galsim.RealGalaxy(**kwargs)

    return gal, safe


def _BuildRealGalaxyOriginal(config, key, base, ignore, gsparams, logger):
    """@brief Return the original image from a RealGalaxy using the real_catalog input item.
    """
    image, safe = _BuildRealGalaxy(config, key, base, ignore, gsparams, logger)
    return image.original_image, safe    


def _BuildOpticalPSF(config, key, base, ignore, gsparams, logger):
    """@brief Build an OpticalPSF.
    """
    kwargs, safe = galsim.config.GetAllParams(config, key, base, 
        req = galsim.OpticalPSF._req_params,
        opt = galsim.OpticalPSF._opt_params,
        single = galsim.OpticalPSF._single_params,
        ignore = [ 'aberrations' ] + ignore)
    if gsparams: kwargs['gsparams'] = galsim.GSParams(**gsparams)

    if 'aberrations' in config:
        aber_list = [0.0] * 4  # Initial 4 values are ignored.
        aberrations = config['aberrations']
        if not isinstance(aberrations,list):
            raise AttributeError("aberrations entry for config.OpticalPSF entry is not a list.")
        for i in range(len(aberrations)):
            value, safe1 = galsim.config.ParseValue(aberrations, i, base, float)
            aber_list.append(value)
            safe = safe and safe1
        kwargs['aberrations'] = aber_list
            
    return galsim.OpticalPSF(**kwargs), safe


def _BuildCOSMOSGalaxy(config, key, base, ignore, gsparams, logger):
    """@brief Build a COSMOS galaxy using the cosmos_catalog input item.
    """
    if 'cosmos_catalog' not in base:
        raise ValueError("No COSMOS galaxy catalog available for building type = COSMOSGalaxy")

    if 'num' in config:
        num, safe = ParseValue(config, 'num', base, int)
    else:
        num, safe = (0, True)
    ignore.append('num')

    if num < 0:
        raise ValueError("Invalid num < 0 supplied for COSMOSGalaxy: num = %d"%num)
    if num >= len(base['cosmos_catalog']):
        raise ValueError("Invalid num supplied for COSMOSGalaxy (too large): num = %d"%num)

    cosmos_cat = base['cosmos_catalog'][num]

    # Special: if index is Sequence or Random, and max isn't set, set it to nobjects-1.
    galsim.config.SetDefaultIndex(config, cosmos_cat.getNObjects())

    kwargs, safe1 = galsim.config.GetAllParams(config, key, base,
        req = galsim.COSMOSCatalog.makeGalaxy._req_params,
        opt = galsim.COSMOSCatalog.makeGalaxy._opt_params,
        single = galsim.COSMOSCatalog.makeGalaxy._single_params,
        ignore = ignore)
    safe = safe and safe1
    if gsparams: kwargs['gsparams'] = galsim.GSParams(**gsparams)
    if logger and galsim.COSMOSCatalog.makeGalaxy._takes_logger: kwargs['logger'] = logger

    if 'gal_type' in kwargs and kwargs['gal_type'] == 'real':
        if 'rng' not in base:
            raise ValueError("No base['rng'] available for %s.type = COSMOSGalaxy"%(key))
        kwargs['rng'] = base['rng']

    if 'index' in kwargs:
        index = kwargs['index']
        if index >= cosmos_cat.getNObjects():
            raise IndexError(
                "%s index has gone past the number of entries in the catalog"%index)

    if logger:
        logger.debug('obj %d: COSMOSGalaxy kwargs = %s',base['obj_num'],str(kwargs))

    kwargs['cosmos_catalog'] = cosmos_cat

    # Use a staticmethod of COSMOSCatalog to avoid pickling the result of makeGalaxy()
    # The RealGalaxy in particular has a large serialization, so it is more efficient to
    # make it in this process, which is what happens here.
    gal = galsim.COSMOSCatalog._makeSingleGalaxy(**kwargs)

    return gal, safe


def _BuildSimple(config, key, base, ignore, gsparams, logger):
    """@brief Build a simple GSObject (i.e. one without a specialized _Build function) or
    any other GalSim object that defines _req_params, _opt_params and _single_params.
    """
    # Build the kwargs according to the various params objects in the class definition.
    type = config['type']
    if type in galsim.__dict__:
        init_func = eval("galsim."+type)
    else:
        init_func = eval(type)
    if logger:
        logger.debug('obj %d: BuildSimple for type = %s',base['obj_num'],type)
        logger.debug('obj %d: init_func = %s',base['obj_num'],str(init_func))

    kwargs, safe = galsim.config.GetAllParams(config, key, base, 
                                              req = init_func._req_params,
                                              opt = init_func._opt_params,
                                              single = init_func._single_params,
                                              ignore = ignore)
    if gsparams: kwargs['gsparams'] = galsim.GSParams(**gsparams)
    if logger and init_func._takes_logger: kwargs['logger'] = logger

    if init_func._takes_rng:
        if 'rng' not in base:
            raise ValueError("No base['rng'] available for %s.type = %s"%(key,type))
        kwargs['rng'] = base['rng']
        safe = False

    if logger:
        logger.debug('obj %d: kwargs = %s',base['obj_num'],str(kwargs))

    # Finally, after pulling together all the params, try making the GSObject.
    return init_func(**kwargs), safe


def _TransformObject(gsobject, config, base, logger):
    """@brief Applies ellipticity, rotation, gravitational shearing and centroid shifting to a
    supplied GSObject, in that order.

    @returns transformed GSObject.
    """
    safe = True
    if 'dilate' in config:
        gsobject, safe1 = _DilateObject(gsobject, config, 'dilate', base, logger)
        safe = safe and safe1
    if 'dilation' in config:
        gsobject, safe1 = _DilateObject(gsobject, config, 'dilation', base, logger)
        safe = safe and safe1
    if 'ellip' in config:
        gsobject, safe1 = _EllipObject(gsobject, config, 'ellip', base, logger)
        safe = safe and safe1
    if 'rotate' in config:
        gsobject, safe1 = _RotateObject(gsobject, config, 'rotate', base, logger)
        safe = safe and safe1
    if 'rotation' in config:
        gsobject, safe1 = _RotateObject(gsobject, config, 'rotation', base, logger)
        safe = safe and safe1
    if 'scale_flux' in config:
        gsobject, safe1 = _ScaleFluxObject(gsobject, config, 'scale_flux', base, logger)
        safe = safe and safe1
    if 'shear' in config:
        gsobject, safe1 = _EllipObject(gsobject, config, 'shear', base, logger)
        safe = safe and safe1
    if 'magnify' in config:
        gsobject, safe1 = _MagnifyObject(gsobject, config, 'magnify', base, logger)
        safe = safe and safe1
    if 'magnification' in config:
        gsobject, safe1 = _MagnifyObject(gsobject, config, 'magnification', base, logger)
        safe = safe and safe1
    if 'shift' in config:
        gsobject, safe1 = _ShiftObject(gsobject, config, 'shift', base, logger)
        safe = safe and safe1
    return gsobject, safe

def _EllipObject(gsobject, config, key, base, logger):
    """@brief Applies ellipticity to a supplied GSObject, also used for gravitational shearing.

    @returns transformed GSObject.
    """
    shear, safe = galsim.config.ParseValue(config, key, base, galsim.Shear)
    if logger:
        logger.debug('obj %d: shear = %f,%f',base['obj_num'],shear.g1,shear.g2)
    gsobject = gsobject.shear(shear)
    return gsobject, safe

def _RotateObject(gsobject, config, key, base, logger):
    """@brief Applies rotation to a supplied GSObject.

    @returns transformed GSObject.
    """
    theta, safe = galsim.config.ParseValue(config, key, base, galsim.Angle)
    if logger:
        logger.debug('obj %d: theta = %f rad',base['obj_num'],theta.rad())
    gsobject = gsobject.rotate(theta)
    return gsobject, safe

def _ScaleFluxObject(gsobject, config, key, base, logger):
    """@brief Scales the flux of a supplied GSObject.

    @returns transformed GSObject.
    """
    flux_ratio, safe = galsim.config.ParseValue(config, key, base, float)
    if logger:
        logger.debug('obj %d: flux_ratio  = %f',base['obj_num'],flux_ratio)
    gsobject = gsobject * flux_ratio
    return gsobject, safe

def _DilateObject(gsobject, config, key, base, logger):
    """@brief Applies dilation to a supplied GSObject.

    @returns transformed GSObject.
    """
    scale, safe = galsim.config.ParseValue(config, key, base, float)
    if logger:
        logger.debug('obj %d: scale  = %f',base['obj_num'],scale)
    gsobject = gsobject.dilate(scale)
    return gsobject, safe

def _MagnifyObject(gsobject, config, key, base, logger):
    """@brief Applies magnification to a supplied GSObject.

    @returns transformed GSObject.
    """
    mu, safe = galsim.config.ParseValue(config, key, base, float)
    if logger:
        logger.debug('obj %d: mu  = %f',base['obj_num'],mu)
    gsobject = gsobject.magnify(mu)
    return gsobject, safe

def _ShiftObject(gsobject, config, key, base, logger):
    """@brief Applies centroid shift to a supplied GSObject.

    @returns transformed GSObject.
    """
    shift, safe = galsim.config.ParseValue(config, key, base, galsim.PositionD)
    if logger:
        logger.debug('obj %d: shift  = %f,%f',base['obj_num'],shift.x,shift.y)
    gsobject = gsobject.shift(shift.x,shift.y)
    return gsobject, safe


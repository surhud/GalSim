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
""""@file table.py
A few adjustments to galsim.LookupTable at the Python layer, including the 
addition of the docstring and few extra features.
"""
from . import _galsim

class LookupTable(object):
    """
    LookupTable represents a lookup table to store function values that may be slow to calculate,
    for which interpolating from a lookup table is sufficiently accurate.

    A LookupTable may be constructed from two arrays (lists, tuples, or NumPy arrays of 
    floats/doubles).

        >>> args = [...]
        >>> vals = []
        >>> for arg in args:
        ...     val = calculateVal(arg)
        ...     vals.append(val)
        >>> table = galsim.LookupTable(x=args,f=vals)

    Then you can use this table as a replacement for the slow calculation:

        >>> other_args = [...]
        >>> for arg in other_args:
        ...     val = table(arg)
        ...     [... use val ...]


    The default interpolation method is cubic spline interpolation.  This is usually the 
    best choice, but we also provide three other options, which can be specified by
    the `interpolant` kwarg.  The choices are 'floor', 'ceil', 'linear' and 'spline':

    - 'floor' takes the value from the previous argument in the table.
    - 'ceil' takes the value from the next argument in the table.
    - 'linear' does linear interpolation between these two values.
    - 'spline' uses a cubic spline interpolation, so the interpolated values are smooth at 
      each argument in the table.

    Another option is to read in the values from an ascii file.  The file should have two 
    columns of numbers, which are taken to be the `x` and `f` values.

    The user can also opt to interpolate in log(x) and/or log(f), though this is not the default.
    It may be a wise choice depending on the particular function, e.g., for a nearly power-law
    f(x) (or at least one that is locally power-law-ish for much of the x range) then it might 
    be a good idea to interpolate in log(x) and log(f) rather than x and f.

    @param x             The list, tuple, or NumPy array of `x` values (floats, doubles, or ints,
                         which get silently converted to floats for the purpose of interpolation).
                         [Either `x` and `f` or `file` is required.]
    @param f             The list, tuple, or NumPy array of `f(x)` values (floats, doubles, or ints,
                         which get silently converted to floats for the purpose of interpolation).
                         [Either `x` and `f` or `file` is required.]
    @param file          A file from which to read the `(x,f)` pairs. [Either `x` and `f`, or `file`
                         is required]
    @param interpolant   The interpolant to use, with the options being 'floor', 'ceil', 
                         'linear' and 'spline'. [default: 'spline']
    @param x_log         Set to True if you wish to interpolate using log(x) rather than x.  Note
                         that all inputs / outputs will still be x, it's just a question of how the
                         interpolation is done. [default: False]
    @param f_log         Set to True if you wish to interpolate using log(f) rather than f.  Note
                         that all inputs / outputs will still be f, it's just a question of how the
                         interpolation is done. [default: False]
    """
    def __init__(self, x=None, f=None, file=None, interpolant=None, x_log=False, f_log=False):
        import numpy as np
        self.x_log = x_log
        self.f_log = f_log
        self.file = file

        # read in from file if a filename was specified
        if file:
            if x is not None or f is not None:
                raise ValueError("Cannot provide both file _and_ x,f for LookupTable")
            data = np.loadtxt(file).transpose()
            if data.shape[0] != 2:
                raise ValueError("File %s provided for LookupTable does not have 2 columns"%file)
            x=data[0]
            f=data[1]
        else:
            if x is None or f is None:
                raise ValueError("Must specify either file or x,f for LookupTable")

        # turn x and f into numpy arrays so that all subsequent math is possible (unlike for
        # lists, tuples).  Also make sure the dtype is float
        x = np.asarray(x).astype(float)
        f = np.asarray(f).astype(float)
        self.x = x
        self.f = f

        # check for proper interpolant
        if interpolant is None:
            interpolant = 'spline'
        else:
            if interpolant not in ['spline', 'linear', 'ceil', 'floor']:
                raise ValueError("Unknown interpolant: %s" % interpolant)
        self.interpolant = interpolant

        # make and store table
        if x_log:
            if np.any(np.array(x) <= 0.):
                raise ValueError("Cannot interpolate in log(x) when table contains x<=0!")
            x = np.log(x)
        if f_log:
            if np.any(np.array(f) <= 0.):
                raise ValueError("Cannot interpolate in log(f) when table contains f<=0!")
            f = np.log(f)

        # table is the thing the does the actual work.  It is a C++ Table object, wrapped
        # as _LookupTable.
        self.table = _galsim._LookupTable(x, f, interpolant)

    @property
    def x_min(self): return min(self.x)
    @property
    def x_max(self): return max(self.x)
    @property
    def n_x(self): return len(self.x)

    def __call__(self, x):
        """Interpolate the LookupTable to get `f(x)` at some `x` value(s).

        When the LookupTable object is called with a single argument, it returns the value at that
        argument.  An exception will be thrown automatically by the _LookupTable class if the `x`
        value is outside the range of the original tabulated values.  The value that is returned is
        the same type as that provided as an argument, e.g., if a single value `x` is provided then
        a single value of `f` is returned; if a tuple of `x` values is provided then a tuple of `f`
        values is returned; and so on.  Even if interpolation was done using the `x_log` option,
        the user should still provide `x` rather than `log(x)`.

        @param x        The `x` value(s) for which `f(x)` should be calculated via interpolation on
                        the original `(x,f)` lookup table.  `x` can be a single float/double, or a
                        tuple, list, or arbitrarily shaped 1- or 2-dimensional NumPy array.

        @returns the interpolated `f(x)` value(s).
        """
        import numpy as np
        # first, keep track of whether interpolation was done in x or log(x)
        if self.x_log:
            if np.any(np.array(x) <= 0.):
                raise ValueError("Cannot interpolate x<=0 when using log(x) interpolation.")
            x = np.log(x)

        # figure out what we received, and return the same thing
        # option 1: a NumPy array
        if isinstance(x, np.ndarray):
            dimen = len(x.shape)
            if dimen > 2:
                raise ValueError("Arrays with dimension larger than 2 not allowed!")
            elif dimen == 2:
                f = np.zeros_like(x)
                for i in xrange(x.shape[0]):
                    f[i,:] = np.fromiter((self.table(float(q)) for q in x[i,:]), dtype='float')
            else:
                f = np.fromiter((self.table(float(q)) for q in x), dtype='float')
        # option 2: a tuple
        elif isinstance(x, tuple):
            f = [ self.table(q) for q in x ]
            f = tuple(f)
        # option 3: a list
        elif isinstance(x, list):
            f = [ self.table(q) for q in x ]
        # option 4: a single value
        else:
            f = self.table(x)

        if self.f_log:
            f = np.exp(f)
        return f

    def getArgs(self):
        args = self.table.getArgs()
        if self.x_log:
            import numpy as np
            return np.exp(args)
        else:
            return args

    def getVals(self):
        vals = self.table.getVals()
        if self.f_log:
            import numpy as np
            return np.exp(vals)
        else:
            return vals

    def getInterp(self):
        return self.table.getInterp()

    def isLogX(self):
        return self.x_log

    def isLogF(self):
        return self.f_log

    def __eq__(self, other):
        import numpy as np
        return (isinstance(other, LookupTable) and
                np.array_equal(self.x,other.x) and
                np.array_equal(self.f,other.f) and
                self.x_log == other.x_log and
                self.f_log == other.f_log and
                self.interpolant == other.interpolant)
    def __ne__(self, other): return not self.__eq__(other)

    def __repr__(self):
        return 'galsim.LookupTable(x=array(%r), f=array(%r), x_log=%r, f_log=%r, interpolant=%r)'%(
            self.x.tolist(), self.f.tolist(), self.x_log, self.f_log, self.interpolant)

    def __str__(self):
        if self.file is not None:
            return 'galsim.LookupTable(file=%r, interpolant=%r)'%(
                self.file, self.interpolant)
        else:
            return 'galsim.LookupTable(x=[%s,..,%s], f=[%s,...,%s], interpolant=%r)'%(
                self.x[0], self.x[-1], self.f[0], self.f[-1], self.interpolant)

    def __hash__(self): return hash(repr(self))


# A function to enable pickling of tables
_galsim._LookupTable.__getinitargs__ = lambda self: \
        (self.getArgs(), self.getVals(), self.getInterp())
_galsim._LookupTable.__repr__ = lambda self: \
        'galsim._galsim._LookupTable(array(%r), array(%r), %r)'%(
            self.getArgs(), self.getVals(), self.getInterp())
_galsim._LookupTable.__eq__ = lambda self, other: repr(self) == repr(other)
_galsim._LookupTable.__ne__ = lambda self, other: not self.__eq__(other)
_galsim._LookupTable.__hash__ = lambda self: hash(repr(other))

# -*- coding: utf-8 -*-
"""
Created on Fri Dec 18 16:48:34 2020

@author: marquart
"""
import logging
from numpy import ndarray
import numpy as np

def input_check( years=None, tokens=None):
    """
    Check provided inputs and throw errors if needed.

    Parameters
    ----------
    years : TYPE, optional
        Year or time variable used in int or dict format. The default is None.
    tokens : TYPE, optional
        appropriate list or array. The default is None.

    Returns
    -------
    None.

    """
    if years is not None:
        if (not isinstance(years, ndarray)) and (not isinstance(years, list)) and (not isinstance(years, dict)) and (not isinstance(years, int)) and (not isinstance(years,np.integer)):
            logging.error("Parameter years must be int, list, array or interval dict ('start':int,'end':int). Supplied: {}".format(type(years)))
        assert isinstance(years, ndarray) or isinstance(years, list) or isinstance(years, dict) or isinstance(years, int) or isinstance(years,np.integer), "Parameter years must be int, list, array or interval dict ('start':int,'end':int). Supplied: {}".format(type(years))
    if tokens is not None:
        if (not isinstance(tokens, ndarray)) and (not isinstance(tokens, list)) and (not isinstance(tokens, int)) and (not isinstance(tokens, str)) and (not isinstance(years,np.integer)):
            logging.error("Token parameter should be string, int or list. Supplied: {}".format(type(tokens)))
        assert isinstance(tokens, ndarray) or isinstance(tokens, list) or isinstance(tokens, int) or isinstance(tokens, str)  or isinstance(years,np.integer), "Token parameter should be string, int or list. Supplied: {}".format(type(tokens))
        
   

from sklearn.cluster import SpectralClustering
import torch
from NLP.src.datasets.dataloaderX import DataLoaderX
import numpy as np
import tables
import networkx as nx
import os
from tqdm import tqdm
from sklearn.preprocessing import normalize
import matplotlib.pyplot as plt
from numpy import inf
from sklearn.cluster import KMeans
import hdbscan
import itertools
from NLP.utils.delwords import create_stopword_list
from torch.utils.data import BatchSampler, SequentialSampler
import time
from sklearn.cluster import MeanShift, estimate_bandwidth
from NLP.src.datasets.tensor_dataset import tensor_dataset, tensor_dataset_collate_batchsample

def calculate_cutoffs(x, method="mean"):
    """
    Different methods to calculate cutoff probability and number.

    :param x: Contextual vector
    :param method: To implement. Currently: mean
    :return: cutoff_number and probability
    """
    if method == "mean":
        cutoff_probability = max(np.mean(x), 0.01)
        cutoff_number = max(np.int(len(x) / 100), 100)
    elif method == "80":
        sortx = np.sort(x)[::-1]
        cum_sum = np.cumsum(sortx)
        cutoff = cum_sum[-1] * 0.8
        cutoff_number = np.where(cum_sum >= cutoff)[0][0]
        cutoff_probability = 0.01
    else:
        cutoff_probability = 0
        cutoff_number = 0

    return cutoff_number, cutoff_probability


def get_weighted_edgelist(token, x, cutoff_number=100, cutoff_probability=0):
    """
    Sort probability distribution to get the most likely neighbor nodes.
    Return a networksx weighted edge list for a given focal token as node.

    :param token: Numerical, token which to add
    :param x: Probability distribution
    :param cutoff_number: Number of neighbor token to consider. Not used if 0.
    :param cutoff_probability: Lowest probability to consider. Not used if 0.
    :return: List of tuples compatible with networkx
    """
    # Get the most pertinent words
    if cutoff_number > 0:
        neighbors = np.argsort(-x)[:cutoff_number]
    else:
        neighbors = np.argsort(-x)[:]

    # Cutoff probability (zeros)
    if len(neighbors > 0):
        neighbors = neighbors[x[neighbors] > cutoff_probability]
        weights = x[neighbors]
        # edgelist = [(token, x) for x in neighbors]
    return [(token, x[0], x[1]) for x in list(zip(neighbors, weights))]


def softmax(x):
    """Compute softmax values for each sets of scores in x."""
    x = np.exp(x - np.max(x))
    return np.exp(x) / np.sum(np.exp(x), axis=-1, keepdims=True)


def simple_norm(x):
    """Just want to start at zero and sum to 1, without norming anything else"""
    x = x - np.min(x, axis=-1)
    if np.sum(x, axis=-1) > 0:
        return x / np.sum(x, axis=-1)
    else:
        return x

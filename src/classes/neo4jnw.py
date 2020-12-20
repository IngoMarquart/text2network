import copy
import logging
from collections.abc import MutableSequence
from src.utils.twowaydict import TwoWayDict
import numpy as np
from src.functions.backout_measure import backout_measure
from src.functions.node_measures import proximity, centrality
from src.utils.input_check import input_check
# import neo4j utilities and classes
from src.classes.neo4db import neo4j_database
# Clustering
from src.functions.graph_clustering import *

# Type definition
try: # Python 3.8+
    from typing import TypedDict
    class GraphDict(TypedDict):
        graph: nx.DiGraph
        name: str
        parent: int
        level: int
        measures: List
        metadata: [Union[Dict,defaultdict]]
except:
    GraphDict = Dict[str, Union[str,int,Dict,List,defaultdict]]

try:
    import networkx as nx
except:
    nx = None

try:
    import igraph as ig
except:
    ig = None


class neo4j_network(MutableSequence):

    # %% Initialization functions
    def __init__(self, neo4j_creds, graph_type="networkx", agg_operator="SUM",
                 write_before_query=True,
                 neo_batch_size=10000, queue_size=100000, tie_query_limit=100000, tie_creation="UNSAFE",
                 logging_level=logging.NOTSET):
        # Set logging level
        logging.disable(logging_level)

        self.db = neo4j_database(neo4j_creds, agg_operator, write_before_query, neo_batch_size, queue_size,
                                 tie_query_limit, tie_creation, logging_level)

        # Conditioned graph information
        self.graph_type = graph_type
        self.graph = None
        self.conditioned = False
        self.years = []

        # Dictionaries and token/id saved in memory
        self.token_id_dict = TwoWayDict()
        # Since both are numerical, we need to use a single way dict here
        self.id_index_dict = dict()
        self.tokens = []
        self.ids = []
        # Copies to be used during conditioning
        self.neo_token_id_dict = TwoWayDict()
        self.neo_ids = []
        self.neo_tokens = []
        # Init tokens
        self.init_tokens()
        # Init parent class
        super().__init__()

    # %% Python Interface implementations
    def __delitem__(self, key):
        """
        Deletes a node and all its ties
        :param key: Token or Token id
        :return:
        """
        self.remove(key)

    def remove(self, key):
        """
        Deletes a node and all its ties
        :param key: Token or Token id
        :return:
        """
        key = self.ensure_ids(key)
        assert key in self.ids, "ID of ego token to connect not found. Not in network?"
        self.remove_token(key)

    def __setitem__(self, key, value):
        """
        Set links of node
        :param key: id or token of node.
        :param value: To add links to node: list of tuples [(neighbor,time, weight))] or [(neighbor,time, {'weight':weight,'p1':p1,'p2':p2}))]. To add node itself, token_id (int)
        :return:
        """
        if isinstance(key, str) and isinstance(value, int):  # Wants to add a node
            self.add_token(value, key)
        else:
            key = self.ensure_ids(key)
            assert key in self.ids, "ID of ego token to connect not found. Not in network?"
            try:

                neighbors = [x[0] for x in value]
                neighbors = self.ensure_ids(neighbors)
                weights = [{'weight': x[2]} if isinstance(
                    x[2], (int, float)) else x[2] for x in value]
                years = [x[1] for x in value]
                token = map(int, np.repeat(key, len(neighbors)))
            except:
                raise ValueError(
                    "Adding requires an iterable over tuples e.g. [(neighbor,time, weight))]")

            # Check if all neighbor tokens present
            assert set(neighbors) < set(
                self.ids), "ID of node to connect not found. Not in network?"
            ties = list(zip(token, neighbors, years, weights))

            # TODO Dispatch if graph conditioned

            # Add ties to query
            self.insert_edges_multiple(ties)

    def __getitem__(self, i):
        """
        Retrieve node information with input checking
        :param i: int or list of nodes, or tuple of nodes with timestamp. Format as int YYYYMMDD, or dict with {'start:'<YYYYMMDD>, 'end':<YYYYMMDD>.
        :return: NetworkX compatible node format
        """
        # If so desired, induce a queue write before any query
        if self.db.write_before_query == True:
            self.db.write_queue()
        # Are time formats submitted? Handle those and check inputs
        if isinstance(i, tuple):
            assert len(
                i) == 2, "Please format a call as <token>,<YYYYMMDD> or <token>,{'start:'<YYYYMMDD>, 'end':<YYYYMMDD>"
            if not isinstance(i[1], dict):
                assert isinstance(
                    i[1], int), "Please timestamp as <YYYYMMDD>, or{'start:'<YYYYMMDD>, 'end':<YYYYMMDD>"
            year = i[1]
            i = i[0]
        else:
            year = None
        if isinstance(i, (list, tuple, range, str, int)):
            i = self.ensure_ids(i)
        else:
            raise AssertionError(
                "Please format a call as <token> or <token_id>")

        # TODO Dispatch in case of graph
        if self.conditioned == False:
            return self.query_nodes(i, year)
        else:
            if isinstance(i, (list, tuple, np.ndarray)):
                returndict = []
                for token in i:
                    neighbors = dict(self.graph[token])
                    returndict.extend({token: neighbors})
            else:
                neighbors = dict(self.graph[i])
                returndict = {i: neighbors}
            return returndict

    def __len__(self):
        return len(self.tokens)

    def insert(self, token, token_id):
        """
        Insert a new token
        :param token: Token string
        :param token_id: Token ID
        :return: None
        """
        assert isinstance(token, str) and isinstance(
            token_id, int), "Please add <token>,<token_id> as str,int"
        self.add_token(token_id, token)

    def add_token(self, id, token):
        # Update class
        self.tokens.append(token)
        self.ids.append(id)
        self.update_dicts()

        # Update database
        queries = [
            ''.join(["MERGE (n:word {token_id: ", str(id), ", token: '", token, "'})"])]
        self.db.add_queries(queries)

    def remove_token(self, key):
        self.tokens.remove(self.get_token_from_id(key))
        self.ids.remove(key)
        self.update_dicts()

        # Update database
        queries = [
            ''.join(["MATCH (n:word {token_id: ", str(key), "}) DETACH DELETE n"])]
        self.db.add_queries(queries)

    def get_times_list(self):
        query = "MATCH (n) WHERE EXISTS(n.time) RETURN DISTINCT  n.time AS time"
        res = self.db.connector.run(query)
        times = [x['time'] for x in res]
        return times

    # %% Conditoning functions
    def condition(self, years=None, tokens=None, weight_cutoff=None, depth=None, context=None, norm=True,
                  batchsize=10000):
        """
        :param years: None, integer YYYY, or interval dict of the form {"start":YYYY,"end":YYYY}
        :param tokens: None or list of strings or integers (ids)
        :param weight_cutoff: Ties with weight smaller will be ignored
        :param depth: If ego network is requested, maximal path length from ego
        :param context: list of tokens or token ids that are in the context of replacement
        :param norm: True/False - Generate normed replacement or aggregate replacement
        :return:
        """
        # Without times, we query all
        if years == None:
            years = self.get_times_list()

        if tokens == None:
            logging.debug("Conditioning dispatch: Yearly")
            self.year_condition(years, weight_cutoff, context, norm, batchsize)
        else:
            logging.debug("Conditioning dispatch: Ego")
            self.ego_condition(years, tokens, weight_cutoff,
                               depth, context, norm)

        self.conditioned = True

    def year_condition(self, years, weight_cutoff=None, context=None, norm=True, batchsize=10000):
        """ Condition the entire network over all years """
        if self.conditioned == False:  # This is the first conditioning
            # Preserve node and token lists
            self.neo_ids = copy.deepcopy(self.ids)
            self.neo_tokens = copy.deepcopy(self.tokens)
            self.neo_token_id_dict = copy.deepcopy(self.token_id_dict)
            # Build graph
            self.graph = self.create_empty_graph()
            # Clear graph dicts
            self.tokens = []
            self.ids = []
            self.update_dicts()

            # All tokens
            worklist = self.neo_ids
            # Add all tokens to graph
            self.graph.add_nodes_from(worklist)

            # Loop batched over all tokens to condition
            for i in range(0, len(worklist), batchsize):

                token_ids = worklist[i:i + batchsize]
                logging.debug(
                    "Conditioning by query batch {} of {} tokens.".format(i, len(token_ids)))
                # Query Neo4j
                try:
                    self.graph.add_edges_from(
                        self.query_nodes(token_ids, context=context, times=years, weight_cutoff=weight_cutoff,
                                         norm_ties=norm))
                except:
                    logging.error("Could not condition graph by query method.")

            # Update IDs and Tokens to reflect conditioning
            all_ids = list(self.graph.nodes)
            self.tokens = [self.get_token_from_id(x) for x in all_ids]
            self.ids = all_ids
            self.update_dicts()
            # Add final properties
            att_list = [{"token": x} for x in self.tokens]
            att_dict = dict(list(zip(self.ids, att_list)))
            nx.set_node_attributes(self.graph, att_dict)
        else:  # Remove conditioning and recondition
            self.decondition()
            self.year_condition(years, weight_cutoff, context, norm)

    def ego_condition(self, years, token_ids, weight_cutoff=None, depth=None, context=None, norm=True):
        if self.conditioned == False:  # This is the first conditioning
            # Preserve node and token lists
            self.neo_ids = copy.deepcopy(self.ids)
            self.neo_tokens = copy.deepcopy(self.tokens)
            self.neo_token_id_dict = copy.deepcopy(self.token_id_dict)
            # Build graph
            self.graph = self.create_empty_graph()
            # Clear graph dicts
            self.tokens = []
            self.ids = []
            self.update_dicts()

            # Depth 0 and Depth 1 really mean the same thing here
            if depth == 0 or depth == None:
                depth = 1
            # Create a dict to hold previously queried ids
            prev_queried_ids = list()
            while depth > 0:
                if not isinstance(token_ids, (list, np.ndarray)):
                    token_ids = [token_ids]
                # Work from ID list, give error if tokens are not in database
                token_ids = self.ensure_ids(token_ids)
                # Do not consider already added tokens
                token_ids = np.setdiff1d(token_ids, prev_queried_ids)
                logging.debug(
                    "Depth {} conditioning: {} new found tokens, where {} already added.".format(depth, len(token_ids),
                                                                                                 len(prev_queried_ids)))
                # Add token_ids to list since they will be queried this iteration
                prev_queried_ids.extend(token_ids)
                # Add starting nodes
                self.graph.add_nodes_from(token_ids)
                # Query Neo4j
                try:
                    self.graph.add_edges_from(
                        self.query_nodes(token_ids, context=context, times=years, weight_cutoff=weight_cutoff,
                                         norm_ties=norm))
                except:
                    logging.error("Could not condition graph by query method.")
                    raise Exception(
                        "Could not condition graph by query method.")

                # Update IDs and Tokens to reflect conditioning
                all_ids = list(self.graph.nodes)
                # ("{} All ids: {}".format(len(all_ids),all_ids))
                self.tokens = [self.get_token_from_id(x) for x in all_ids]
                self.ids = all_ids
                self.update_dicts()

                # Set the next set of tokens as those that have not been previously queried
                token_ids = np.setdiff1d(all_ids, prev_queried_ids)
                # print("{} tokens post setdiff: {}".format(len(token_ids),token_ids))
                # Set additional attributes
                att_list = [{"token": x} for x in self.tokens]
                att_dict = dict(list(zip(self.ids, att_list)))
                nx.set_node_attributes(self.graph, att_dict)

                # decrease depth
                depth = depth - 1
                if token_ids == []:
                    depth = 0

            # Set conditioning true
            self.conditioned = True

        else:  # Remove conditioning and recondition
            # TODO: "Allow for conditioning on conditioning"
            self.decondition()
            self.condition(years, token_ids, weight_cutoff,
                           depth, context, norm)

        # Continue conditioning

    def decondition(self, write=False):
        # Reset token lists to original state.
        self.ids = self.neo_ids
        self.tokens = self.neo_tokens
        self.token_id_dict = self.neo_token_id_dict

        # Decondition
        logging.debug("Deconditioning graph.")
        self.delete_graph()
        self.conditioned = False

        if write == True:
            self.db.write_queue()
        else:
            self.db.neo_queue = []

    # %% Clustering
    def cluster(self, levels:int = 1, name:Optional[str]="base", metadata: Optional[Union[dict,defaultdict]] = None, algorithm: Optional[Callable[[nx.DiGraph], List]] = None,to_measure: Optional[List[Callable[[nx.DiGraph], Dict]]] = None, ego_nw_tokens:Optional[List]=None, depth:Optional[int]=1,years:Optional[Union[int,Dict,List]]=None, context:Optional[List]=None, weight_cutoff:float=None, norm_ties:bool=True):
        """
        Cluster the network, run measures on the clusters and return them as networkx subgraph in packaged dicts with metadata.
        Use the levels variable to determine how often to cluster hierarchically.

        Function takes the usual conditioning argument when the network is not yet conditioned.
        If it is conditioned, then the current graph will be used to cluster

        Parameters
        ----------
        levels: int
            Number of hierarchy levels to cluster
        name: str. Optional.
            Base name of the cluster. Further levels will add -i. Default is "base".
        metadata: dict. Optional.
            A dict of metadata that is kept for all clusters.
        algorithm: callable.  Optional.
            Any algorithm taking a networkx graph and return a list of lists of tokens.
        to_measure: list of callables. Optional.
            Functions that take a networkx graph as argument and return a formatted dict with measures.
        ego_nw_tokens: list. Optional.
            Ego network tokens. Used only when conditioning.
        depth: int. Optional.
            Depth of ego network. Used only when conditioning.
        years: int, list, str. Optional
            Given year, list of year, or an interval dict {"start":int,"end":int}. The default is None.
        context : list, optional - used when conditioning
            List of tokens that need to appear in the context distribution of a tie. The default is None.
        weight_cutoff : float, optional - used when conditioning
            Only ties of higher weight are considered. The default is None.
        norm_ties : bool, optional - used when conditioning
            Norm ties to get correct probabilities. The default is True.

        Returns
        -------
        list of cluster-dictionaries.
        """

        input_check(tokens=ego_nw_tokens)
        input_check(tokens=context)
        input_check(years=years)

        # Check and fix up token lists
        if ego_nw_tokens is not None:
            ego_nw_tokens = self.ensure_ids(ego_nw_tokens)
        if context is not None:
            context = self.ensure_ids(context)



        # Prepare metadata with standard additions
        # TODO Add standard metadata for conditioning
        metadata_new=defaultdict(list)
        if metadata is not None:
            for (k, v) in metadata.items():
                metadata_new[k].append(v)


        if self.conditioned == False:
            was_conditioned = False
            if ego_nw_tokens == None:
                logging.debug("Conditioning year(s) {} with all tokens".format(
                    years))
                self.condition(years=years, tokens=None, weight_cutoff=weight_cutoff,
                               depth=depth, context=context, norm=norm_ties)
                logging.debug("Finished conditioning, {} nodes and {} edges in graph".format(
                    len(self.graph.nodes), len(self.graph.edges)))
            else:
                logging.debug("Conditioning ego-network for {} tokens with depth {}, for year(s) {} with focus on tokens {}".format(
                    len(ego_nw_tokens), depth, years, ego_nw_tokens))
                self.condition(years=years, tokens=ego_nw_tokens, weight_cutoff=weight_cutoff,
                               depth=depth, context=context, norm=norm_ties)
                logging.debug("Finished ego conditioning, {} nodes and {} edges in graph".format(
                    len(self.graph.nodes), len(self.graph.edges)))
        else:
            logging.debug(
                "Network already conditioned! No reconditioning attempted, parameters unused.")
            was_conditioned = True

        # Prepare base cluster
        base_cluster=return_cluster(self.graph, name, "", 0, to_measure, metadata_new)
        cluster_list=[]
        step_list = []
        base_step_list = []
        prior_list = [base_cluster]
        for t in range(0,levels):
            step_list=[]
            base_step_list=[]
            for base in prior_list:
                base,new_list=cluster_graph(base, to_measure, algorithm)
                base_step_list.append(base)
                step_list.extend(new_list)
            prior_list=step_list
            cluster_list.extend(base_step_list)
        # Add last hierarchy
        cluster_list.extend(step_list)

        if was_conditioned == False:
            # Decondition
            self.decondition()

        return cluster_list

    # %% Measures

    def yearly_centralities(self, year_list, focal_tokens=None,  types=["PageRank", "normedPageRank"], ego_nw_tokens=None, depth=1, context=None, weight_cutoff=None, norm_ties=True):
        """
        Compute directly year-by-year centralities for provided list.

        Parameters
        ----------
        year_list : list
            List of years for which to calculate centrality.
        focal_tokens : list, str
            List of tokens of interest. If not provided, centralities for all tokens will be returned.
        types : list, optional
            types of centrality to calculate. The default is ["PageRank"].
        ego_nw_tokens : list, optional - used when conditioning
             List of tokens for an ego-network if desired. Only used if no graph is supplied. The default is None.
        depth : TYPE, optional - used when conditioning
            Maximal path length for ego network. Only used if no graph is supplied. The default is 1.
        context : list, optional - used when conditioning
            List of tokens that need to appear in the context distribution of a tie. The default is None.
        weight_cutoff : float, optional - used when conditioning
            Only links of higher weight are considered in conditioning.. The default is None.
        norm_ties : bool, optional - used when conditioning
            Please see semantic network class. The default is True.

        Returns
        -------
        dict
            Dict of years with dict of centralities for focal tokens.

        """
        cent_year = {}
        assert isinstance(year_list, list), "Please provide list of years."
        for year in year_list:
            cent_measures = self.centralities(focal_tokens=focal_tokens, types=types, years=[
                                              year], ego_nw_tokens=ego_nw_tokens, depth=depth, context=context, weight_cutoff=weight_cutoff, norm_ties=norm_ties)
            cent_year.update({year: cent_measures})

        return {'yearly_centrality': cent_year}

    def centralities(self, focal_tokens=None,  types=["PageRank", "normedPageRank"], years=None, ego_nw_tokens=None, depth=1, context=None, weight_cutoff=None, norm_ties=True):
        """
        Calculate centralities for given tokens over an aggregate of given years.
        If not conditioned, the semantic network will be conditioned according to the parameters given.

        Parameters
        ----------
        focal_tokens : list, str, optional
            List of tokens of interest. If not provided, centralities for all tokens will be returned.
        types : list, optional
            Types of centrality to calculate. The default is ["PageRank", "normedPageRank"].
        years : dict, int, optional - used when conditioning
            Given year, or an interval dict {"start":YYYYMMDD,"end":YYYYMMDD}. The default is None.
        ego_nw_tokens : list, optional - used when conditioning
             List of tokens for an ego-network if desired. Only used if no graph is supplied. The default is None.
        depth : TYPE, optional - used when conditioning
            Maximal path length for ego network. Only used if no graph is supplied. The default is 1.
        context : list, optional - used when conditioning
            List of tokens that need to appear in the context distribution of a tie. The default is None.
        weight_cutoff : float, optional - used when conditioning
            Only links of higher weight are considered in conditioning.. The default is None.
        norm_ties : bool, optional - used when conditioning
            Please see semantic network class. The default is True.

        Returns
        -------
        dict
            Dict of centralities for focal tokens.

        """
        input_check(tokens=focal_tokens)
        input_check(tokens=ego_nw_tokens)
        input_check(tokens=context)
        input_check(years=years)

        if self.conditioned == False:
            was_conditioned = False
            if ego_nw_tokens == None:
                logging.debug("Conditioning year(s) {} with focus on tokens {}".format(
                    years, focal_tokens))
                self.condition(years=years, tokens=None, weight_cutoff=weight_cutoff,
                               depth=depth, context=context, norm=norm_ties)
                logging.debug("Finished conditioning, {} nodes and {} edges in graph".format(
                    len(self.graph.nodes), len(self.graph.edges)))
            else:
                logging.debug("Conditioning ego-network for {} tokens with depth {}, for year(s) {} with focus on tokens {}".format(
                    len(ego_nw_tokens), depth, years, focal_tokens))
                self.condition(years=years, tokens=ego_nw_tokens, weight_cutoff=weight_cutoff,
                               depth=depth, context=context, norm=norm_ties)
                logging.debug("Finished ego conditioning, {} nodes and {} edges in graph".format(
                    len(self.graph.nodes), len(self.graph.edges)))
        else:
            logging.warning(
                "Network already conditioned! No reconditioning attempted, parameters unused.")
            was_conditioned = True

        cent_dict = centrality(
            self.graph, focal_tokens=focal_tokens,  types=types)

        if was_conditioned == False:
            # Decondition
            self.decondition()

        return cent_dict

    def proximities(self, focal_tokens=None,  alter_subset=None, years=None, context=None, weight_cutoff=None, norm_ties=True):
        """
        Calculate proximities for given tokens.
        Conditions if network is not already conditioned.

        Parameters
        ----------
        focal_tokens : list, str, optional
            List of tokens of interest. If not provided, centralities for all tokens will be returned.
        alter_subset : list, str optional
            List of alters to show. Others are hidden. The default is None.
        years : dict, int, optional - used when conditioning
            Given year, or an interval dict {"start":YYYYMMDD,"end":YYYYMMDD}. The default is None.
        context : list, optional - used when conditioning
            List of tokens that need to appear in the context distribution of a tie. The default is None.
        weight_cutoff : float, optional - used when conditioning
            Only ties of higher weight are considered. The default is None.
        norm_ties : bool, optional - used when conditioning
            Norm ties to get correct probabilities. The default is True.

        Returns
        -------
        proximity_dict : dict
            Dictionary of form {token_id:{alter_id: proximity}}.

        """

        input_check(tokens=focal_tokens)
        input_check(tokens=alter_subset)
        input_check(tokens=context)
        input_check(years=years)

        if alter_subset is not None:
            alter_subset = self.ensure_ids(alter_subset)
        if focal_tokens is not None:
            focal_tokens = self.ensure_ids(focal_tokens)
        else:
            focal_tokens = self.ids

        if self.conditioned == True:
            logging.warning(
                "Network already conditioned! No reconditioning attempted, parameters unused.")
        proximity_dict = {}
        for token in focal_tokens:
            if self.conditioned == True:
                was_conditioned = True
            else:
                logging.debug(
                    "Conditioning year(s) {} with focus on token {}".format(years, token))
                self.condition(years, tokens=[
                    token], weight_cutoff=weight_cutoff, depth=1, context=context, norm=norm_ties)
                was_conditioned = False

            tie_dict = proximity(self.graph, focal_tokens=focal_tokens, alter_subset=alter_subset)[
                'proximity'][token]

            proximity_dict.update({token: tie_dict})

        if was_conditioned == False:
            # Decondition
            self.decondition()

        return {"proximity": proximity_dict}

    def to_backout(self, decay=None, method="invert", stopping=25):
        """
        If each node is defined by the ties to its neighbors, and neighbors
        are equally defined in this manner, what is the final composition
        of each node?

        Function redefines neighborhood of a node by following all paths
        to other nodes, weighting each path according to its length by the 
        decay parameter:
            a_ij is the sum of weighted, discounted paths from i to j

        Row sum then corresponds to Eigenvector or Bonacich centrality.


        Parameters
        ----------
        decay : float, optional
            Decay parameter determining the weight of higher order ties. The default is None.
        method : "invert" or "series", optional
            "invert" tries to invert the adjacency matrix.
            "series" uses a series computation. The default is "invert".
        stopping : int, optional
            Used if method is "series". Determines the maximum order of series computation. The default is 25.


        Returns
        -------
        None.

        """
        if self.conditioned == False:
            logging.warning(
                "Network is not conditioned. Conditioning on all data...")
            self.condition()

        self.graph = backout_measure(
            self.graph, decay=decay, method=method, stopping=stopping)

    def to_symmetric(self, technique="avg-sym"):
        """
        Make graph symmetric

        Parameters
        ----------
        technique : string, optional
            transpose: Transpose and average adjacency matrix. Note: Loses other edge parameters!
            min-sym: Retain minimum direction, no tie if zero / unidirectional.
            max-sym: Retain maximum direction; tie exists even if unidirectional.
            avg-sym: Average ties. 
            min-sym-avg: Average ties if link is bidirectional, otherwise no tie.
            The default is "avg-sym".

        Returns
        -------
        None.

        """

        if self.conditioned == False:
            logging.warning(
                "Network is not conditioned. Conditioning on all data...")
            self.condition()

        self.graph = make_symmetric(self.graph, technique)

    # %% Graph abstractions - for now only networkx

    def create_empty_graph(self):
        return nx.DiGraph()

    def delete_graph(self):
        self.graph = None

    # %% Utility functioncs
    def update_dicts(self):
        """Simply update dictionaries"""
        # Update dictionaries
        self.token_id_dict.update(dict(zip(self.tokens, self.ids)))

    def get_index_from_ID(self, id):
        """Index (order) of token in data structures used"""
        # Token has to be string
        assert isinstance(id, int)
        try:
            index = self.id_index_dict[id]
        except:
            raise LookupError("".join(
                ["Index of token with id ", str(id), " missing. Token not in network?"]))
        return index.item()

    def get_token_from_id(self, id):
        """Token of id in data structures used"""
        # id should be int
        assert np.issubdtype(type(id), np.integer)
        try:
            token = self.token_id_dict[id]
        except:
            # Graph is possibly conditioned or in the process of being conditioned
            # Check Backup dict from neo database.
            try:
                token = self.neo_token_id_dict[id]
            except:
                raise LookupError("".join(["Token with ID ", str(
                    id), " missing. Token not in network or database?"]))
        return token

    def get_id_from_token(self, token):
        """Id of token in data structures used"""
        # Token has to be string
        assert isinstance(token, str)
        try:
            id = int(self.token_id_dict[token])
        except:
            # Graph is possibly conditioned or in the process of being conditioned
            # Check Backup dict from neo database.
            try:
                id = int(self.neo_token_id_dict[token])
            except:
                raise LookupError(
                    "".join(["ID of token ", token, " missing. Token not in network or database?"]))
        return id

    def ensure_ids(self, tokens):
        """This is just to confirm mixed lists of tokens and ids get converted to ids"""
        if isinstance(tokens, (list, tuple, np.ndarray)):
            # Transform strings to corresponding IDs
            tokens = [self.get_id_from_token(x) if not np.issubdtype(
                type(x), np.integer) else x for x in tokens]
            # Make sure np arrays get transformed to int lists
            return [int(x) if not isinstance(x, int) else x for x in tokens]
        else:
            if not np.issubdtype(type(tokens), np.integer):
                return self.get_id_from_token(tokens)
            else:
                return int(tokens)

    def ensure_tokens(self, ids):
        """This is just to confirm mixed lists of tokens and ids get converted to ids"""
        if isinstance(ids, list):
            return [self.get_token_from_id(x) if not isinstance(x, str) else x for x in ids]
        else:
            if not isinstance(ids, str):
                return self.get_token_from_id(ids)
            else:
                return ids

    def export_gefx(self, path, delete_isolates=True):
        if self.conditioned == True:
            try:
                # Relabel nodes
                labeldict = dict(
                    zip(self.ids, [self.get_token_from_id(x) for x in self.ids]))
                reverse_dict = dict(
                    zip([self.get_token_from_id(x) for x in self.ids], self.ids))
                self.graph = nx.relabel_nodes(self.graph, labeldict)

                print(len(self.graph.nodes))
                if delete_isolates == True:
                    isolates = list(nx.isolates(self.graph))
                    logging.info(
                        "Found {} isolated nodes in graph, deleting.".format(len(isolates)))
                    cleaned_graph = self.graph.copy()
                    cleaned_graph.remove_nodes_from(isolates)
                    nx.write_gexf(cleaned_graph, path)
                else:
                    nx.write_gexf(self.graph, path)
                self.graph = nx.relabel_nodes(self.graph, reverse_dict)
                print(len(self.graph.nodes))
            except:
                raise SystemError("Could not save to %s " % path)

    # %% Graph Database Aliases
    def setup_neo_db(self, tokens, token_ids):
        """
        Creates tokens and token_ids in Neo database. Does not delete existing network!
        :param tokens: list of tokens
        :param token_ids: list of corresponding token IDs
        :return: None
        """
        self.db.setup_neo_db(tokens, token_ids)
        self.init_tokens()

    def init_tokens(self):
        """
        Gets all tokens and token_ids in the database
        and sets up two-way dicts
        :return:
        """
        # Run neo query to get all nodes
        ids, tokens = self.db.init_tokens()
        # Update results
        self.ids = ids
        self.tokens = tokens
        self.update_dicts()

    def query_nodes(self, ids, context=None, times=None, weight_cutoff=None, norm_ties=True):
        """
        Query multiple nodes by ID and over a set of time intervals, return distinct occurrences
        If provided with context, return under the condition that elements of context are present in the context element distribution of
        this occurrence
        :param ids: list of ids
        :param context: list of ids
        :param times: either a number format YYYY, or an interval dict {"start":YYYY,"end":YYYY}
        :param weight_cutoff: float in 0,1
        :return: list of tuples (u,occurrences)
        """
        # Make sure we have a list of ids
        ids = self.ensure_ids(ids)
        if not isinstance(ids, (list, np.ndarray)):
            ids = [ids]
        # Dispatch with or without context
        if context is not None:
            context = self.ensure_ids(context)
            if not isinstance(context, (list, np.ndarray)):
                context = [context]
            return self.db.query_multiple_nodes_in_context(ids, context, times, weight_cutoff, norm_ties)
        else:
            return self.db.query_multiple_nodes(ids, times, weight_cutoff, norm_ties)

    def query_multiple_nodes(self, ids, times=None, weight_cutoff=None, norm_ties=True):
        """
        Old interface
        """
        return self.query_nodes(ids, times, weight_cutoff, norm_ties)

    def query_multiple_nodes_context(self, ids, context, times=None, weight_cutoff=None, norm_ties=True):
        """
        Old interface
        """
        return self.db.query_nodes(self, ids, context, times, weight_cutoff, norm_ties)

    def insert_edges_context(self, ego, ties, contexts):
        return self.db.insert_edges_context(ego, ties, contexts)

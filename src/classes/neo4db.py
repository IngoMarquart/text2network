import copy
import logging
from collections.abc import MutableSequence
from src.utils.twowaydict import TwoWayDict
import numpy as np
# import neo4j
import neo4jCon as neo_connector
try:
    from neo4j import GraphDatabase
except:
    GraphDatabase = None


class neo4j_database():
    def __init__(self, neo4j_creds, agg_operator="SUM",
                 write_before_query=True,
                 neo_batch_size=10000, queue_size=100000, tie_query_limit=100000, tie_creation="UNSAFE",  context_tie_creation="SAFE",
                 logging_level=logging.NOTSET, connection_type="Bolt"):
        # Set logging level
        #logging.disable(logging_level)

        self.neo4j_connection, self.neo4j_credentials = neo4j_creds
        self.write_before_query = write_before_query


        # Set up Neo4j driver
        if connection_type=="Bolt" and GraphDatabase is not None:
            self.driver = GraphDatabase.driver(self.neo4j_connection, auth=self.neo4j_credentials)
            self.connection_type="Bolt"
            
            
        else: # Fallback custom HTTP connector for Neo4j <= 4.02
            self.driver = neo_connector.Connector(self.neo4j_connection, self.neo4j_credentials)
            self.connection_type="Fallback"
            


        # Neo4J Internals
        # Pick Merge or Create. Create will double ties but Merge becomes very slow for large networks
        if tie_creation == "SAFE":
            self.creation_statement = "MERGE"
        else:
            self.creation_statement = "CREATE"

        if context_tie_creation == "SAFE":
            self.context_creation_statement = "MERGE"
        else:
            self.context_creation_statement = "CREATE"
        self.neo_queue = []
        self.neo_batch_size = neo_batch_size
        self.queue_size = queue_size
        self.aggregate_operator = agg_operator
        
        # Init tokens in the database, required since order etc. may be different
        self.db_ids,self.db_tokens=self.init_tokens()
        self.db_ids=np.array(self.db_ids)
        self.db_tokens=np.array(self.db_tokens)
        self.db_id_dict={}
        # Init parent class
        super().__init__()

    # %% Setup

    def check_create_tokenid_dict(self,tokens,token_ids,fail_on_missing=False):
        tokens=np.array(tokens)
        self.db_tokens=np.array(self.db_tokens)
        token_ids = np.array(token_ids)
        db_ids= np.array(self.db_ids)
        if len(self.db_ids)>0:
            new_ids=[np.where(self.db_tokens==k)[0][0] for k in tokens if k in self.db_tokens ]
        else:
            new_ids=[]
        if not len(new_ids)==len(token_ids):
            missing_ids = np.array(list(np.setdiff1d(token_ids, token_ids[new_ids])))
            missing_tokens=tokens[missing_ids]

            msg="Token ID translation failed. {} Tokens missing in database: {}".format(len(missing_tokens),missing_tokens)
            if fail_on_missing==True:
                logging.error(msg)
                raise ValueError(msg)

            added_ids=list(range(len(db_ids),len(db_ids)+len(missing_tokens)))

            db_id_dict = {x[0]: x[1] for x in zip(token_ids[new_ids], new_ids)}
            db_id_dict2={x[0]: x[1] for x in zip(missing_ids, added_ids)}
            db_id_dict.update(db_id_dict2)
            self.db_id_dict=db_id_dict
            return new_ids,missing_tokens,added_ids
        else:
            # Update
            self.db_id_dict = {x[0]: x[1] for x in zip(token_ids, new_ids)}
            return new_ids,[],[]

    def translate_token_ids(self,ids,fail_on_missing=False):
        try:
            new_ids=[self.db_id_dict[x] for x in ids]
        except:
            msg="Could not translate {} token ids: {}".format(len(ids),ids)
            logging.error(msg)
            raise ValueError(msg)
        return new_ids


    def setup_neo_db(self, tokens, token_ids):
        """
        Creates tokens and token_ids in Neo database. Does not delete existing network!
        :param tokens: list of tokens
        :param token_ids: list of corresponding token IDs
        :return: None
        """
        logging.debug("Creating indecies and nodes in Neo4j database.")
        constr = [x['name'] for x in self.receive_query("CALL db.constraints")]
        # Create uniqueness constraints
        logging.debug("Creating constraints in Neo4j database.")
        if 'id_con' not in constr:
            query = "CREATE CONSTRAINT id_con ON(n:word) ASSERT n.token_id IS UNIQUE"
            self.add_query(query)
        if 'tk_con' not in constr:
            query = "CREATE CONSTRAINT tk_con ON(n:word) ASSERT n.token IS UNIQUE"
            self.add_query(query)
        constr = [x['name'] for x in self.receive_query("CALL db.indexes")]
        if 'timeindex' not in constr:
            query = "CREATE INDEX timeindex FOR (a:edge) ON (a.time)"
            self.add_query(query)
        if 'contimeindex' not in constr:
            query = "CREATE INDEX contimeindex FOR (a:context) ON (a.time)"
            self.add_query(query)
        if 'runidxindex' not in constr:
            query = "CREATE INDEX runidxindex FOR (a:edge) ON (a.run_index)"
            self.add_query(query)
        if 'conrunidxindex' not in constr:
            query = "CREATE INDEX conrunidxindex FOR (a:context) ON (a.run_index)"
            self.add_query(query)
        if 'posedgeindex' not in constr:
            query = "CREATE INDEX posedgeindex FOR (a:edge) ON (a.pos)"
            self.add_query(query)
        if 'posconindex' not in constr:
            query = "CREATE INDEX posconindex FOR (a:context) ON (a.pos)"
            self.add_query(query)
        # Need to write first because create and structure changes can not be batched
        self.non_con_write_queue()
        # Create nodes in neo db
        # Get rid of signs that can not be used
        tokens = [x.translate(x.maketrans({"\"": '#e1#', "'": '#e2#', "\\": '#e3#'})) for x in tokens]
        token_ids, missing_tokens, missing_ids=self.check_create_tokenid_dict(tokens,token_ids)
        if len(missing_tokens)>0:
            queries = [''.join(["MERGE (n:word {token_id: ", str(id), ", token: '", tok, "'})"]) for tok, id in
                       zip(missing_tokens, missing_ids)]
            self.add_queries(queries)
            self.non_con_write_queue()
        self.db_ids, self.db_tokens = self.init_tokens()

    def clean_database(self, time=None, del_limit=1000000):
        # DEBUG
        nr_nodes = self.receive_query("MATCH (n:edge) RETURN count(n) AS nodes")[0]['nodes']
        nr_context = self.receive_query("MATCH (n:context) RETURN count(*) AS nodes")[0]['nodes']
        logging.info("Before cleaning: Network has %i edge-nodes and %i context-nodes" % (nr_nodes, nr_context))

        if time is not None:
            # Delete previous edges
            node_query = ''.join(
                ["MATCH (p:edge {time:", str(time), "}) WITH p LIMIT ", str(del_limit), " DETACH DELETE p"])
            # Delete previous context edges
            context_query = ''.join(
                ["MATCH (p:context {time:", str(time), "})  WITH p LIMIT ", str(del_limit), "  DETACH DELETE p"])
        else:
            # Delete previous edges
            node_query = ''.join(
                ["MATCH (p:edge)  WITH p LIMIT ", str(del_limit), " DETACH DELETE p"])
            # Delete previous context edges
            context_query = ''.join(
                ["MATCH (p:context)  WITH p LIMIT ", str(del_limit), " DETACH DELETE p"])

        while nr_nodes > 0:
            # Delete edge nodes
            self.add_query(node_query, run=True)
            nr_nodes = self.receive_query("MATCH (n:edge) RETURN count(n) AS nodes")[0]['nodes']
            logging.info("Network has %i edge-nodes and %i context-nodes" % (nr_nodes, nr_context))
        while nr_context > 0:
            # Delete context nodes
            self.add_query(context_query,run=True)
            nr_context = self.receive_query("MATCH (n:context) RETURN count(*) AS nodes")[0]['nodes']
            logging.info("Network has %i edge-nodes and %i context-nodes" % (nr_nodes, nr_context))

        # DEBUG
        nr_nodes = self.receive_query("MATCH (n:edge) RETURN count(n) AS nodes")[0]['nodes']
        nr_context = self.receive_query("MATCH (n:context) RETURN count(*) AS nodes")[0]['nodes']
        logging.info("After cleaning: Network has %i nodes and %i ties" % (nr_nodes, nr_context))

    # %% Initializations
    def init_tokens(self):
        """
        Gets all tokens and token_ids in the database
        and sets up two-way dicts
        :return: ids,tokens
        """
        logging.debug("Querying tokens and filling data structure.")
        # Run neo query to get all nodes
        res = self.receive_query("MATCH (n:word) RETURN n.token_id, n.token")
        # Update results
        ids = [x['n.token_id'] for x in res]
        tokens = [x['n.token'] for x in res]
        return ids, tokens

    def prune_database(self):
        """
        Deletes all disconnected nodes
        Returns
        -------

        """
        logging.debug("Pruning disconnected tokens in database.")
        res = self.add_query("MATCH (n) WHERE size((n)--())=0 DELETE (n)", run=True)


    # %% Query Functions
    def query_multiple_nodes(self, ids, times=None, weight_cutoff=None, norm_ties=True):
        """
        Query multiple nodes by ID and over a set of time intervals
        :param ids: list of id's
        :param times: either a number format YYYYMMDD, or an interval dict {"start":YYYYMMDD,"end":YYYYMMDD}
        :param weight_cutoff: float in 0,1
        :return: list of tuples (u,v,Time,{weight:x})
        """
        logging.debug("Querying {} nodes in Neo4j database.".format(len(ids)))
        # Allow cutoff value of (non-aggregated) weights and set up time-interval query
        if weight_cutoff is not None:
            where_query = ''.join([" WHERE r.weight >=", str(weight_cutoff), " "])
            if isinstance(times, dict):
                where_query = ''.join([where_query, " AND  $times.start <= r.time<= $times.end "])
        else:
            if isinstance(times, dict):
                where_query = "WHERE  $times.start <= r.time<= $times.end "
            else:
                where_query = ""
        # Create query depending on graph direction and whether time variable is queried via where or node property
        # By default, a->b when ego->is_replaced_by->b
        # Given an id, we query b:id(sender)<-a(receiver)
        # This gives all ties where b -predicts-> a
        return_query = ''.join([" RETURN b.token_id AS sender,a.token_id AS receiver,count(r.pos) AS occurrences,",
                                self.aggregate_operator, "(r.weight) AS agg_weight order by receiver"])

        if isinstance(times, int):
            match_query = "UNWIND $ids AS id MATCH p=(a:word)-[:onto]->(r:edge {time:$times})-[:onto]->(b:word {token_id:id}) "
        else:
            match_query = "unwind $ids AS id MATCH p=(a:word)-[:onto]->(r:edge)-[:onto]->(b:word {token_id:id}) "

        # Format time to set for network
        if isinstance(times, int):
            nw_time = {"s": times, "e": times, "m": times}
        elif isinstance(times, dict):
            nw_time = {"s": times['start'], "e": times['end'], "m": int((times['end'] + times['start']) / 2)}
        else:
            nw_time = {"s": 0, "e": 0, "m": 0}

        # Create params with or without time
        if isinstance(times, dict) or isinstance(times, int):
            params = {"ids": ids, "times": times}
        else:
            params = {"ids": ids}

        query = "".join([match_query, where_query, return_query])
        res = self.receive_query(query, params)

        tie_weights = np.array([x['agg_weight'] for x in res])
        senders = [x['sender'] for x in res]
        receivers = [x['receiver'] for x in res]
        occurrences = [x['occurrences'] for x in res]
        # Normalization
        # Ties should be normalized by the number of occurrences of the receiver
        if norm_ties == True:
            norms = dict(self.query_occurrences(receivers, times, weight_cutoff))
            for i, token in enumerate(receivers):
                tie_weights[i] = tie_weights[i] / norms[token]

        ties = [
            (x[0], x[1],
             {'weight': x[2], 'time': nw_time['m'], 'start': nw_time['s'], 'end': nw_time['e'], 'occurrences': x[3]})
            for x in zip(senders, receivers, tie_weights, occurrences)]

        return ties

    def query_multiple_nodes_in_context(self, ids, context, times=None, weight_cutoff=None, norm_ties=True):
        """
        Query multiple nodes by ID and over a set of time intervals
        Each replacement must occur within a context-element distribution including at least one
        contextual token in context list
        :param ids: list of id's
        :param context: list of context ids
        :param times: either a number format YYYYMMDD, or an interval dict {"start":YYYYMMDD,"end":YYYYMMDD}
        :param weight_cutoff: float in 0,1
        :return: list of tuples (u,v,Time,{weight:x})
        """
        logging.debug("Querying {} nodes in Neo4j database.".format(len(ids)))

        # Create context query
        context_where = ' ALL(r in nodes(p) WHERE size([(r) - [: conto]->(:context) - [: conto]->(e:word) WHERE e.token_id IN $clist | e]) > 0 OR(r: word))'

        # Allow cutoff value of (non-aggregated) weights and set up time-interval query
        if weight_cutoff is not None:
            where_query = ''.join([" WHERE r.weight >=", str(weight_cutoff), " AND "])
            if isinstance(times, dict):
                where_query = ''.join([where_query, " $times.start <= r.time<= $times.end "])
        else:
            if isinstance(times, dict):
                where_query = "WHERE  $times.start <= r.time<= $times.end AND "
            else:
                where_query = "WHERE "

        # Join where and context query
        where_query = ' '.join([where_query, context_where])

        # Create query depending on graph direction and whether time variable is queried via where or node property
        # By default, a->b when ego->is_replaced_by->b
        # Given an id, we query b:id(sender)<-a(receiver)
        # This gives all ties where b -predicts-> a
        return_query = ''.join([" RETURN b.token_id AS sender,a.token_id AS receiver,count(r.pos) AS occurrences,",
                                self.aggregate_operator, "(r.weight) AS agg_weight order by receiver"])

        if isinstance(times, int):
            match_query = "UNWIND $ids AS id MATCH p=(a:word)-[:onto]->(r:edge {time:$times})-[:onto]->(b:word {token_id:id}) "
        else:
            match_query = "unwind $ids AS id MATCH p=(a:word)-[:onto]->(r:edge)-[:onto]->(b:word {token_id:id}) "

        # Format time to set for network
        if isinstance(times, int):
            nw_time = {"s": times, "e": times, "m": times}
        elif isinstance(times, dict):
            nw_time = {"s": times['start'], "e": times['end'], "m": int((times['end'] + times['start']) / 2)}
        else:
            nw_time = {"s": 0, "e": 0, "m": 0}

        # Create params with or without time
        if isinstance(times, dict) or isinstance(times, int):
            params = {"ids": ids, "times": times, "clist": context}
        else:
            params = {"ids": ids, "clist": context}

        query = "".join([match_query, where_query, return_query])
        res = self.receive_query(query, params)

        tie_weights = np.array([x['agg_weight'] for x in res])
        senders = [x['sender'] for x in res]
        receivers = [x['receiver'] for x in res]
        occurrences = [x['occurrences'] for x in res]
        # Normalization
        # Ties should be normalized by the number of occurrences of the receiver
        if norm_ties == True:
            norms = dict(self.query_occurrences_in_context(receivers, context, times, weight_cutoff))
            for i, token in enumerate(receivers):
                tie_weights[i] = tie_weights[i] / norms[token]

        ties = [
            (x[0], x[1],
             {'weight': x[2], 'time': nw_time['m'], 'start': nw_time['s'], 'end': nw_time['e'], 'occurrences': x[3]})
            for x in zip(senders, receivers, tie_weights, occurrences)]

        return ties

    def query_occurrences(self, ids, times=None, weight_cutoff=None):
        """
        Query multiple nodes by ID and over a set of time intervals, return distinct occurrences
        :param ids: list of id's
        :param times: either a number format YYYY, or an interval dict {"start":YYYY,"end":YYYY}
        :param weight_cutoff: float in 0,1
        :return: list of tuples (u,occurrences)
        """
        logging.debug("Querying {} node occurrences for normalization".format(len(ids)))
        # Allow cutoff value of (non-aggregated) weights and set up time-interval query
        # If times is a dict, we want an interval and hence where query
        if weight_cutoff is not None:
            where_query = ''.join([" WHERE r.weight >=", str(weight_cutoff), " "])
            if isinstance(times, dict):
                where_query = ''.join([where_query, " AND  $times.start <= r.time<= $times.end "])
        else:
            if isinstance(times, dict):
                where_query = "WHERE  $times.start <= r.time<= $times.end "
            else:
                where_query = ""
        # Create params with or without time
        if isinstance(times, dict) or isinstance(times, int):
            params = {"ids": ids, "times": times}
        else:
            params = {"ids": ids}

        return_query = ''.join([
                                   " WITH a.token_id AS idx, sum(r.weight) AS weight RETURN idx, round(sum(weight)) as occurrences order by idx"])

        if isinstance(times, int):
            match_query = "UNWIND $ids AS id MATCH p=(a:word  {token_id:id})-[:onto]->(r:edge {time:$times})-[:onto]->(b:word) "
        else:
            match_query = "unwind $ids AS id MATCH p=(a:word  {token_id:id})-[:onto]->(r:edge)-[:onto]->(b:word) "

        query = "".join([match_query, where_query, return_query])
        res = self.receive_query(query, params)

        ties = [(x['idx'], x['occurrences']) for x in res]

        return ties

    def query_occurrences_in_context(self, ids, context, times=None, weight_cutoff=None):
        """
        Query multiple nodes by ID and over a set of time intervals, return distinct occurrences
        under the condition that elements of context are present in the context element distribution of
        this occurrence
        :param ids: list of ids
        :param context: list of ids
        :param times: either a number format YYYY, or an interval dict {"start":YYYY,"end":YYYY}
        :param weight_cutoff: float in 0,1
        :return: list of tuples (u,occurrences)
        """

        logging.debug("Querying {} node occurrences for normalization".format(len(ids)))

        # Create context query
        context_where = ' ALL(r in nodes(p) WHERE size([(r) - [: conto]->(:context) - [: conto]->(e:word) WHERE e.token_id IN $clist | e]) > 0 OR(r: word))'

        # Allow cutoff value of (non-aggregated) weights and set up time-interval query
        # If times is a dict, we want an interval and hence where query
        if weight_cutoff is not None:
            where_query = ''.join([" WHERE r.weight >=", str(weight_cutoff), " AND "])
            if isinstance(times, dict):
                where_query = ''.join([where_query, " $times.start <= r.time<= $times.end AND "])
        else:
            if isinstance(times, dict):
                where_query = "WHERE  $times.start <= r.time<= $times.end AND "
            else:
                # Always need a WHERE query for context
                where_query = "WHERE "
        # Join where and context query
        where_query = ' '.join([where_query, context_where])

        # Create params with or without time
        if isinstance(times, dict) or isinstance(times, int):
            params = {"ids": ids, "times": times, "clist": context}
        else:
            params = {"ids": ids, "clist": context}

        # return_query = ''.join([" WITH a.token_id AS idx, r.seq_id AS sequence_id ,(r.time) as year, count(DISTINCT(r.pos)) as pos_count RETURN idx, sum(pos_count) AS occurrences order by idx"])
        return_query = " WITH s.token_id AS idx, sum(r.weight) AS weight RETURN idx, round(sum(weight)) as occurrences order by idx"
        if isinstance(times, int):
            match_query = "UNWIND $ids AS id MATCH p=(s:word  {token_id:id})-[:onto]->(r:edge {time:$times})-[:onto]->(v:word) "
        else:
            match_query = "unwind $ids AS id MATCH p=(s:word  {token_id:id})-[:onto]->(r:edge)-[:onto]->(v:word) "

        query = "".join([match_query, where_query, return_query])
        logging.debug(query)
        res = self.receive_query(query, params)

        ties = [(x['idx'], x['occurrences']) for x in res]

        return ties

    def query_context_element(self, ids, times=None, weight_cutoff=None, disable_normalization=False,
                              replacement_ce=False, ):
        """
        Queries the aggregated context element distribution for tokens given by ids.
        P(c|t € s) where t is the focal token appearing in s, and c is another random token appearing in s.
        Note that stopwords are ignored.
        :param ids: ids of focal token
        :param times: int or interval dict {"start":YYYY,"end":YYYY}
        :param weight_cutoff: list of tuples (u,v,Time,{weight:x, further parameters})
        :param disable_normalization: Do not normalize context element distribution
        :param replacement_ce: Query the context in which focal token replaces another token (reverse direction)
        :return:
        """
        # Allow cutoff value of (non-aggregated) weights and set up time-interval query
        if weight_cutoff is not None:
            where_query = ''.join([" WHERE c.weight >=", str(weight_cutoff), " "])
            if isinstance(times, dict):
                where_query = ''.join([where_query, " AND  $times.start <= c.time<= $times.end "])
        else:
            if isinstance(times, dict):
                where_query = "WHERE  $times.start <= c.time<= $times.end "
            else:
                where_query = ""
        # Create params with or without time
        if isinstance(times, dict) or isinstance(times, int):
            params = {"ids": ids, "times": times}
        else:
            params = {"ids": ids}

        # Format return query
        return_query = ''.join(
            [" RETURN b.token_id AS context_token,a.token_id AS focal_token,count(c.time) AS occurrences,",
             self.aggregate_operator, "(c.weight) AS agg_weight order by agg_weight"])
        if replacement_ce == False:
            if isinstance(times, int):
                match_query = "UNWIND $ids AS id MATCH p=(a: word {token_id:id})-[: onto]->(r:edge) - [: conto]->(c:context {time:$times}) - [: conto]->(b:word)"
            else:
                match_query = "UNWIND $ids AS id MATCH p=(a: word {token_id:id})-[: onto]->(r:edge) - [: conto]->(c:context) - [: conto]->(b:word)"
        else:
            # Reverse direction
            if isinstance(times, int):
                match_query = "UNWIND $ids AS id MATCH p=(a: word {token_id:id})<-[: onto]-(r:edge) - [: conto]->(c:context {time:$times}) - [: conto]->(b:word)"
            else:
                match_query = "UNWIND $ids AS id MATCH p=(a: word {token_id:id})<-[: onto]-(r:edge) - [: conto]->(c:context) - [: conto]->(b:word)"
        # Format time to set for network
        if isinstance(times, int):
            nw_time = {"s": times, "e": times, "m": times}
        elif isinstance(times, dict):
            nw_time = {"s": times['start'], "e": times['end'], "m": int((times['end'] + times['start']) / 2)}
        else:
            nw_time = {"s": 0, "e": 0, "m": 0}

        query = "".join([match_query, where_query, return_query])
        res = self.receive_query(query, params)
        focal_tokens = np.array([x['focal_token'] for x in res])
        context_tokens = np.array([x['context_token'] for x in res])
        weights = np.array([x['agg_weight'] for x in res])
        occurrences = np.array([x['occurrences'] for x in res])
        # Normalize context element
        if disable_normalization == False:
            for focal_token in np.unique(focal_tokens):
                mask = focal_tokens == focal_token
                weight_sum = np.sum(weights[mask])
                weights[mask] = weights[mask] / weight_sum

        ties = [(x[0], x[1], nw_time['m'],
                 {'weight': x[2], 't1': nw_time['s'], 't2': nw_time['e'], 'occurrences': x[3]})
                for x in zip(focal_tokens, context_tokens, weights, occurrences)]
        return ties

    # %% Insert functions
    def insert_edges_context(self, ego, ties, contexts, logging_level=logging.DEBUG):
        if logging_level is not None:
            logging.disable(logging_level)
        logging.debug("Insert {} ego nodes with {} ties".format(ego, len(ties)))
        # Tie direction matters
        # Ego by default is the focal token to be replaced. Normal insertion points the link accordingly.
        # Hence, a->b is an instance of b replacing a!
        # Contextual ties always point toward the context word!

        egos = np.array([x[0] for x in ties])
        alters = np.array([x[1] for x in ties])
        con_alters = np.array([x[1] for x in contexts])

        # token translation
        egos = np.array(self.translate_token_ids(egos))
        alters = np.array(self.translate_token_ids(alters))
        con_alters = np.array(self.translate_token_ids(con_alters))

        times = np.array([x[2] for x in ties])
        dicts = np.array([x[3] for x in ties])
        con_times = np.array([x[2] for x in contexts])
        con_dicts = np.array([x[3] for x in contexts])

        # Delte just to make sure translation is taken
        del ties, contexts

        unique_egos = np.unique(egos)
        if len(unique_egos) == 1:
            ties_formatted = [{"alter": int(x[0]), "time": int(x[1]), "weight": float(x[2]['weight']),
                               "seq_id": int(x[2]['seq_id']),
                               "pos": int(x[2]['pos']),
                               "run_index": int(x[2]['run_index']),
                               "p1": ((x[2]['p1']) if len(x[2]) > 4 else 0),
                               "p2": ((x[2]['p2']) if len(x[2]) > 5 else 0),
                               "p3": ((x[2]['p3']) if len(x[2]) > 6 else 0),
                               "p4": ((x[2]['p4']) if len(x[2]) > 7 else 0), }
                              for x in zip(alters.tolist(), times.tolist(), dicts.tolist())]
            contexts_formatted = [{"alter": int(x[0]), "time": int(x[1]), "weight": float(x[2]['weight']),
                                   "seq_id": int(x[2]['seq_id'] if len(x[2]) > 2 else 0),
                                   "pos": int(x[2]['pos'] if len(x[2]) > 3 else 0),
                                   "run_index": int(x[2]['run_index'] if len(x[2]) > 1 else 0),
                                   "p1": ((x[2]['p1']) if len(x[2]) > 4 else 0),
                                   "p2": ((x[2]['p2']) if len(x[2]) > 5 else 0),
                                   "p3": ((x[2]['p3']) if len(x[2]) > 6 else 0),
                                   "p4": ((x[2]['p4']) if len(x[2]) > 7 else 0), }
                                  for x in zip(con_alters.tolist(), con_times.tolist(), con_dicts.tolist())]
            params = {"ego": int(egos[0]), "ties": ties_formatted, "contexts": contexts_formatted}

            # Select order of parameters
            p1 = np.array([str(x['p1']) if (len(x)>4) else "0" for x in dicts ])
            p2 = np.array([str(x['p2']) if (len(x)>5) else "0" for x in dicts ])
            p3 = np.array([str(x['p3']) if (len(x)>6) else "0" for x in dicts ])
            p4 = np.array([str(x['p4']) if (len(x)>7) else "0" for x in dicts ])
            # Select order of context parameters
            cseq_id = np.array([x['seq_id'] if len(x)>2 else "0" for x in con_dicts ], dtype=np.str)
            cpos = np.array([x['pos'] if len(x)>3 else "0" for x in con_dicts ], dtype=np.str)
            crun_index = np.array([x['run_index'] if len(x)>1 else "0" for x in con_dicts ], dtype=np.str)
            cp1 =  np.array([str(x['p1']) if (len(x)>4) else "0" for x in con_dicts ])
            cp2 =  np.array([str(x['p2']) if (len(x)>5) else "0" for x in con_dicts ])
            cp3 =  np.array([str(x['p3']) if (len(x)>6) else "0" for x in con_dicts ])
            cp4 = np.array([str(x['p4'] )if (len(x)>7) else "0" for x in con_dicts ])


            # Build parameter string
            parameter_string=""
            if not all(p1 == "0") and not all(p1==''):
                parameter_string=parameter_string+", p1:tie.p1"
            if not all(p2 == "0") and not all( p2==''):
                parameter_string=parameter_string+", p2:tie.p2"
            if not all(p3 == "0") and not all(p3==''):
                parameter_string=parameter_string+", p3:tie.p3"
            if not all(p4 == "0") and not all( p4==''):
                parameter_string=parameter_string+", p4:tie.p4 "


            cparameter_string = ""
            if not all(cseq_id == "0") and not all(cseq_id==''):
                cparameter_string = cparameter_string + ", seq_id:con.seq_id"
            if not all(cpos == "0" ) and not all(cpos==''):
                cparameter_string = cparameter_string + ", pos:con.pos"
            if not all(crun_index == "0") and not all(crun_index==''):
                cparameter_string = cparameter_string + ", run_index:con.run_index"
            if not all(cp1 == "0") and not all(cp1==''):
                cparameter_string = cparameter_string + ", p1:con.p1"
            if not all(cp2 == "0" ) and not all( cp2==''):
                cparameter_string = cparameter_string + ", p2:con.p2"
            if not all(cp3 == "0" ) and not all(cp3==''):
                cparameter_string = cparameter_string + ", p3:con.p3"
            if not all(cp4 == "0" ) and not all(cp4==''):
                cparameter_string = cparameter_string + ", p4:con.p4"


            query = ''.join(
                [" MATCH (a:word {token_id: $ego}) WITH a UNWIND $ties as tie MATCH (b:word {token_id: tie.alter}) ",
                 self.creation_statement,
                 " (b)<-[:onto]-(r:edge {weight:tie.weight, time:tie.time, seq_id:tie.seq_id,pos:tie.pos, run_index:tie.run_index ",parameter_string, "})<-[:onto]-(a) WITH r UNWIND $contexts as con MATCH (q:word {token_id: con.alter}) WITH r,q,con MERGE (c:context {weight:con.weight, time:con.time ", cparameter_string, "})-[:conto]->(q) WITH r,c ",
                 self.context_creation_statement,
                 " (r)-[:conto]->(c)"])
        else:
            logging.error("Batched edge creation with context for multiple egos not supported.")
            raise NotImplementedError

        self.add_query(query, params)

    # %% Neo4J interaction
    # All function that interact with neo are here, dispatched as needed from above

    def add_query(self, query, params=None, run=False):
        """
        Add a single query to queue
        :param query: Neo4j query
        :param params: Associates parameters
        :return:
        """
        if params is not None:
            self.add_queries([query], [params])
        else:
            self.add_queries([query], None)
        
        if run==True:
            self.write_queue()

    def add_queries(self, query, params=None):
        """
        Add a list of query to queue
        :param query: list - Neo4j queries
        :param params: list - Associates parameters corresponding to queries
        :return:
        """
        assert isinstance(query, list)

        if params is not None:
            assert isinstance(params, list)
            statements = [neo_connector.Statement(q, p) for (q, p) in zip(query, params)]
            self.neo_queue.extend(statements)
        else:
            statements = [neo_connector.Statement(q) for (q) in query]
            self.neo_queue.extend(statements)

        # Check for queue size if not conditioned!
        if (len(self.neo_queue) > self.queue_size) and (self.conditioned == False):
            self.write_queue()

    def write_queue(self):
        """
        If called will run queries in the queue and empty it.
        :return:
        """
        if len(self.neo_queue) > 0:
            if self.connection_type=="Bolt":
                with self.driver.session() as session:
                    with session.begin_transaction() as tx:
                        for statement in self.neo_queue:
                            if 'parameters' in statement:
                                tx.run(statement['statement'],statement['parameters'])
                            else:
                                tx.run(statement['statement'])
                        tx.commit()
                        tx.close()
            else:
                ret = self.connector.run_multiple(self.neo_queue, self.neo_batch_size)
                logging.debug(ret)

            self.neo_queue = []

    def non_con_write_queue(self):
        """
        Utility function to write queue immediately
        :return:
        """
        self.write_queue()
   
    def consume_result(self, tx, query, params=None):
        result = tx.run(query,params)
        return result.data()
        
    
    def receive_query(self, query, params=None):
        if self.connection_type=="Bolt":
            with self.driver.session() as session:
                res = session.read_transaction(self.consume_result, query, params)
        else:
            res = self.connector.run(query, params)
        
        return res
        
    def close(self):
        self.driver.close()
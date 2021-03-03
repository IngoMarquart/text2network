from src.functions.file_helpers import check_create_folder
from src.functions.measures import average_fixed_cluster_proximities, extract_all_clusters
from src.utils.logging_helpers import setup_logger
import logging
import time
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
from src.functions.node_measures import proximity, centrality
from src.functions.graph_clustering import consensus_louvain, louvain_cluster
from src.classes.neo4jnw import neo4j_network

# Set a configuration path
configuration_path = '/config/config.ini'
# Settings
years = range(1980, 2020)
focal_words = ["leader", "manager"]
focal_token = "leader"
alter_subset = ["boss"]
alter_subset = ["ceo", "kid", "manager", "head", "sadhu", "boss", "collector", "arbitrator", "offender", "partner", "person", "catcher", "player", "founder", "musician", "volunteer", "golfer", "commander", "employee", "speaker", "coach", "candidate", "champion", "expert", "negotiator", "owner", "chief", "entrepreneur", "successor", "star", "salesperson", "teacher", "alpha", "cop", "performer", "editor", "agent", "supervisor", "chef", "builder", "consultant", "listener", "assistant", "veteran", "journalist", "physicist", "chair", "reformer", "facilitator", "ally", "buddy", "colleague", "enthusiast", "proponent", "artist", "composer", "achiever", "citizen", "researcher", "hero", "minister", "designer", "protagonist", "writer", "scientist", "fool", "mayor", "senator", "admiral", "statesman", "co", "lawyer", "middle", "prosecutor", "businessman", "billionaire", "actor", "baseman", "politician", "novice", "secretary", "driver", "jerk", "rebel", "lieutenant", "victim", "sergeant", "inventor", "front", "helm"]
alter_subset = ["chieftain", "enemy", "congressman", "ombudsman", "believer", "deputy", "guest", "magistrate", "heir", "wizard", "hostess", "protaga", "athlete", "supervisor", "head", "emeritus", "critic", "thief", "man", "golfer", "policeman", "trainer", "visitor", "specialist", "trainee", "helper", "adjunct", "prey", "scholar", "dreamer", "titan", "partner", "resident", "preacher", "boxer", "successor", "reformer", "prosecutor", "warlord", "rocker", "peasant", "chairs", "champ", "coward", "salesperson", "comptroller", "sponsor", "builder", "former", "cornerback", "colonel", "bully", "negotiator", "nun", "rebel", "reporter", "hitter", "technician", "rear", "top", "warriors", "savior", "magician", "representative", "president", "hillbilly", "practitioner", "sheriff", "biker", "teenager", "patriarch", "front", "creature", "creator", "superstar", "archbishop", "monkey", "selector", "alpha", "player", "superman", "collaborator", "villain", "bystander", "director", "bearer", "advisor", "coordinator", "entrepreneur", "legislator", "keeper", "composer", "linguist", "spy", "predecessor", "priests", "recruiter", "offender", "co", "newcomer", "auditor", "missionary", "researcher", "slave", "outsider", "sociologist", "pessimist", "publisher", "salesman", "mentor", "racer", "heads", "spectator", "guardian", "aide", "ops", "sidekick", "teammate", "dean", "sergeant", "organizer", "instrumentalist", "contestant", "expert", "novice", "presidency", "warrior", "valet", "geek", "adversary", "intern", "victim", "sage", "liaison", "chairperson", "middle", "analyst", "minister", "chief", "crusader", "person", "bargainer", "commodore", "donor", "cop", "star", "forecaster", "psychologist", "calf", "poet", "administrator", "friend", "skipper", "operator", "vp", "biographer", "consultant", "counsels", "businessman", "buddy", "thinker", "moderator", "kid", "dictator", "celebrity", "seeker", "benefactor", "hacker", "citizen", "shortstop", "founding", "volunteer", "subordinate", "attorney", "skier", "theologian", "shooter", "coach", "bulldozer", "boy", "martyr", "counselor", "skeptic", "architect", "foreigner", "geologist", "therapist", "vo", "crook", "pianist", "enthusiast", "jock", "quarterback", "abolitionist", "nemesis", "diplomat", "professor", "journalist", "participant", "individualist", "captain", "philanthropist", "innovator", "officer", "priest", "holder", "trustee", "screenwriter", "playwright", "superintendent", "listener", "undertaker", "narrator", "lover", "mathematician", "choreographer", "ringmaster", "drummer", "baton", "connector", "patron", "opponent", "exec", "senior", "antagonist", "tops", "biologist", "scientist", "pioneer", "artist", "optimizers", "student", "columnist", "presidents", "strategist", "comrade", "alchemist", "governor", "performer", "lawyer", "apprentice", "swimmer", "guy", "anthropologist", "proprietor", "senator", "interpreter", "prisoner", "correspondent", "fortune", "regulator", "secretary", "manager", "banker", "apex", "translator", "chancellor", "writer", "scribe", "worker", "soldier", "historian", "executive", "neighbor", "chair", "chemist", "promoter", "industrialist", "perfectionist", "cartoonist", "applicant", "referee", "procrastinator", "controller", "receptionist", "storyteller", "educator", "examiner", "instructor", "ranger", "batter", "waiter", "synthesizer", "activist", "narcissist", "trader", "stars", "integrator", "hero", "statesman", "assistant", "godfather", "actor", "astronaut", "counsel", "freak", "monarch", "healer", "gardener", "farmer", "musician", "champion", "fan", "associate", "persuader", "psychoanalyst", "clergy", "summaries", "harasser", "physicist", "diva", "amateur", "chairman", "commander", "achiever", "conductor", "junior", "fellow", "goalkeeper", "disciple", "economist", "sadhu", "philosopher", "colleague", "ally", "sprinter", "adviser", "catcher", "editor", "evangelist", "starter", "accountant", "observer", "developer", "vice", "millionaire", "steward", "sailor", "librarian", "asshole", "cofounder", "clown", "nominee", "blogger", "tokugawa", "waitress", "bitch", "mayor", "gangster", "spokesperson", "ruler", "foreman", "avatar", "baseman", "swami", "recipient", "clerk", "expat", "ceo", "hulk", "latter", "arbitrator", "apostle", "contender", "boss", "cum", "broker", "craftsman", "politician", "theorist", "finalist", "guru", "chro", "messenger", "commissioner", "employee", "psychiatrist", "designer", "lieutenant", "rabbi", "spokesman", "investigator", "novelist", "speaker", "reviewer", "teacher", "foe", "dude", "servant", "admiral", "billionaire", "fool", "collector", "protector", "chef", "actress", "programmer", "stranger", "survivor", "idiot", "lobbyist", "presenter", "dentist", "veteran", "founder", "confidant", "filmmaker", "sergeants", "contributor", "dancer", "guitarist", "sucker", "bottom", "owner", "coachee", "fundraiser", "helm", "follower", "reader", "pitcher", "tyrant", "supporter", "jerk", "protege", "engineer", "photographer", "agent", "headmaster", "ambassador", "sculptor", "candidate", "corporal", "gentleman", "inventor", "protagonist", "bulldog", "proponent", "solver", "driver", "frontline", "treasurer", "facilitator", "rep", "planner", "commentator", "liar", "skeptics", "redhead", "author", "economists", "coauthor", "wife", "brother", "dad", "sons", "cousins", "girl", "apes", "widow", "mate", "daughter", "lady", "grandparents", "nephew", "spouse", "male", "fleas", "father", "feminist", "nanny", "maiden", "women", "children", "youth", "scout", "maternal", "son", "stepmother", "mother", "sister", "female", "uncle", "families", "offspring", "woman", "daddy", "cousin", "lesbian", "mom", "grandfather", "mover", "loser", "runner", "laureate", "winner", "impostor"]


# Load Configuration file
import configparser

config = configparser.ConfigParser()
print(check_create_folder(configuration_path))
config.read(check_create_folder(configuration_path))
# Setup logging
setup_logger(config['Paths']['log'], config['General']['logging_level'], "clustering")

# First, create an empty network
semantic_network = neo4j_network(config)

#### Cluster test
level_list = [5,5,5,5,5,5,5,5,5,5]
weight_list = [0,0.1,0,0.1,0,0.1,0.01,0.01,0.05,0.05]
depth_list = [1,1,1,1,1,1,0,0,0,0]
rs_list = [100,100,200,200,300,300,200,300,200,300]

logging.info("------------------------------------------------")
for depth, level, rs,cutoff in zip(depth_list,level_list,rs_list,weight_list):
    del semantic_network
    semantic_network = neo4j_network(config)
    filename = "".join(
        [config['Paths']['csv_outputs'], "/", str(focal_token), "_con_egocluster_lev", str(level), "_cut",
         str(cutoff), "_depth", str(depth),
         ".xlsx"])
    focal_token = "leader"
    logging.info("Network clustering: {}".format(filename))
    # Random Seed
    np.random.seed(rs)
    df = extract_all_clusters(level=level, cutoff=cutoff,focal_token=focal_token, semantic_network=semantic_network, depth= depth, interest_list=alter_subset, algorithm=louvain_cluster, filename=filename)
    logging.info(df)

#### Cluster yearly proximities
# Random Seed
np.random.seed(100)

ma_list=[(0,0),(1,1),(2,0),(2,1),(0,0),(1,1),(2,0),(2,1),(0,0),(1,1),(2,0),(2,1),(0,0),(1,1),(2,0),(2,1),(0,0),(1,1),(2,0),(2,1)]
level_list = [5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5]
weight_list = [0,0,0,0,0.05,0.05,0.05,0.05,0,0,0,0,0,0,0,0,0.1,0.1,0.1,0.1]
depth_list = [2,2,2,2,0,0,0,0,0,0,0,0]

logging.info("------------------------------------------------")
for depth, levels, moving_average,weight_cutoff in zip(depth_list,level_list,ma_list,weight_list):
    focal_token="leader"
    interest_tokens=alter_subset
    #levels=5
    #depth=1
    #moving_average=(1,1)
    cluster_cutoff=0.1
    #weight_cutoff=0
    filename = "".join(
        [config['Paths']['csv_outputs'], "/", str(focal_token), "_con_yearfixed_lev", str(levels), "_clcut",
         str(cluster_cutoff),"_cut", str(weight_cutoff), "_depth", str(depth),"_ma",str(moving_average),
         ".xlsx"])

    #df=average_fixed_cluster_proximities(focal_token, interest_tokens, semantic_network, levels,do_reverse=True, depth=depth,weight_cutoff=weight_cutoff,cluster_cutoff=cluster_cutoff, moving_average=moving_average,filename=filename)
    #logging.info(df)

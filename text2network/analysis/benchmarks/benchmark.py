from src.functions.file_helpers import check_create_folder
from src.utils.logging_helpers import setup_logger
import logging
import time
import numpy as np
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
setup_logger(config['Paths']['log'], config['General']['logging_level'], "bench")

# First, create an empty network
semantic_network = neo4j_network(config)

#### Conditioning test
level_list = [5,5,5,5,5]
weight_list = [0,0.1,0,0.1,0,0.1]
depth_list = [1,1,1,1,1,1]
rs_list = [100,200,300]
year_list = [2000,2010,2010,1980,1986]
focal_token = "leader"

logging.info("-----------------Conditioning---------------------")
logger = logging.getLogger('neo4j')
logger.setLevel(level=logging.ERROR)

logging.info("------------------------------------------------")
test_name="Normed 1 Year  Conditioning"
tokens=['leader']
years=year_list
weight_cutoff=0.1
depth=1
context=None
norm=True
param_string="Years: {}, Tokens: {}, Cutoff: {}, Depth: {}, Context: {}, Norm: {}".format(years,tokens,weight_cutoff,depth,context,norm)
logging.info("------- {} -------".format(test_name))
time_list=[]
semantic_network = neo4j_network(config)
# Random Seed
for year in years:
    start_time=time.time()
    np.random.seed(100)
    logging.disable(logging.ERROR)
    semantic_network.decondition()
    semantic_network.condition(years=year, tokens=tokens,weight_cutoff=weight_cutoff,depth=depth,context=context,norm=norm)

    elapsed_time=time.time() - start_time
    time_list.append(elapsed_time)
    #logging.info("{} finished in {} seconds".format(year, elapsed_time))
    #logging.info("nodes in network %i" % (len(semantic_network)))
    #logging.info("ties in network %i" % (semantic_network.graph.number_of_edges()))
logging.disable(logging.NOTSET)
logging.info("------------------------------------------------")
logging.info("{} finished in average {} seconds".format(test_name,np.mean(time_list)))
logging.info(param_string)
logging.info("nodes in network %i" % (len(semantic_network)))
logging.info("ties in network %i" % (semantic_network.graph.number_of_edges()))
logging.info("------------------------------------------------")


logging.info("------------------------------------------------")
test_name="List Normed 1 Year  Conditioning"
tokens=['leader']
years=year_list
#weight_cutoff=0.3
#depth=1
context=None
norm=True
param_string="(List) Years: {}, Tokens: {}, Cutoff: {}, Depth: {}, Context: {}, Norm: {}".format(years,tokens,weight_cutoff,depth,context,norm)
logging.info("------- {} -------".format(test_name))
time_list=[]
semantic_network = neo4j_network(config, consume_type="list")
# Random Seed
for year in years:
    start_time=time.time()
    np.random.seed(100)
    logging.disable(logging.ERROR)
    semantic_network.decondition()
    semantic_network.condition(years=year, tokens=tokens,weight_cutoff=weight_cutoff,depth=depth,context=context,norm=norm)
    logging.disable(logging.NOTSET)
    elapsed_time=time.time() - start_time
    time_list.append(elapsed_time)
    #logging.info("{} finished in {} seconds".format(year, elapsed_time))
    #logging.info("nodes in network %i" % (len(semantic_network)))
    #logging.info("ties in network %i" % (semantic_network.graph.number_of_edges()))
logging.disable(logging.NOTSET)
logging.info("------------------------------------------------")
logging.info("{} finished in average {} seconds".format(test_name,np.mean(time_list)))
logging.info(param_string)
logging.info("nodes in network %i" % (len(semantic_network)))
logging.info("ties in network %i" % (semantic_network.graph.number_of_edges()))
logging.info("------------------------------------------------")



logging.info("------------------------------------------------")
test_name=" 1 Year  Conditioning"
tokens=['leader']
years=year_list
#weight_cutoff=0.3
#depth=1
context=None
norm=False
param_string="Years: {}, Tokens: {}, Cutoff: {}, Depth: {}, Context: {}, Norm: {}".format(years,tokens,weight_cutoff,depth,context,norm)
logging.info("------- {} -------".format(test_name))
time_list=[]
semantic_network = neo4j_network(config)
# Random Seed
for year in years:
    start_time=time.time()
    np.random.seed(100)
    logging.disable(logging.ERROR)
    semantic_network.decondition()
    semantic_network.condition(years=year, tokens=tokens,weight_cutoff=weight_cutoff,depth=depth,context=context,norm=norm)
    elapsed_time=time.time() - start_time
    time_list.append(elapsed_time)
    #logging.info("{} finished in {} seconds".format(year, elapsed_time))
    #logging.info("nodes in network %i" % (len(semantic_network)))
    #logging.info("ties in network %i" % (semantic_network.graph.number_of_edges()))
logging.disable(logging.NOTSET)
logging.info("------------------------------------------------")
logging.info("{} finished in average {} seconds".format(test_name,np.mean(time_list)))
logging.info(param_string)
logging.info("nodes in network %i" % (len(semantic_network)))
logging.info("ties in network %i" % (semantic_network.graph.number_of_edges()))
logging.info("------------------------------------------------")


logging.info("------------------------------------------------")
test_name="List 1 Year  Conditioning"
tokens=['leader']
years=year_list
#weight_cutoff=0.3
#depth=1
context=None
norm=False
param_string="(List) Years: {}, Tokens: {}, Cutoff: {}, Depth: {}, Context: {}, Norm: {}".format(years,tokens,weight_cutoff,depth,context,norm)
logging.info("------- {} -------".format(test_name))
time_list=[]
semantic_network = neo4j_network(config, consume_type="list")
# Random Seed
for year in years:

    start_time=time.time()
    np.random.seed(100)
    logging.disable(logging.ERROR)
    semantic_network.decondition()
    semantic_network.condition(years=year, tokens=tokens,weight_cutoff=weight_cutoff,depth=depth,context=context,norm=norm)
    elapsed_time=time.time() - start_time
    time_list.append(elapsed_time)
    #logging.info("{} finished in {} seconds".format(year, elapsed_time))
    #logging.info("nodes in network %i" % (len(semantic_network)))
    #logging.info("ties in network %i" % (semantic_network.graph.number_of_edges()))
logging.disable(logging.NOTSET)
logging.info("------------------------------------------------")
logging.info("{} finished in average {} seconds".format(test_name,np.mean(time_list)))
logging.info(param_string)
logging.info("nodes in network %i" % (len(semantic_network)))
logging.info("ties in network %i" % (semantic_network.graph.number_of_edges()))
logging.info("------------------------------------------------")
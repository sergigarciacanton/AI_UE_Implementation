# DEPENDENCIES
import random
import networkx as nx
from config import (
    MAX_GPU,
    MIN_GPU,
    MAX_RAM,
    MIN_RAM,
    MAX_BW,
    MIN_BW,
    EDGES_COST,)

# GLOBALS
# Represent scenario as a graph with node, edges and edges cost
G = nx.Graph()
G.add_edges_from((u, v, {'weight': w}) for (u, v), w in EDGES_COST.items())


# CLASS
class VNF:
    """ Generate random VNF requests"""
    def __init__(self, seed=None):
        # Set the seed
        random.seed(seed)
        # Ensure ns and nd are not the same. Nodes start at 0 and end at number_of_nodes
        self.__ns, self.__nd = random.sample(range(0, G.number_of_nodes()), 2)
        self.__gpu = random.choice([MIN_GPU, MAX_GPU])
        self.__ram = random.choice([MIN_RAM, MAX_RAM])
        self.__bw = random.choice([MIN_BW, MAX_BW])

    def get_request(self):
        return dict(source=self.__ns, target=self.__nd, gpu=self.__gpu, ram=self.__ram, bw=self.__bw)

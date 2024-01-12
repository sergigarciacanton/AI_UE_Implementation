# DEPENDENCIES
import random

import networkx as nx
from config import (
    VNF_GPU,
    VNF_RAM,
    VNF_BW,
    NODES_2_TRAIN,
    SEED)

# Activate deterministic randomness
if SEED is not None:
    random.seed(SEED)


def set_nodes_for_route(nodes_for_bg_vehicles=None, nodes_to_evaluate=None):
    if nodes_for_bg_vehicles is not None:
        source_n, target_n = random.sample(nodes_for_bg_vehicles, 2)
    elif nodes_to_evaluate is not None:
        source_n, target_n = nodes_to_evaluate
    else:
        source_n, target_n = random.sample(NODES_2_TRAIN, 2)
    return source_n, target_n


# CLASS
class VNF:
    """ Generate random VNF requests"""

    def __init__(self, nodes_for_bg_vehicles, nodes_to_evaluate=None):
        # Ensure ns and nd are not the same. Nodes start at 0 and end at number_of_nodes
        self.__ns, self.__nd = set_nodes_for_route(nodes_for_bg_vehicles, nodes_to_evaluate)
        self.__gpu = random.choice(VNF_GPU)
        self.__ram = random.choice(VNF_RAM)
        self.__bw = random.choice(VNF_BW)

    def get_request(self):
        return dict(source=self.__ns, target=self.__nd, gpu=self.__gpu, ram=self.__ram, bw=self.__bw)

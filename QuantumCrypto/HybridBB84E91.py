from sequence.kernel.timeline import Timeline

from sequence.topology.node import Node
from sequence.components.photon import Photon
from sequence.components.light_source import LightSource
from sequence.components.optical_channel import QuantumChannel
from sequence.components.detector import Detector
import numpy as np
from sequence.kernel.process import Process
from sequence.kernel.event import Event
from sequence.topology.node import Node
from sequence.components.memory import Memory
from sequence.entanglement_management.generation import EntanglementGenerationA
from sequence.kernel.timeline import Timeline
from sequence.topology.node import BSMNode
from sequence.components.optical_channel import QuantumChannel, ClassicalChannel
from math import sqrt


tl = Timeline()
class AliceBob(Node):
    def __init__(self, name, timeline, seed=None, gate_fid = 1, meas_fid = 1):
        super().__init__(name, timeline, seed, gate_fid, meas_fid)

        self.memory = Memory(f'{name}.memory',timeline,1,2000,1,-1,500)

        self.add_receiver(self)
        self.add_component(self.memory)
    
    def get(self, photon, **kwargs):
        return super().get(photon, **kwargs)
    
def entangle_memory(memo1, memo2, fidelity):
    from math import sqrt

    memo1.reset()
    memo2.reset()

    # classical link
    memo1.entangled_memory['node_id'] = memo2.owner.name
    memo1.entangled_memory['memo_id'] = memo2.name
    memo2.entangled_memory['node_id'] = memo1.owner.name
    memo2.entangled_memory['memo_id'] = memo1.name

    memo1.fidelity = memo2.fidelity = fidelity

    # quantum entanglement
    qm = memo1.timeline.quantum_manager
    qm.set(
        [memo1.qstate_key, memo2.qstate_key],
        [1/sqrt(2), 0, 0, 1/sqrt(2)]
    )

alice = AliceBob('alice',tl)
bob = AliceBob('bob',tl)

print("before:",alice.memory.get_bds_state())
alice.memory.update_state([complex(sqrt(1/2)),complex(sqrt(1/2))])
bob.memory.update_state([complex(sqrt(1/2)),complex(sqrt(1/2))])

print("after:",alice.memory.get_bds_state())
# print("after:",alice.memory.get_bds_state())

print("before entanglement:",alice.memory.entangled_memory)



entangle_memory(alice.memory,bob.memory,1)

print('after entanglement:',alice.memory.entangled_memory)

print("after-bob:",bob.memory.get_bds_state())

# qm = alice.memory.timeline.quantum_manager

# k1 = alice.memory.qstate_key
# k2 = bob.memory.qstate_key

from sequence.components.circuit import Circuit
import random

alice_angles = [0, 45, 90]
bob_angles   = [45, 90, 135]

a = random.choice(alice_angles)
b = random.choice(bob_angles)

circuit = Circuit(2)

# -------- Alice (qubit 0) --------
if a == 45:
    circuit.minus_root_iY(0)
elif a == 90:
    circuit.h(0)

# -------- Bob (qubit 1) --------
if b == 45:
    circuit.minus_root_iY(1)
elif b == 90:
    circuit.h(1)
elif b == 135:
    circuit.root_iY(1)

# measure both
circuit.measure(0)
circuit.measure(1)

qm = alice.memory.timeline.quantum_manager
rng = alice.get_generator()

result = qm.run_circuit(
    circuit,
    [alice.memory.qstate_key, bob.memory.qstate_key],
    meas_samp=rng.random()
)

print("Alice angle:", a, "result:", result[alice.memory.qstate_key])
print("Bob angle:", b, "result:", result[bob.memory.qstate_key])

# class SimpleManager:
#     def __init__(self, owner, memo_name):
#         self.owner = owner
#         self.memo_name = memo_name
#         self.raw_counter = 0
#         self.ent_counter = 0

#     def update(self, protocol, memory, state):
#         if state == 'RAW':
#             self.raw_counter += 1
#             memory.reset()
#         else:
#             self.ent_counter += 1

#     def create_protocol(self, middle: str, other: str):
#         self.owner.protocols = [EntanglementGenerationA.create(self.owner, '%s.eg' % self.owner.name, middle, other,
#                                                                self.owner.components[self.memo_name])]


# class EntangleGenNode(Node):
#     def __init__(self, name: str, tl: Timeline):
#         super().__init__(name, tl)

#         memo_name = '%s.memo' % name
#         memory = Memory(memo_name, tl, 0.9, 2000, 1, -1, 500)
#         memory.owner = self
#         memory.add_receiver(self)
#         self.add_component(memory)

#         self.resource_manager = SimpleManager(self, memo_name)

#     def init(self):
#         memory = self.get_components_by_type("Memory")[0]
#         memory.reset()

#     def receive_message(self, src: str, msg: "Message") -> None:
#         self.protocols[0].received_message(src, msg)

#     def get(self, photon, **kwargs):
#         self.send_qubit(kwargs['dst'], photon)




# tl = Timeline()

# node1 = EntangleGenNode('node1', tl)
# node2 = EntangleGenNode('node2', tl)
# bsm_node = BSMNode('bsm_node', tl, ['node1', 'node2'])
# # node1.set_seed(0)
# # node2.set_seed(1)
# # bsm_node.set_seed(2)

# bsm = bsm_node.get_components_by_type("SingleAtomBSM")[0]
# print(type(bsm))
# bsm.update_detectors_params('efficiency', 1)

# qc1 = QuantumChannel('qc1', tl, attenuation=0, distance=1000)
# qc2 = QuantumChannel('qc2', tl, attenuation=0, distance=1000)
# qc1.set_ends(node1, bsm_node.name)
# qc2.set_ends(node2, bsm_node.name)

# nodes = [node1, node2, bsm_node]

# for i in range(3):
#     for j in range(3):
#         if i != j:
#             cc= ClassicalChannel('cc_%s_%s'%(nodes[i].name, nodes[j].name), tl, 1000, 1e8)
#             cc.set_ends(nodes[i], nodes[j].name)


# from sequence.entanglement_management.entanglement_protocol import EntanglementProtocol


# def pair_protocol(node1: Node, node2: Node):
#     p1 = node1.protocols[0]
#     p2 = node2.protocols[0]
#     node1_memo_name = node1.get_components_by_type("Memory")[0].name
#     node2_memo_name = node2.get_components_by_type("Memory")[0].name
#     p1.set_others(p2.name, node2.name, [node2_memo_name])
#     p2.set_others(p1.name, node1.name, [node1_memo_name])


# node1.resource_manager.create_protocol('bsm_node', 'node2')
# node2.resource_manager.create_protocol('bsm_node', 'node1')
# pair_protocol(node1, node2)

# memory = node1.get_components_by_type("Memory")[0]

# print('before', memory.entangled_memory, memory.fidelity)
# # "before node1.memo {'node_id': None, 'memo_id': None} 0"

# tl.init()
# node1.protocols[0].start()
# node2.protocols[0].start()
# tl.run()

# print('after', memory.entangled_memory, memory.fidelity)




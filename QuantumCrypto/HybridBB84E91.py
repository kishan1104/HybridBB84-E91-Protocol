from sequence.kernel.timeline import Timeline

from sequence.topology.node import Node
from sequence.components.photon import Photon
from sequence.components.light_source import LightSource
from sequence.components.optical_channel import QuantumChannel
from sequence.components.detector import Detector
from sequence.kernel.process import Process
from sequence.kernel.event import Event
from sequence.topology.node import Node
from sequence.components.memory import Memory
from sequence.kernel.timeline import Timeline
from sequence.topology.node import BSMNode
from sequence.components.optical_channel import QuantumChannel, ClassicalChannel
from math import sqrt
from sequence.components.circuit import Circuit
import random
from sequence.utils.encoding import polarization


class CDetector(Detector):
    def __init__(self, name, timeline, efficiency = 1, dark_count = 0, count_rate = 25000000, time_resolution = 150):
        super().__init__(name, timeline, efficiency, dark_count, count_rate, time_resolution)
    
    def get(self,photon: Photon, **kwargs):
        self.photon_counter +=1
        
        if self.get_generator().random() < self.efficiency:
            choice = random.choice([0,1])
            basis = polarization['bases'][choice]
            # print(photon.quantum_state.state)
            output = photon.measure(basis, photon,self.get_generator())
            self.record_detection()
            self.owner.bob_basis_list.append(choice)
            self.owner.bob_bit_list.append(output)
           
            
        else:
            print(f'Photon loss in detector {self.name}')



tl = Timeline()
class AliceBob(Node):
    def __init__(self, name, timeline, seed=None, gate_fid = 1, meas_fid = 1):
        super().__init__(name, timeline, seed, gate_fid, meas_fid)

        self.memories = []
        self.alice_basis_list = []
        self.alice_bit_list = []
        self.alice_BB84_results = []
        self.bob_basis_list = []
        self.bob_BB84_results = []
        self.bob_bit_list = []
        self.alice_angles = []
        self.bob_angles = []
        self.alice_E91_results = []
        self.bob_E91_results = []

        self.detector = CDetector(
            name=f"{self.name}.detector",timeline=self.timeline)
        self.detector.owner = self
        self.add_component(self.detector)
        self.set_first_component(self.detector.name)


    def create_memory(self, name):
        memory = Memory(name, self.timeline, 1, 2000, 1, -1, 500)
        memory.owner = self
        memory.add_receiver(self)
        self.add_component(memory)
        self.memories.append(memory)


    def receive_qubit(self, src, qubit):
        # print(f'{self.name} received qubit from {src} at time {self.timeline.now()}')
        return super().receive_qubit(src, qubit)
    
    
    def send_bb84(self,alice, bob,photon):
        alice.send_qubit(bob.name, photon)
    
def entangle_memory(memo1, memo2, fidelity):

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

def measure(alice,bob,mem):
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

    qm = alice.memories[mem].timeline.quantum_manager
    rng = alice.get_generator()

    result = qm.run_circuit(
        circuit,
        [alice.memories[mem].qstate_key, bob.memories[mem].qstate_key],
        meas_samp=rng.random()
    )
    return result,a,b


    



class HybridBB84E91():
    def __init__(self,rho,alice:AliceBob,bob:AliceBob,timeline:Timeline):
        self.rho = rho
        self.bb84counter = 0
        self.e91counter = 0
        self.alice = alice
        self.bob = bob
        self.timeline = timeline
        self.time = 0
    def start(self,round):
        self.time += 1000
        r = random.random()
        if r<self.rho:
            self.BB84()
            

        else:
            self.E91()
            
    def BB84(self):
        basis = random.choice([0,1])
        bit = random.choice([0,1])
        self.alice.alice_basis_list.append(basis)
        self.alice.alice_bit_list.append(bit)

        if basis == 0 and bit == 0:
            state = (complex(1), complex(0))
        elif basis == 0 and bit == 1:
            state = (complex(0), complex(1))
        elif basis == 1 and bit == 0:
            state = (complex(sqrt(1/2)), complex(sqrt(1/2)))
        else:            
            state = (complex(-sqrt(1/2)), complex(sqrt(1/2)))
        photon = Photon(f'{self.alice.name}.photon{self.bb84counter}', self.timeline,quantum_state=state)

        process = Process(self.alice, "send_bb84", [self.alice,self.bob,photon])
        event = Event(self.timeline.now()+self.time, process)
        self.timeline.schedule(event)

        self.bb84counter +=1
        # print('running BB84')

    def E91(self):
        self.alice.create_memory(f'{self.alice.name+str(self.e91counter)}.memory{self.e91counter}')
        self.bob.create_memory(f'{self.bob.name+str(self.e91counter)}.memory{self.e91counter}')
        entangle_memory(self.alice.memories[-1], self.bob.memories[-1], 1)
        result,a,b = measure(self.alice,self.bob,-1)
        self.alice.alice_angles.append(a)
        self.bob.bob_angles.append(b)
        self.alice.alice_E91_results.append(result[self.alice.memories[-1].qstate_key])
        self.bob.bob_E91_results.append(result[self.bob.memories[-1].qstate_key])

        self.e91counter +=1
        # print('E91')
    def sifting(self):
        # print('sifting')
        message = []

        for i in range(len(self.alice.alice_basis_list)):
            if self.alice.alice_basis_list[i] == self.bob.bob_basis_list[i]:
                self.alice.alice_BB84_results.append(self.alice.alice_bit_list[i])
                self.bob.bob_BB84_results.append(self.bob.bob_bit_list[i])



alice = AliceBob('alice',tl)
bob = AliceBob('bob',tl)

channel = QuantumChannel(
    name='qc',
    timeline=tl,
    attenuation=0,
    distance=1000
)
cc_ab = ClassicalChannel(
    name='cc_ab',
    timeline=tl,
    distance=1000
)
cc_ba = ClassicalChannel(
    name='cc_ba',
    timeline=tl,
    distance=1000
)

cc_ab.set_ends(alice,bob.name)
cc_ba.set_ends(bob,alice.name)

channel.set_ends(alice,bob.name)

hnew = HybridBB84E91(0.8,alice,bob,tl)
for i in range(10):
    hnew.start(i)

tl.init()

tl.run()

hnew.sifting()

# print(hnew.e91counter)
# print(hnew.bb84counter)

# print("alice basis list: ", alice.alice_basis_list)
# print("alice bit list:   ", alice.alice_bit_list)
# print("bob basis list:   ", bob.bob_basis_list)
# print("bob bit list:     ", bob.bob_bit_list)

print("alice BB84 results:", alice.alice_BB84_results)
print("alice E91 results:", alice.alice_E91_results)
print("bob BB84 results:", bob.bob_BB84_results)
print("Bob results:", bob.bob_E91_results)




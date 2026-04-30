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
from math import sqrt, log2, pi
from sequence.components.circuit import Circuit
import random
import hashlib
from sequence.utils.encoding import polarization

import numpy as np

def Ry(theta):
    return np.array([
        [np.cos(theta/2), -np.sin(theta/2)],
        [np.sin(theta/2),  np.cos(theta/2)]
    ])

def apply_rotation(qm, k1, k2, theta, target):
    state_obj = qm.get(k1)
    state = np.array(state_obj.state)

    Ry_gate = Ry(theta)

    if target == 0:
        U = np.kron(Ry_gate, np.eye(2))
    else:
        U = np.kron(np.eye(2), Ry_gate)

    new_state = U @ state

    qm.set([k1, k2], new_state)

class CDetector(Detector):
    def __init__(self, name, timeline, efficiency=1, dark_count=0, count_rate=25000000, time_resolution=150):
        super().__init__(name, timeline, efficiency, dark_count, count_rate, time_resolution)

    def get(self, photon: Photon, **__):
        self.photon_counter += 1
        if self.get_generator().random() < self.efficiency:
            choice = random.choice([0, 1])
            basis = polarization['bases'][choice]
            output = photon.measure(basis, photon, self.get_generator())
            self.record_detection()
            self.owner.bob_basis_list.append(choice)
            self.owner.bob_bit_list.append(output)
        else:
            choice = random.choice([0, 1])
            self.owner.bob_basis_list.append(choice)
            self.owner.bob_bit_list.append(random.choice([0, 1]))
            print(f'Photon loss in detector {self.name}')


tl = Timeline()


class AliceBob(Node):
    def __init__(self, name, timeline, seed=None, gate_fid=1, meas_fid=1):
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
        self.final_key_alice = []
        self.final_key_bob = []

        self.detector = CDetector(name=f"{self.name}.detector", timeline=self.timeline)
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
        return super().receive_qubit(src, qubit)

    def send_bb84(self, alice, bob, photon):
        alice.send_qubit(bob.name, photon)


def entangle_memory(memo1, memo2, fidelity):
    memo1.reset()
    memo2.reset()
    memo1.entangled_memory['node_id'] = memo2.owner.name
    memo1.entangled_memory['memo_id'] = memo2.name
    memo2.entangled_memory['node_id'] = memo1.owner.name
    memo2.entangled_memory['memo_id'] = memo1.name
    memo1.fidelity = memo2.fidelity = fidelity
    qm = memo1.timeline.quantum_manager
    # |ψ⁻⟩ = (|01⟩ - |10⟩)/√2  in basis {|00⟩,|01⟩,|10⟩,|11⟩}
    qm.set(
        [memo1.qstate_key, memo2.qstate_key],
        [0, 1/sqrt(2), -1/sqrt(2), 0]
    )


def measure(alice, bob, mem):
    import numpy as np
    import random
    from sequence.components.circuit import Circuit

    alice_angles = [0, 90]
    bob_angles   = [45, 135]

    a = random.choice(alice_angles)
    b = random.choice(bob_angles)

    qm = alice.memories[mem].timeline.quantum_manager

    k1 = alice.memories[mem].qstate_key
    k2 = bob.memories[mem].qstate_key

    # -------- exact rotations --------
    if a == 90:
        apply_rotation(qm, k1, k2, -np.pi/2, target=0)

    if b == 45:
        apply_rotation(qm, k1, k2, -np.pi/4, target=1)
    elif b == 135:
        apply_rotation(qm, k1, k2, -3*np.pi/4, target=1)

    # -------- measurement --------
    circuit = Circuit(2)
    circuit.measure(0)
    circuit.measure(1)

    rng = alice.get_generator()

    result = qm.run_circuit(
        circuit,
        [k1, k2],
        meas_samp=rng.random()
    )

    return result, a, b

class HybridBB84E91():
    def __init__(self, rho, alice: AliceBob, bob: AliceBob, timeline: Timeline):
        self.rho = rho
        self.bb84counter = 0
        self.e91counter = 0
        self.alice = alice
        self.bob = bob
        self.timeline = timeline
        self.time = 0
        self.qber = None
        self.chsh_s = None

    def start(self, round):
        self.time += 1000
        r = random.random()
        if r < self.rho:
            self.BB84()
        else:
            self.E91()

    def BB84(self):
        basis = random.choice([0, 1])
        bit = random.choice([0, 1])
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

        photon = Photon(f'{self.alice.name}.photon{self.bb84counter}', self.timeline, quantum_state=state)
        process = Process(self.alice, "send_bb84", [self.alice, self.bob, photon])
        event = Event(self.timeline.now() + self.time, process)
        self.timeline.schedule(event)
        self.bb84counter += 1

    def E91(self):
        self.alice.create_memory(f'{self.alice.name+str(self.e91counter)}.memory{self.e91counter}')
        self.bob.create_memory(f'{self.bob.name+str(self.e91counter)}.memory{self.e91counter}')
        entangle_memory(self.alice.memories[-1], self.bob.memories[-1], 1)
        result, a, b = measure(self.alice, self.bob, -1)
        self.alice.alice_angles.append(a)
        self.bob.bob_angles.append(b)
        self.alice.alice_E91_results.append(result[self.alice.memories[-1].qstate_key])
        self.bob.bob_E91_results.append(result[self.bob.memories[-1].qstate_key])
        self.e91counter += 1

    # ── Step Sifting ──────────────────────────────────────────────────
    def sifting(self):
        bob_len = len(self.bob.bob_basis_list)
        for i in range(len(self.alice.alice_basis_list)):
            if i >= bob_len:
                break
            if self.alice.alice_basis_list[i] == self.bob.bob_basis_list[i]:
                self.alice.alice_BB84_results.append(self.alice.alice_bit_list[i])
                self.bob.bob_BB84_results.append(self.bob.bob_bit_list[i])

    # ──  QBER from BB84 sample ──────────────────────────────────────
    def _estimate_qber(self):
        alice_bits = self.alice.alice_BB84_results
        bob_bits   = self.bob.bob_BB84_results
        n = min(len(alice_bits), len(bob_bits))
        if n == 0:
            return 1.0, [], []
        sample_size = max(1, n // 2)
        sample_idx  = set(random.sample(range(n), sample_size))
        errors = sum(1 for i in sample_idx if alice_bits[i] != bob_bits[i])
        qber = errors / sample_size
        # Remove revealed sample bits — they can no longer contribute to the key
        remaining_alice = [alice_bits[i] for i in range(n) if i not in sample_idx]
        remaining_bob   = [bob_bits[i]   for i in range(n) if i not in sample_idx]
        return qber, remaining_alice, remaining_bob

    # ── CHSH S from E91 rounds  ─────────────────────────────
    def _compute_chsh(self):
        corr   = {}
        counts = {}
        for a, b, ar, br in zip(
            self.alice.alice_angles, self.bob.bob_angles,
            self.alice.alice_E91_results, self.bob.bob_E91_results
        ):
            # Map measurement outcomes 0/1 → spin values +1/−1
            a_spin = 1 - 2 * int(ar)
            b_spin = 1 - 2 * int(br)
            key = (a, b)
            corr[key]   = corr.get(key, 0.0) + a_spin * b_spin
            counts[key] = counts.get(key, 0)  + 1

        def E(a, b):
            k = (a, b)
            return corr[k] / counts[k] if counts.get(k, 0) > 0 else 0.0

        
        S = (
            E(0,45)
            - E(0,135)
            + E(90,45)
            + E(90,135)
            )
        return abs(S)

    # ── Steps 17–22: Parameter Estimation + Abort ────────────────────────────
    def parameter_estimation(self, qber_threshold=0.11, chsh_threshold=2.0):
        print("\n=== Parameter Estimation ===")
        print(f"  BB84 rounds: {self.bb84counter}  |  E91 rounds: {self.e91counter}")

        qber, remaining_alice, remaining_bob = self._estimate_qber()
        self.qber = qber

        S = self._compute_chsh()
        self.chsh_s = S

        print(f"  QBER Q  = {qber:.4f}  (abort if > {qber_threshold})")
        print(f"  CHSH |S| = {S:.4f}  (abort if ≤ {chsh_threshold})")

        abort = False
        if qber > qber_threshold:
            print("  ABORT: QBER too high — possible eavesdropper on BB84 channel.")
            abort = True
        if S <= chsh_threshold:
            print("  ABORT: CHSH parameter too low — entanglement integrity not verified.")
            abort = True

        if not abort:
            print("  Security checks PASSED.")

        return not abort, remaining_alice, remaining_bob


    # ──  Privacy Amplification ──────────────────────────────────
    def privacy_amplification(self, key, leak_bits, epsilon_PA=1e-10):
        """
        Compress key to ℓ ≤ H_min(X^n|E) − leak_EC − 2·log(1/ε_PA) bits
        using a SHA-256-based universal hash.
        """
        print("\n=== Privacy Amplification ===")
        n = len(key)
        if n == 0:
            print("  Warning: No key bits to amplify.")
            return []

        qber = self.qber if self.qber is not None else 0.0
        if 0 < qber < 1:
            h_qber = -qber * log2(qber) - (1 - qber) * log2(1 - qber)
        else:
            h_qber = 0.0

        h_min          = n * (1 - h_qber)            # Eq. 1 (simplified BB84 min-entropy)
        security_param = 2 * log2(1 / epsilon_PA)    # 2·log(1/ε_PA)
        secure_length  = max(0, int(h_min - leak_bits - security_param))

        print(f"  Raw key: {n} bits")
        print(f"  H_min ≈ {h_min:.1f}  |  leak_EC = {leak_bits}  |  2·log(1/ε) = {security_param:.1f}")
        print(f"  Final secure key length ℓ = {secure_length} bits")

        if secure_length == 0:
            print("  Warning: No secure bits remain after privacy amplification.")
            return []

        # Pack bits into bytes (pad to multiple of 8)
        padded = key + [0] * ((8 - len(key) % 8) % 8)
        key_bytes = bytes(
            sum(padded[i + j] << (7 - j) for j in range(8))
            for i in range(0, len(padded), 8)
        )

        # Extend via iterated SHA-256 until we have enough bits
        final_bits = []
        seed = 0
        while len(final_bits) < secure_length:
            digest = hashlib.sha256(key_bytes + seed.to_bytes(4, 'big')).digest()
            for byte in digest:
                for shift in range(7, -1, -1):
                    final_bits.append((byte >> shift) & 1)
            seed += 1

        return final_bits[:secure_length]

    # ── Full protocol orchestrator ────────────────────────────────────────────
    def run_full_protocol(self):
        secure, alice_key, bob_key = self.parameter_estimation()
        if not secure:
            return None
        
        final_key_alice = self.privacy_amplification(alice_key, 0)
        final_key_bob   = self.privacy_amplification(bob_key, 0)
        self.alice.final_key_alice = final_key_alice
        self.bob.final_key_bob = final_key_bob
        return final_key_alice, final_key_bob


# ─── Setup ───────────────────────────────────────────────────────────────────
alice = AliceBob('alice', tl)
bob   = AliceBob('bob',   tl)

channel = QuantumChannel(name='qc',    timeline=tl, attenuation=0, distance=1000)
cc_ab   = ClassicalChannel(name='cc_ab', timeline=tl, distance=1000)
cc_ba   = ClassicalChannel(name='cc_ba', timeline=tl, distance=1000)

cc_ab.set_ends(alice, bob.name)
cc_ba.set_ends(bob,   alice.name)
channel.set_ends(alice, bob.name)

# ─── Run simulation ──────────────────────────────────────────────────────────

rounds = 1000

hnew = HybridBB84E91(0.8, alice, bob, tl)
for i in range(rounds):
    hnew.start(i)

tl.init()
tl.run()





# ─── Protocol phases ─────────────────────────────────────────────────────────
print("\n=== Sifting ===")
hnew.sifting()
print(f"  Matched BB84 bits: {len(alice.alice_BB84_results)}")

final_key_alice, final_key_bob = hnew.run_full_protocol()



print("\n=== Summary of Results ===")
preview_alice = ''.join(map(str, final_key_alice[:64]))
ellipsis = '...' if len(final_key_alice) > 64 else ''
preview_bob   = ''.join(map(str, final_key_bob[:64]))
print(f"  Final Key (Alice): {preview_alice}{ellipsis}")
print(f"  Final Key (Bob)  : {preview_bob}{ellipsis}")

import numpy as np
from qiskit import *
from qiskit_ibm_runtime import IBMBackend
from qiskit import QuantumCircuit, QuantumRegister, ClassicalRegister, transpile
from qiskit.circuit.library import ZGate, XGate, YGate
from qiskit.transpiler import PassManager
from qiskit.transpiler.passes import ALAPScheduleAnalysis, PadDynamicalDecoupling
from qiskit.circuit.equivalence_library import SessionEquivalenceLibrary as sel
from qiskit.transpiler.passes import BasisTranslator
from qiskit.transpiler import InstructionProperties
from qiskit_ibm_runtime import SamplerV2
from qiskit.quantum_info.analysis import hellinger_fidelity

class Experiment:
    def __init__(self, numQubits:int, initialLayout: list[int], initialLayoutWithBuffer: list[int], backend: IBMBackend, initialState:int = 0, ddSequenceType:int = 0):
        """
        Initialize the Experiment class with quantum circuit parameters and backend.
        
        :param numQubits: Number of qubits in the experiment
        :param initialLayout: Initial layout of qubits on the backend
        :param initialLayoutWithBuffer: Initial layout with buffer qubits
        :param backend: IBM quantum backend to execute circuits
        :param initialState: Initial state of qubits (0: |0>, 1: |1>, 2: |+>)
        :param ddSequenceType: Type of dynamical decoupling sequence (0 for XYXY or 1 for XX)

        If the parameters are not provided, default values for Layout (1) are considered
        """

        if numQubits:
            self.numQubits = numQubits
        else:
            self.numQubits = 9
        
        if len(initialLayout):
            self.initialLayout = initialLayout
        else:
            self.initialLayout = [4,3,5,15,22,2,1,6,7]
            
        if len(initialLayoutWithBuffer):
            self.initialLayoutWithBuffer = initialLayoutWithBuffer
        else:
            self.initialLayoutWithBuffer = [4,3,5,22,23,1,0,7,8]
        
        self.initialState = initialState
        self.ddSequenceType = ddSequenceType
        self.groverOperator = self.createGroverOperator()
        self.backend = backend
        self.addYGateToTargetBackend()
        self.circuits = []
        self.result = []
        self.fidelities = []
        
    def createGroverOperator(self):
        """
        Creates a 3-qubit Grover diffusion operator circuit.
        
        :return: Grover diffusion operator as a circuit instruction
        """
        qc = QuantumCircuit(3)
        ccz = ZGate().control(2)

        qc.append(ccz,[0,1,2])

        qc.h(0)
        qc.h(1)
        qc.h(2)

        qc.x(0)    
        qc.x(1)    
        qc.x(2)

        qc.append(ccz,[0,1,2])

        qc.x(0)    
        qc.x(1)    
        qc.x(2)

        qc.h(0)
        qc.h(1)
        qc.h(2)
        
        groverOperator = qc.to_instruction()
        return groverOperator
    
    def addYGateToTargetBackend(self):
        """
        Adds a Y gate to the target backend if it is not already available.
        This ensures that the backend supports Y gates for transpilation.
        """
        target = self.backend.target
        y_gate_properties = {}
        yPresent = False
        for instruction in target.instructions:
            if instruction[0].name == 'y':
                yPresent = True
                break
        if not yPresent:        
            for qubit in range(target.num_qubits):
                y_gate_properties.update(
                    {
                        (qubit,): InstructionProperties(
                            duration=target["x"][(qubit,)].duration,
                            error=target["x"][(qubit,)].error,
                        )
                    }
                )

            target.add_instruction(YGate(), y_gate_properties)
        
    def addNoAttackCircuit(self):
        """
        Creates a quantum circuit without an attack and appends it to the circuit list.
        The circuit includes a Grover operator applied twice and measurement.
        """
        q = QuantumRegister(self.numQubits)
        c = ClassicalRegister(self.numQubits)
        qc = QuantumCircuit(q,c)
        if self.initialState == 1:
            for i in range(3,self.numQubits,2):
                qc.x(q[i])
        elif self.initialState == 2:
            for i in range(3,self.numQubits,2):
                qc.h(q[i])

        qc.h(q[0])    
        qc.h(q[1])
        qc.h(q[2])

        qc.append(self.groverOperator,[q[0],q[1],q[2]])
        qc.append(self.groverOperator,[q[0],q[1],q[2]])

        qc.measure(q,c)
        tr_circuit = transpile(qc,self.backend,scheduling_method='alap',initial_layout=self.initialLayout,optimization_level=2)
        self.circuits.append(tr_circuit)
        
    def addNoAttackPlusDDCircuit(self):
        """
        Creates a quantum circuit without an attack but with dynamical decoupling (DD) 
        and appends it to the circuit list.
        """
        q = QuantumRegister(self.numQubits)
        c = ClassicalRegister(self.numQubits)
        qc = QuantumCircuit(q,c)
        
        if self.initialState == 1:
            for i in range(3,self.numQubits,2):
                qc.x(q[i])
        elif self.initialState == 2:
            for i in range(3,self.numQubits,2):
                qc.h(q[i])
        
        qc.h(q[0])    
        qc.h(q[1])
        qc.h(q[2])

        qc.append(self.groverOperator,[q[0],q[1],q[2]])
        qc.append(self.groverOperator,[q[0],q[1],q[2]])
        qc.measure(q,c)
        
        target = self.backend.target
        tr_circuit = transpile(qc,self.backend,scheduling_method='alap',initial_layout=self.initialLayout,optimization_level=2)
        if self.ddSequenceType == 1:
            dd_sequence = [XGate(), YGate(), XGate(), YGate()]
        else:
            dd_sequence = [XGate(), XGate()]
            
        dd_pm = PassManager(
            [
                ALAPScheduleAnalysis(target=target),
                PadDynamicalDecoupling(target=target, dd_sequence=dd_sequence, qubits=self.initialLayout[:3]),
            ]
        )
        circ_dd = dd_pm.run(tr_circuit)

        for item in circ_dd.data:
            if item[0].duration % 8:
                item[0].duration = ((item[0].duration // 8) + 1) * 8

        qc_dd = BasisTranslator(sel, self.backend.basis_gates)(circ_dd)
        self.circuits.append(qc_dd)
        
    def addAttackWithoutMitigationCircuits(self):
        """
        Creates multiple circuits simulating an attack scenario without mitigation techniques.
        The attack modifies CX gate application timing and applies delays.
        """
        slots = 8
        for i in range(45):
            q = QuantumRegister(self.numQubits)
            c = ClassicalRegister(self.numQubits)
            qc = QuantumCircuit(q,c)

            if self.initialState == 1:
                for k in range(3,self.numQubits,2):
                    qc.x(q[k])
            elif self.initialState == 2:
                for k in range(3,self.numQubits,2):
                    qc.h(q[k])

            qc.h(q[0])    
            qc.h(q[1])
            qc.h(q[2])

            qc.append(self.groverOperator,[q[0],q[1],q[2]])
            qc.append(self.groverOperator,[q[0],q[1],q[2]])

            if i < 20 and i % 5 == 0:
                slots = slots / 2
            elif i >= 20 and i < 25:
                slots = 0.75
            elif i >= 25 and i < 30:
                slots = 0.5
            elif i >= 30 and i < 35:
                slots = 0.05
            elif i >= 35 and i < 40:
                slots = 0.025

            for j in range(i):
                for k in range(3,self.numQubits,2):    
                    qc.cx(q[k],q[k+1])
                    qc.delay(slots,unit="us",qarg=q[k])

            qc.measure(q,c)
            tr_circuit = transpile(qc,self.backend,scheduling_method='alap',initial_layout=self.initialLayout,optimization_level=2)
            self.circuits.append(tr_circuit)
            
    def addAttackWithDDCircuits(self):
        """
        Creates multiple circuits simulating an attack scenario with dynamical 
        decoupling applied for mitigation.
        """
        slots = 8
        for i in range(45):
            q = QuantumRegister(self.numQubits)
            c = ClassicalRegister(self.numQubits)
            qc = QuantumCircuit(q,c)

            if self.initialState == 1:
                for k in range(3,self.numQubits,2):
                    qc.x(q[k])
            elif self.initialState == 2:
                for k in range(3,self.numQubits,2):
                    qc.h(q[k])

            qc.h(q[0])    
            qc.h(q[1])
            qc.h(q[2])

            qc.append(self.groverOperator,[q[0],q[1],q[2]])
            qc.append(self.groverOperator,[q[0],q[1],q[2]])

            if i < 20 and i % 5 == 0:
                slots = slots / 2
            elif i >= 20 and i < 25:
                slots = 0.75
            elif i >= 25 and i < 30:
                slots = 0.5
            elif i >= 30 and i < 35:
                slots = 0.05
            elif i >= 35 and i < 40:
                slots = 0.025

            for j in range(i):
                for k in range(3,self.numQubits,2):    
                    qc.cx(q[k],q[k+1])
                    qc.delay(slots,unit="us",qarg=q[k])

            qc.measure(q,c)
            target = self.backend.target
            tr_circuit = transpile(qc,self.backend,scheduling_method='alap',initial_layout=self.initialLayout,optimization_level=2)
            if self.ddSequenceType == 1:
                dd_sequence = [XGate(), YGate(), XGate(), YGate()]
            else:
                dd_sequence = [XGate(), XGate()]
                
            dd_pm = PassManager(
                [
                    ALAPScheduleAnalysis(target=target),
                    PadDynamicalDecoupling(target=target, dd_sequence=dd_sequence, qubits=self.initialLayout[:3]),
                ]
            )
            circ_dd = dd_pm.run(tr_circuit)

            for item in circ_dd.data:
                if item[0].duration % 8:
                    item[0].duration = ((item[0].duration // 8) + 1) * 8

            qc_dd = BasisTranslator(sel, self.backend.basis_gates)(circ_dd)
            self.circuits.append(qc_dd)
            
    def addAttackWithSpacingCircuits(self):
        """
        Creates multiple circuits simulating an attack scenario with buffer spacing
        applied for mitigation.
        """
        slots = 8
        for i in range(45):
            q = QuantumRegister(self.numQubits + (self.numQubits - 3)//2)
            c = ClassicalRegister(self.numQubits + (self.numQubits - 3)//2)
            qc = QuantumCircuit(q,c)

            if self.initialState == 1:
                for k in range(3,self.numQubits,2):
                    qc.x(q[k])
            elif self.initialState == 2:
                for k in range(3,self.numQubits,2):
                    qc.h(q[k])

            qc.h(q[0])    
            qc.h(q[1])
            qc.h(q[2])

            qc.append(self.groverOperator,[q[0],q[1],q[2]])
            qc.append(self.groverOperator,[q[0],q[1],q[2]])

            if i < 20 and i % 5 == 0:
                slots = slots / 2
            elif i >= 20 and i < 25:
                slots = 0.75
            elif i >= 25 and i < 30:
                slots = 0.5
            elif i >= 30 and i < 35:
                slots = 0.05
            elif i >= 35 and i < 40:
                slots = 0.025

            for j in range(i):
                for k in range(3,self.numQubits,3):    
                    qc.cx(q[k+1],q[k+2])
                    qc.delay(slots,unit="us",qarg=q[k+1])

            qc.measure(q,c)
            tr_circuit = transpile(qc,self.backend,scheduling_method='alap',initial_layout=self.initialLayoutWithBuffer,optimization_level=2)
            self.circuits.append(tr_circuit)
            
    def addAttackWithDDAndSpacingCircuits(self):
        """
        Creates multiple circuits simulating an attack scenario with dynamical 
        decoupling and buffer spacing applied for mitigation.
        """
        slots = 8
        for i in range(45):
            q = QuantumRegister(self.numQubits + (self.numQubits - 3)//2)
            c = ClassicalRegister(self.numQubits + (self.numQubits - 3)//2)
            qc = QuantumCircuit(q,c)

            if self.initialState == 1:
                for k in range(3,self.numQubits,2):
                    qc.x(q[k])
            elif self.initialState == 2:
                for k in range(3,self.numQubits,2):
                    qc.h(q[k])

            qc.h(q[0])    
            qc.h(q[1])
            qc.h(q[2])

            qc.append(self.groverOperator,[q[0],q[1],q[2]])
            qc.append(self.groverOperator,[q[0],q[1],q[2]])

            if i < 20 and i % 5 == 0:
                slots = slots / 2
            elif i >= 20 and i < 25:
                slots = 0.75
            elif i >= 25 and i < 30:
                slots = 0.5
            elif i >= 30 and i < 35:
                slots = 0.05
            elif i >= 35 and i < 40:
                slots = 0.025

            for j in range(i):
                for k in range(3,self.numQubits,3):    
                    qc.cx(q[k+1],q[k+2])
                    qc.delay(slots,unit="us",qarg=q[k+1])

            qc.measure(q,c)
            target = self.backend.target
            tr_circuit = transpile(qc,self.backend,scheduling_method='alap',initial_layout=self.initialLayoutWithBuffer,optimization_level=2)
            if self.ddSequenceType == 1:
                dd_sequence = [XGate(), YGate(), XGate(), YGate()]
            else:
                dd_sequence = [XGate(), XGate()]
                
            dd_pm = PassManager(
                [
                    ALAPScheduleAnalysis(target=target),
                    PadDynamicalDecoupling(target=target, dd_sequence=dd_sequence, qubits=self.initialLayoutWithBuffer[:3]),
                ]
            )
            circ_dd = dd_pm.run(tr_circuit)

            for item in circ_dd.data:
                if item[0].duration % 8:
                    item[0].duration = ((item[0].duration // 8) + 1) * 8

            qc_dd = BasisTranslator(sel, self.backend.basis_gates)(circ_dd)
            self.circuits.append(qc_dd)
        
    def runAllCircuits(self):
        """
        Executes all quantum circuits stored in the 'circuits' list using the specified backend.
        
        This function prepares the circuits for execution by wrapping each one in a separate list, 
        runs them using the SamplerV2 class, and stores the measurement results. The results are 
        stored in 'self.result' as a list of dictionaries, where each dictionary contains bitstring 
        outcomes and their corresponding counts.
        """
        circuitarray = []
        for circuit in self.circuits:
            circuitarray.append([circuit])
        sampler = SamplerV2(mode=self.backend)
        job = sampler.run(circuitarray)
        jobResult = job.result()
        self.result = []
        for i in range(len(self.circuits)):
            self.result.append(jobResult[i].join_data().get_counts())

    def getResult(self):
        """
        Returns the measurement results of the executed quantum circuits.
        
        If no results are available (i.e., circuits have not been run yet), 
        a warning message is printed, and an empty list is returned.
        """
        if not len(self.result):
            print("No results yet, returning an empty array.")
        return self.result
    
    def calculateFidelityOfDataQubits(self):
        """
        Computes the fidelity between an expected ideal distribution and the measured results.
        
        This function extracts the last three bits from each measurement outcome (data qubits 
        only) to compare the distribution of data qubits against a predefined ideal state.
        The fidelity is calculated using the Hellinger fidelity metric and stored in 
        'self.fidelities'.
        """
        def find_fidelity(counts):
            initialState = {'111': 968,'101': 8,'011': 8,'110': 8,'100': 8,'010': 8,'001': 8,'000': 8}
            finalState = {}
            for key in counts:
                key_prefix = key[-3:]
                if key_prefix not in finalState:
                    finalState[key_prefix] = 0  # Initialize the key if it doesn't exist
                finalState[key_prefix] += counts[key]
            fidelity = hellinger_fidelity(initialState, finalState)
            return fidelity

        self.fidelities = []
        i = 0
        for count in self.result:
            f = find_fidelity(count)
            i = i + 1
            self.fidelities.append(f)
    
    def getFidelities(self):
        """
        Returns the list of computed fidelities for the quantum circuit results.
        
        If fidelity values have not been calculated yet, a warning message is printed, 
        and an empty list is returned.
        """
        if not len(self.fidelities):
            print("Fidelities are not yet calculated. Returning an empty array")
        return self.fidelities